from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import html as html_lib
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import urllib.request
import feedparser

DATA_DIR = Path("data")
MAX_ITEMS_PER_SECTION = 40

REGISTRATION_KEYWORDS = [
    "ثبت نام", "ثبتنام", "نام نویسی", "پیش ثبت نام", "فراخوان",
    "تمدید مهلت", "مهلت ثبت", "مهلت نام نویسی", "آغاز ثبت", "شروع ثبت",
    "زمان ثبت", "نحوه ثبت", "سامانه ثبت", "دریافت کارت", "کارت ورود به جلسه",
    "ویرایش اطلاعات", "تکمیل ظرفیت", "اعلام نتایج", "نتایج اولیه",
    "آزمون استخدامی", "استخدام", "کنکور", "وام", "یارانه", "کالابرگ",
    "کارت سوخت", "سجام", "سهام عدالت", "اظهارنامه", "مالیات", "خودرو",
    "حج", "عتبات", "نوبت دهی", "تعویض پلاک", "گذرنامه", "نظام وظیفه",
    "ابلاغیه", "ثنا", "نرخ خدمات", "تعرفه",
]

EXCLUDE_KEYWORDS = [
    "تبلیغ", "رپورتاژ", "فال", "طالع", "ورزشی", "فوتبال",
    "قرعه کشی تلگرام", "پروکسی", "فیلترشکن",
]

BLOCKED_LINK_DOMAINS = (
    "isna.ir", "mehrnews.com", "tasnimnews.ir", "khabaronline.ir",
    "onlinecofe.ir", "cafeneti.com", "cofeeenet.ir", "farsnews.ir",
    "irna.ir", "yjc.ir", "tabnak.ir", "entekhab.ir", "asriran.com",
    "t.me", "telegram.me", "telegram.org", "eitaa.com", "rubika.ir",
    "ble.ir", "instagram.com", "eestekhdam.com",
)

PORTAL_RULES = [
    (["کنکور", "سنجش", "پزشکی", "آزمون استخدامی", "تخصصی", "دکتری", "کارشناسی ارشد", "کارت ورود به جلسه", "اعلام نتایج"], "https://my.sanjesh.org"),
    (["آموزش و پرورش", "مدارس", "مای مدیو", "my.medu"], "https://my.medu.ir"),
    (["یارانه", "کالابرگ", "حمایتی"], "https://hemayat.mcls.gov.ir"),
    (["سجام"], "https://www.sejam.ir"),
    (["سهام عدالت"], "https://www.sahamedalat.ir"),
    (["مالیات", "اظهارنامه", "مودیان", "مالیاتی"], "https://my.tax.gov.ir"),
    (["کارت سوخت", "سوخت"], "https://fcp.niopdc.ir"),
    (["خودرو", "یکپارچه خودرو", "فروش خودرو", "تعویض پلاک"], "https://esale.ikco.ir"),
    (["گذرنامه", "نظام وظیفه", "سخا", "پلیس من"], "https://sakha.epolice.ir"),
    (["حج", "عتبات", "عمره"], "https://my.haj.ir"),
    (["ثبت احوال", "شناسنامه", "کارت ملی"], "https://ncr.ir"),
    (["ثنا", "ابلاغیه", "قوه قضاییه", "عدل ایران"], "https://adliran.ir"),
]

