from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import feedparser

DATA_DIR = Path("data")
MAX_ITEMS_PER_SECTION = 40

# کلمات کلیدی اختصاصی برای استخراج صرف اخبار ثبت‌نامی و خدمات کافی‌نت
REGISTRATION_KEYWORDS = [
    "ثبت نام",
    "ثبتنام",
    "نام نویسی",
    "پیش ثبت نام",
    "فراخوان",
    "تمدید مهلت",
    "مهلت ثبت",
    "مهلت نام نویسی",
    "آغاز ثبت",
    "شروع ثبت",
    "زمان ثبت",
    "نحوه ثبت",
    "سامانه ثبت",
    "دریافت کارت",
    "کارت ورود به جلسه",
    "ویرایش اطلاعات",
    "تکمیل ظرفیت",
    "اعلام نتایج",
    "نتایج اولیه",
    "آزمون استخدامی",
    "استخدام",
    "کنکور",
    "وام",
    "یارانه",
    "کالابرگ",
    "کارت سوخت",
    "سجام",
    "سهام عدالت",
    "اظهارنامه",
    "خودرو",
    "حج",
    "عتبات",
    "نوبت دهی",
    "تعویض پلاک",
    "گذرنامه",
    "نظام وظیفه",
]

EXCLUDE_KEYWORDS = [
    "تبلیغ",
    "رپورتاژ",
    "فال",
    "طالع",
    "ورزشی",
    "فوتبال",
]

# دامنه‌های خبرگزاری‌ها و سایت‌های واسط که نباید به عنوان لینک ثبت‌نام استفاده شوند
NEWS_AGENCY_DOMAINS = (
    "isna.ir",
    "mehrnews.com",
    "tasnimnews.ir",
    "khabaronline.ir",
    "onlinecofe.ir",
    "cafeneti.com",
    "cofeeenet.ir",
    "farsnews.ir",
    "irna.ir",
    "yjc.ir",
    "tabnak.ir",
    "entekhab.ir",
    "asriran.com",
)

# تشخیص خودکار لینک مستقیم سامانه‌های رسمی ثبت‌نام بر اساس موضوع خبر
PORTAL_RULES = [
    (["کنکور", "سنجش", "پزشکی", "آزمون استخدامی", "تخصصی", "دکتری", "کارشناسی ارشد", "کارت ورود به جلسه", "اعلام نتایج"], "https://my.sanjesh.org"),
    (["آموزش و پرورش", "مدارس", "مای مدیو", "my.medu"], "https://my.medu.ir"),
    (["یارانه", "کالابرگ", "حمایتی"], "https://hemayat.mcls.gov.ir"),
    (["سجام"], "https://www.sejam.ir"),
    (["سهام عدالت"], "https://www.sahamedalat.ir"),
    (["مالیات", "اظهارنامه", "مودیان"], "https://my.tax.gov.ir"),
    (["کارت سوخت", "سوخت"], "https://fcp.niopdc.ir"),
    (["خودرو", "یکپارچه خودرو", "فروش خودرو", "تعویض پلاک"], "https://esale.ikco.ir"),
    (["گذرنامه", "نظام وظیفه", "سخا", "پلیس من"], "https://sakha.epolice.ir"),
    (["حج", "عتبات", "عمره"], "https://my.haj.ir"),
    (["ثبت احوال", "شناسنامه", "کارت ملی"], "https://ncr.ir"),
]

