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
DEFAULT_SUMMARY_LEN = 750
DEFAULT_FULL_LEN = 1200

CAFENET_CORE_KEYWORDS = [
    "کافی نت", "کافی‌نت", "نرخ خدمات", "تعرفه", "ثبت نام", "ثبتنام",
    "نام نویسی", "پیش ثبت نام", "فراخوان", "تمدید مهلت", "مهلت ثبت",
    "وام", "یارانه", "کالابرگ", "کارت سوخت", "سجام", "سهام عدالت",
    "اظهارنامه", "مالیات", "خودرو", "نوبت دهی", "تعویض پلاک", "گذرنامه",
    "نظام وظیفه", "ابلاغیه", "ثنا", "بیمه", "تامین اجتماعی", "مسکن",
    "نهضت ملی", "سیم کارت", "اینترنت", "پاسپورت", "گواهینامه", "خسارت",
]

EXAMS_CORE_KEYWORDS = [
    "کنکور", "سنجش", "دانشگاه", "دانشجو", "آزمون", "استخدام", "استخدامی",
    "مدرسه", "مدارس", "آموزش و پرورش", "فرهنگیان", "کارشناسی", "ارشد",
    "دکتری", "کارت ورود به جلسه", "اعلام نتایج", "نتایج اولیه", "تراز",
    "انتخاب رشته", "ظرفیت", "فراخوان استخدام", "ثبت نام کنکور", "ثبت نام آزمون",
]

NOTICES_CORE_KEYWORDS = [
    "اطلاعیه", "فراخوان", "ثبت نام", "ثبتنام", "نام نویسی", "تمدید مهلت",
    "مهلت ثبت", "آغاز ثبت", "شروع ثبت", "اعلام نتایج", "وام", "یارانه",
    "کالابرگ", "مالیات", "اظهارنامه", "بیمه", "مسکن", "خودرو", "سجام",
    "سهام عدالت", "نوبت دهی", "ابلاغیه", "ثنا", "کارت سوخت",
]

STRICT_EXCLUDE_KEYWORDS = [
    "قابل توجه همکاران محترم", "ربات های ویژه ثبت نام", "ربات‌های ویژه ثبت نام",
    "مدیریت مغازه یا دفترکار", "هزینه اشتراک ماهانه", "اشتراک ماهانه",
    "انتخابات میان دوره", "انتخابات میان‌دوره", "جمهوری خواهان", "دموکرات",
    "ترامپ", "وزیر خزانه داری", "وزیر خزانه‌داری", "آمریکا", "انگلیس",
    "آمازون", "amazon", "جنگ ایران", "توافق", "دیپلماسی", "سیاست خارجی",
    "تبلیغ", "رپورتاژ", "فال", "طالع", "ورزشی", "فوتبال", "لیگ",
    "آلودگی هوا", "هوای اهواز", "ناوگان تهران", "شورای اسلامی", "فرماندار",
    "گردشگری", "تور", "قرعه کشی تلگرام", "پروکسی", "فیلترشکن",
]

BLOCKED_LINK_DOMAINS = (
    "isna.ir", "mehrnews.com", "tasnimnews.ir", "khabaronline.ir",
    "onlinecofe.ir", "cafeneti.com", "cofeeenet.ir", "farsnews.ir",
    "irna.ir", "yjc.ir", "tabnak.ir", "entekhab.ir", "asriran.com",
    "t.me", "telegram.me", "telegram.org", "eitaa.com", "rubika.ir",
    "ble.ir", "instagram.com", "eestekhdam.com", "e-estekhdam.com",
)

PORTAL_RULES = [
    (["کنکور", "سنجش", "پزشکی", "آزمون استخدامی", "تخصصی", "دکتری", "کارشناسی ارشد", "کارت ورود به جلسه", "اعلام نتایج"], "https://my.sanjesh.org"),
    (["آموزش و پرورش", "مدارس", "مای مدیو", "my.medu"], "https://my.medu.ir"),
    (["یارانه", "کالابرگ", "حمایتی"], "https://hemayat.mcls.gov.ir"),
    (["سجام"], "https://www.sejam.ir"),
    (["سهام عدالت"], "https://www.sahamedalat.ir"),
    (["مالیات", "اظهارنامه", "مودیان", "مالیاتی", "استرداد مالیات"], "https://my.tax.gov.ir"),
    (["کارت سوخت", "سوخت"], "https://fcp.niopdc.ir"),
    (["خودرو", "یکپارچه خودرو", "فروش خودرو", "تعویض پلاک", "اسقاط"], "https://esale.ikco.ir"),
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


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) - 80 + gd + g_d_m[gm - 1]
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def get_today_jalali_str(dt: datetime | None = None) -> str:
    now = dt or datetime.now()
    jy, jm, jd = gregorian_to_jalali(now.year, now.month, now.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d}"