SECTIONS = {
    "cafenet": {
        "file": DATA_DIR / "cafenet.json",
        "sources": [
            {"type": "telegram", "name": "تلگرام کافی‌نت ۱", "url": "https://t.me/s/akhbar_cafenet"},
            {"type": "telegram", "name": "تلگرام کافی‌نت ۲", "url": "https://t.me/s/nerkh_net"},
            {"type": "telegram", "name": "تلگرام کافی‌نت ۳", "url": "https://t.me/s/ertebat_ba_adminhaa2"},
            {"type": "rss", "name": "دستیار کافی‌نت", "url": "https://onlinecofe.ir/news/feed/"},
            {"type": "rss", "name": "کافی نتی", "url": "https://cafeneti.com/feed/"},
            {"type": "rss", "name": "کافی نت آنلاین", "url": "https://cofeeenet.ir/feed/"},
            {"type": "rss", "name": "تسنیم اقتصادی", "url": "https://www.tasnimnews.ir/fa/rss/feed/0/8/7"},
            {"type": "rss", "name": "تسنیم اجتماعی", "url": "https://www.tasnimnews.ir/fa/rss/feed/0/8/2"},
            {"type": "rss", "name": "مهر اقتصادی", "url": "https://www.mehrnews.com/rss/tp/25"},
            {"type": "rss", "name": "ایسنا اقتصادی", "url": "https://www.isna.ir/rss/tp/34"},
            {"type": "rss", "name": "خبرآنلاین اقتصادی", "url": "https://www.khabaronline.ir/rss/tp/2"},
        ],
    },
    "exams": {
        "file": DATA_DIR / "exams.json",
        "sources": [
            {"type": "telegram", "name": "تلگرام استخدامی", "url": "https://t.me/s/eestekhdam_com"},
            {"type": "rss", "name": "ایسنا آموزش", "url": "https://www.isna.ir/rss/tp/390"},
            {"type": "rss", "name": "ایسنا آموزش و پرورش", "url": "https://www.isna.ir/rss/tp/59"},
            {"type": "rss", "name": "مهر دانشجویی", "url": "https://www.mehrnews.com/rss/tp/178"},
            {"type": "rss", "name": "خبرآنلاین آموزش", "url": "https://www.khabaronline.ir/rss/tp/43"},
            {"type": "rss", "name": "تسنیم آموزش", "url": "https://www.tasnimnews.ir/fa/rss/feed/0/8/22"},
        ],
    },
    "notices": {
        "file": DATA_DIR / "notices.json",
        "sources": [
            {"type": "telegram", "name": "تلگرام مالیاتی", "url": "https://t.me/s/taxpress"},
            {
                "type": "rss",
                "name": "کافی نت آنلاین ثبت‌نام‌ها",
                "url": "https://cofeeenet.ir/category/%d8%a7%d8%ae%d8%a8%d8%a7%d8%b1-%d8%ab%d8%a8%d8%aa-%d9%86%d8%a7%d9%85-%d9%87%d8%a7/feed/",
            },
            {"type": "rss", "name": "ایسنا اجتماعی", "url": "https://www.isna.ir/rss/tp/9"},
            {"type": "rss", "name": "مهر اجتماعی", "url": "https://www.mehrnews.com/rss/tp/6"},
            {"type": "rss", "name": "خبرآنلاین اجتماعی", "url": "https://www.khabaronline.ir/rss/tp/5"},
        ],
    },
}


def normalize_persian(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u200c", " ")
    text = text.replace("ي", "ی").replace("ك", "ک").replace("ة", "ه")
    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def clean_text_content(raw: str, max_len: int = 240) -> str:
    if not raw:
        return ""
    text = html_lib.unescape(raw)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"@[A-Za-z0-9_]{3,}", "", text)
    text = re.sub(r"https?://(?:t\.me|telegram\.me)/\S+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(ادامه مطلب|بیشتر بخوانید|منبع\s*:.*|انتهای پیام.*|عضویت در کانال.*|لینک کانال.*)", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len] + "..." if len(text) > max_len else text


def is_blocked_url(url: str) -> bool:
    if not url:
        return True
    try:
        host = urlparse(url).netloc.lower()
        return any(domain in host for domain in BLOCKED_LINK_DOMAINS)
    except Exception:
        return True


def extract_official_url(raw_text: str) -> str:
    if not raw_text:
        return ""
    for token in raw_text.split():
        cleaned = token.strip("<>\"'().,،؛!؟]").rstrip(").،؛!؟]")
        if cleaned.startswith(("http://", "https://")) and not is_blocked_url(cleaned):
            return cleaned
    return ""


def detect_portal_url(title: str, summary: str, raw_html: str) -> str:
    explicit = extract_official_url(f"{summary} {raw_html}")
    if explicit:
        return explicit
    norm_text = normalize_persian(f"{title} {summary}")
    for keywords, portal_url in PORTAL_RULES:
        if any(normalize_persian(kw) in norm_text for kw in keywords):
            return portal_url
    return ""


def is_registration_news(title: str, summary: str) -> bool:
    norm_text = normalize_persian(f"{title} {summary}")
    if any(normalize_persian(bad) in norm_text for bad in EXCLUDE_KEYWORDS):
        return False
    return any(normalize_persian(kw) in norm_text for kw in REGISTRATION_KEYWORDS)


def detect_type(title: str, summary: str) -> str:
    norm_text = normalize_persian(f"{title} {summary}")
    if any(k in norm_text for k in ["فوری", "لغو", "تمدید", "هشدار", "پایان مهلت", "آخرین مهلت"]):
        return "alert"
    if any(k in norm_text for k in ["ثبت نام", "نام نویسی", "آغاز", "شروع", "اعلام نتایج", "فراخوان"]):
        return "update"
    return "info"


def make_id(seed: str) -> int:
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def is_duplicate(norm_title: str, seen_titles: set[str]) -> bool:
    if norm_title in seen_titles:
        return True
    words_a = set(norm_title.split())
    if len(words_a) >= 4:
        for existing in seen_titles:
            words_b = set(existing.split())
            if words_b:
                overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
                if overlap >= 0.80:
                    return True
    return False