SECTIONS = {
    "cafenet": {
        "file": DATA_DIR / "cafenet.json",
        "sources": [
            {"name": "دستیار کافی‌نت", "url": "https://onlinecofe.ir/news/feed/"},
            {"name": "کافی نتی", "url": "https://cafeneti.com/feed/"},
            {"name": "کافی نت آنلاین", "url": "https://cofeeenet.ir/feed/"},
            {"name": "تسنیم اقتصادی", "url": "https://www.tasnimnews.ir/fa/rss/feed/0/8/7"},
            {"name": "تسنیم اجتماعی", "url": "https://www.tasnimnews.ir/fa/rss/feed/0/8/2"},
            {"name": "مهر اقتصادی", "url": "https://www.mehrnews.com/rss/tp/25"},
            {"name": "ایسنا اقتصادی", "url": "https://www.isna.ir/rss/tp/34"},
            {"name": "خبرآنلاین اقتصادی", "url": "https://www.khabaronline.ir/rss/tp/2"},
        ],
    },
    "exams": {
        "file": DATA_DIR / "exams.json",
        "sources": [
            {"name": "ایسنا آموزش", "url": "https://www.isna.ir/rss/tp/390"},
            {"name": "ایسنا آموزش و پرورش", "url": "https://www.isna.ir/rss/tp/59"},
            {"name": "مهر دانشجویی", "url": "https://www.mehrnews.com/rss/tp/178"},
            {"name": "خبرآنلاین آموزش", "url": "https://www.khabaronline.ir/rss/tp/43"},
            {"name": "تسنیم آموزش", "url": "https://www.tasnimnews.ir/fa/rss/feed/0/8/22"},
        ],
    },
    "notices": {
        "file": DATA_DIR / "notices.json",
        "sources": [
            {
                "name": "کافی نت آنلاین ثبت‌نام‌ها",
                "url": "https://cofeeenet.ir/category/%d8%a7%d8%ae%d8%a8%d8%a7%d8%b1-%d8%ab%d8%a8%d8%aa-%d9%86%d8%a7%d9%85-%d9%87%d8%a7/feed/",
            },
            {"name": "ایسنا اجتماعی", "url": "https://www.isna.ir/rss/tp/9"},
            {"name": "مهر اجتماعی", "url": "https://www.mehrnews.com/rss/tp/6"},
            {"name": "خبرآنلاین اجتماعی", "url": "https://www.khabaronline.ir/rss/tp/5"},
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


def clean_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    # حذف عبارات تبلیغاتی انتهای فیدها مثل «ادامه مطلب» یا «مشاهده در سایت...»
    text = re.sub(r"(ادامه مطلب|بیشتر بخوانید|منبع\s*:.*|انتهای پیام.*)", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:230] + "..." if len(text) > 230 else text


def is_news_agency_url(url: str) -> bool:
    if not url:
        return True
    try:
        host = urlparse(url).netloc.lower()
        return any(domain in host for domain in NEWS_AGENCY_DOMAINS)
    except Exception:
        return True


def extract_official_url(raw_text: str) -> str:
    """استخراج لینک‌های غیراز خبرگزاری‌ها از متن خبر (مثل سامانه‌های .ir یا .org دولتی)"""
    if not raw_text:
        return ""
    urls = re.findall(r"https?://[^\s<>"']+", raw_text)
    for u in urls:
        cleaned = u.rstrip(").،؛!؟]")
        if not is_news_agency_url(cleaned):
            return cleaned
    return ""


def detect_portal_url(title: str, summary: str, raw_html: str) -> str:
    """برگرداندن صرفاً لینک سامانه رسمی ثبت‌نام؛ در صورت نبودن، رشته خالی برمی‌گرداند"""
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


def fetch_source(section_key: str, source: dict) -> tuple[str, str, list[dict]]:
    try:
        feed = feedparser.parse(source["url"])
        entries = list(getattr(feed, "entries", []))
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
            t = str(x.get("title", ""))
            m = str(x.get("message", ""))
            if not is_registration_news(t, m):
                continue

            # حذف کامل نام منبع و لینک خبرگزاری از آیتم‌های قبلی
            x.pop("source", None)
            x.pop("url", None)

            existing_reg = str(x.get("reg_url", "")).strip()
            if not existing_reg or is_news_agency_url(existing_reg):
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
    with ThreadPoolExecutor(max_workers=10) as executor:
        for sec_key, cfg in SECTIONS.items():
            for src in cfg["sources"]:
                futures.append(executor.submit(fetch_source, sec_key, src))

        for idx, fut in enumerate(as_completed(futures)):
            sec_key, src_name, entries = fut.result()
            added = 0

            for entry in entries:
                title = str(entry.get("title", "")).strip()
                raw_html = str(entry.get("summary", "") or entry.get("description", ""))
                summary = clean_html(raw_html)

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