def normalize_date_to_jalali(date_str: str, fallback_str: str) -> str:
    if not date_str:
        return fallback_str
    cleaned = date_str.strip()
    m = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", cleaned)
    if not m:
        return fallback_str
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if 1800 <= y <= 2200:
        jy, jm, jd = gregorian_to_jalali(y, mo, d)
        return f"{jy:04d}/{jm:02d}/{jd:02d}"
    if 1300 <= y <= 1500:
        return f"{y:04d}/{mo:02d}/{d:02d}"
    return fallback_str


def normalize_persian(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u200c", " ")
    text = text.replace("ي", "ی").replace("ك", "ک").replace("ة", "ه")
    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def clean_text_content(raw: str, max_len: int = DEFAULT_SUMMARY_LEN, strip_links_and_tags_text: bool = False) -> str:
    if not raw:
        return ""
    text = html_lib.unescape(raw)
    text = re.sub(r"<i\b[^>]*>.*?</i>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<i\b[^>]*>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"</i\s*>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"class\s*=\s*[\"']?emoji[\"']?[^>]*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"style\s*=\s*[\"']?background-image\s*:[^\"']*\)?", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"background-image\s*:\s*url\([^)]*\)?", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"@[A-Za-z0-9_]{3,}", "", text)
    text = re.sub(r"https?://(?:t\.me|telegram\.me)/\S+", "", text, flags=re.IGNORECASE)
    if strip_links_and_tags_text:
        text = re.sub(r"(?:https?://)?(?:www\.)?[a-z0-9-]+\.[a-z]{2,}(?:/\S*)?", "", text, flags=re.IGNORECASE)
        text = text.replace("#", " ")
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
    action_words = ["ثبت نام", "ثبتنام", "نام نویسی", "دریافت کارت", "کارت ورود به جلسه", "اعلام نتایج", "فراخوان", "اظهارنامه", "نوبت دهی", "وام", "یارانه", "کالابرگ", "سجام", "سهام عدالت", "کارت سوخت", "ابلاغیه", "ثنا"]
    if not any(normalize_persian(aw) in norm_text for aw in action_words):
        return ""
    for keywords, portal_url in PORTAL_RULES:
        if any(normalize_persian(kw) in norm_text for kw in keywords):
            return portal_url
    return ""


def is_section_relevant(section_key: str, title: str, summary: str) -> bool:
    norm_text = normalize_persian(f"{title} {summary}")
    if not norm_text:
        return False
    if any(normalize_persian(bad) in norm_text for bad in STRICT_EXCLUDE_KEYWORDS):
        return False
    if section_key == "cafenet":
        return any(normalize_persian(kw) in norm_text for kw in CAFENET_CORE_KEYWORDS)
    if section_key == "exams":
        return any(normalize_persian(kw) in norm_text for kw in EXAMS_CORE_KEYWORDS)
    if section_key == "notices":
        return any(normalize_persian(kw) in norm_text for kw in NOTICES_CORE_KEYWORDS)
    return False


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


def build_clean_title_and_summary(raw_block: str, is_estekhdam: bool = False) -> tuple[str, str, str]:
    clean_full = clean_text_content(raw_block, max_len=DEFAULT_FULL_LEN, strip_links_and_tags_text=is_estekhdam)
    if not clean_full or len(clean_full) < 15:
        return "", "", ""
    parts = re.split(r"<br\s*/?>|\n", raw_block)
    cleaned_parts = [
        clean_text_content(p, max_len=160, strip_links_and_tags_text=is_estekhdam)
        for p in parts
    ]
    cleaned_parts = [p for p in cleaned_parts if p and len(p) >= 6 and not p.startswith(("<i", "class=", "style="))]
    title = cleaned_parts[0] if cleaned_parts else clean_full[:115]
    if len(title) > 120:
        title = title[:117] + "..."
    summary = clean_text_content(raw_block, max_len=DEFAULT_SUMMARY_LEN, strip_links_and_tags_text=is_estekhdam)
    return title, summary, clean_full


def parse_telegram_channel(url: str) -> list[dict]:
    is_estekhdam = "eestekhdam" in url.lower()
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
        title, summary, full_text = build_clean_title_and_summary(raw_block, is_estekhdam=is_estekhdam)
        if not title or not summary:
            continue
        entries.append({
            "title": title,
            "summary": summary,
            "full_text": full_text,
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
            raw_html = str(e.get("summary", "") or e.get("description", "") or e.get("content", [{}])[0].get("value", "") if isinstance(e.get("content"), list) and e.get("content") else (e.get("summary", "") or e.get("description", "")))
            title_clean = clean_text_content(str(e.get("title", "")), max_len=130)
            summary_clean = clean_text_content(raw_html, max_len=DEFAULT_SUMMARY_LEN)
            full_clean = clean_text_content(raw_html, max_len=DEFAULT_FULL_LEN)
            entries.append({
                "title": title_clean,
                "summary": summary_clean,
                "full_text": full_clean,
                "raw_html": raw_html,
            })
        return section_key, source["name"], entries
    except Exception as e:
        print(f"[{section_key}] خطا در {source['name']}: {e}")
        return section_key, source["name"], []


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now_dt = datetime.now()
    now_stamp = int(now_dt.timestamp())
    today_jalali = get_today_jalali_str(now_dt)
    section_items: dict[str, list[dict]] = {}
    seen_ids: dict[str, set[int]] = {}
    global_seen_titles: set[str] = set()
    for sec_key, cfg in SECTIONS.items():
        raw_items = load_json_list(cfg["file"])
        items = []
        for x in raw_items:
            t = clean_text_content(str(x.get("title", "")), max_len=130)
            raw_msg = str(x.get("full_text") or x.get("message") or "")
            is_est = ("e-estekhdam" in raw_msg.lower()) or ("eestekhdam" in raw_msg.lower())
            m = clean_text_content(raw_msg, max_len=DEFAULT_SUMMARY_LEN, strip_links_and_tags_text=is_est)
            if not is_section_relevant(sec_key, t, m):
                continue
            existing_reg = str(x.get("reg_url", "")).strip()
            if not existing_reg or is_blocked_url(existing_reg):
                existing_reg = detect_portal_url(t, m, "")
            item_date = normalize_date_to_jalali(str(x.get("date", "")), today_jalali)
            cleaned_item = {
                "id": int(x.get("id", make_id(normalize_persian(t)))),
                "type": x.get("type", detect_type(t, m)),
                "title": t,
                "message": m,
                "full_text": clean_text_content(raw_msg, max_len=DEFAULT_FULL_LEN, strip_links_and_tags_text=is_est),
                "date": item_date,
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
                is_est = "e-estekhdam" in (src_name.lower() + " " + str(entry.get("summary", "")).lower())
                title = clean_text_content(str(entry.get("title", "")), max_len=130, strip_links_and_tags_text=is_est)
                summary = clean_text_content(str(entry.get("summary", "")), max_len=DEFAULT_SUMMARY_LEN, strip_links_and_tags_text=is_est)
                full_text = clean_text_content(str(entry.get("full_text") or summary), max_len=DEFAULT_FULL_LEN, strip_links_and_tags_text=is_est)
                raw_html = str(entry.get("raw_html", ""))
                if not title:
                    continue
                if not is_section_relevant(sec_key, title, summary):
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
                    "full_text": full_text or summary or title,
                    "date": today_jalali,
                    "_order": now_stamp - idx,
                }
                if reg_url:
                    item_obj["reg_url"] = reg_url
                section_items[sec_key].append(item_obj)
                seen_ids[sec_key].add(item_id)
                global_seen_titles.add(norm_title)
                added += 1
            print(f"[{sec_key}] منبع «{src_name}»: {added} اطلاعیه مرتبط جدید اضافه شد.")
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