def load_json_list(path: Path) -> list[dict]:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def parse_telegram_channel(url: str) -> list[dict]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        page_html = resp.read().decode("utf-8", errors="ignore")
    blocks = re.findall(
        r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
        page_html,
        flags=re.DOTALL,
    )
    entries = []
    for raw_block in reversed(blocks[-25:]):
        clean_full = clean_text_content(raw_block, max_len=500)
        if not clean_full or len(clean_full) < 15:
            continue
        first_line_raw = re.split(r"<br\s*/?>|\n|\.", raw_block, maxsplit=1)[0]
        title = clean_text_content(first_line_raw, max_len=115)
        if len(title) < 10:
            title = clean_full[:110] + ("..." if len(clean_full) > 110 else "")
        summary = clean_text_content(raw_block, max_len=240)
        entries.append({
            "title": title,
            "summary": summary,
            "raw_html": raw_block,
        })
    return entries


def fetch_source(section_key: str, source: dict) -> tuple[str, str, list[dict]]:
    try:
        if source.get("type") == "telegram":
            entries = parse_telegram_channel(source["url"])
            return section_key, source["name"], entries
        feed = feedparser.parse(source["url"])
        entries = []
        for e in getattr(feed, "entries", []):
            raw_html = str(e.get("summary", "") or e.get("description", ""))
            entries.append({
                "title": str(e.get("title", "")).strip(),
                "summary": clean_text_content(raw_html, max_len=240),
                "raw_html": raw_html,
            })
        return section_key, source["name"], entries
    except Exception as e:
        print(f"[{section_key}] خطا در {source['name']}: {e}")
        return section_key, source["name"], []


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now_stamp = int(datetime.now().timestamp())
    today_str = datetime.now().strftime("%Y/%m/%d")
    section_items: dict[str, list[dict]] = {}
    seen_ids: dict[str, set[int]] = {}
    global_seen_titles: set[str] = set()
    for sec_key, cfg in SECTIONS.items():
        raw_items = load_json_list(cfg["file"])
        items = []
        for x in raw_items:
            t = clean_text_content(str(x.get("title", "")), max_len=120)
            m = clean_text_content(str(x.get("message", "")), max_len=240)
            if not is_registration_news(t, m):
                continue
            existing_reg = str(x.get("reg_url", "")).strip()
            if not existing_reg or is_blocked_url(existing_reg):
                existing_reg = detect_portal_url(t, m, "")
            cleaned_item = {
                "id": int(x.get("id", make_id(normalize_persian(t)))),
                "type": x.get("type", detect_type(t, m)),
                "title": t,
                "message": m,
                "date": x.get("date", today_str),
                "_order": int(x.get("_order", now_stamp)),
            }
            if existing_reg:
                cleaned_item["reg_url"] = existing_reg
            items.append(cleaned_item)
        section_items[sec_key] = items
        seen_ids[sec_key] = {int(x.get("id", 0)) for x in items}
        global_seen_titles.update(
            normalize_persian(str(x.get("title", ""))) for x in items if x.get("title")
        )
    futures = []
    with ThreadPoolExecutor(max_workers=12) as executor:
        for sec_key, cfg in SECTIONS.items():
            for src in cfg["sources"]:
                futures.append(executor.submit(fetch_source, sec_key, src))
        for idx, fut in enumerate(as_completed(futures)):
            sec_key, src_name, entries = fut.result()
            added = 0
            for entry in entries:
                title = str(entry.get("title", "")).strip()
                summary = str(entry.get("summary", "")).strip()
                raw_html = str(entry.get("raw_html", ""))
                if not title:
                    continue
                if not is_registration_news(title, summary):
                    continue
                norm_title = normalize_persian(title)
                if not norm_title or is_duplicate(norm_title, global_seen_titles):
                    continue
                item_id = make_id(norm_title)
                if item_id in seen_ids[sec_key]:
                    continue
                reg_url = detect_portal_url(title, summary, raw_html)
                item_obj = {
                    "id": item_id,
                    "type": detect_type(title, summary),
                    "title": title,
                    "message": summary or title,
                    "date": today_str,
                    "_order": now_stamp - idx,
                }
                if reg_url:
                    item_obj["reg_url"] = reg_url
                section_items[sec_key].append(item_obj)
                seen_ids[sec_key].add(item_id)
                global_seen_titles.add(norm_title)
                added += 1
            print(f"[{sec_key}] منبع «{src_name}»: {added} اطلاعیه ثبت‌نامی جدید اضافه شد.")
    for sec_key, cfg in SECTIONS.items():
        sorted_sec = sorted(
            section_items[sec_key],
            key=lambda x: int(x.get("_order", x.get("id", 0))),
            reverse=True,
        )[:MAX_ITEMS_PER_SECTION]
        cfg["file"].write_text(
            json.dumps(sorted_sec, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
