from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
import feedparser

DATA_DIR = Path("data")
MAX_ITEMS_PER_SECTION = 30

# کلمات کلیدی اجباری برای اینکه فقط اخبار مرتبط با ثبت‌نام‌ها و خدمات ثبت‌نامی برداشته شوند
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
]

# کلمات منفی: اگر خبری این کلمات را داشت حتی با کلمات بالا رد شود
EXCLUDE_KEYWORDS = [
    "تبلیغ",
    "رپورتاژ",
    "فال",
    "طالع",
    "ورزشی",
    "فوتبال",
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
        ],
    },
    "exams": {
        "file": DATA_DIR / "exams.json",
        "sources": [
            {"name": "ایسنا آموزش", "url": "https://www.isna.ir/rss/tp/390"},
            {"name": "ایسنا آموزش و پرورش", "url": "https://www.isna.ir/rss/tp/59"},
            {"name": "مهر دانشجویی", "url": "https://www.mehrnews.com/rss/tp/178"},
            {"name": "خبرآنلاین آموزش", "url": "https://www.khabaronline.ir/rss/tp/43"},
        ],
    },
    "notices": {
        "file": DATA_DIR / "notices.json",
        "sources": [
            {
                "name": "کافی نت آنلاین - ثبت‌نام‌ها",
                "url": "https://cofeeenet.ir/category/%d8%a7%d8%ae%d8%a8%d8%a7%d8%b1-%d8%ab%d8%a8%d8%aa-%d9%86%d8%a7%d9%85-%d9%87%d8%a7/feed/",
            },
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
    text = re.sub(r"\s+", " ", text).strip()
    return text[:200] + "..." if len(text) > 200 else text


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


def is_duplicate(norm_title: str, norm_link: str, seen_urls: set[str], seen_titles: set[str]) -> bool:
    if norm_link and norm_link in seen_urls:
        return True
    if norm_title in seen_titles:
        return True

    words_a = set(norm_title.split())
    if len(words_a) >= 4:
        for existing in seen_titles:
            words_b = set(existing.split())
            if words_b:
                overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
                if overlap >= 0.85:
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
    seen_urls: dict[str, set[str]] = {}
    seen_titles: dict[str, set[str]] = {}

    for sec_key, cfg in SECTIONS.items():
        raw_items = load_json_list(cfg["file"])
        items = [
            x for x in raw_items
            if is_registration_news(str(x.get("title", "")), str(x.get("message", "")))
        ]
        section_items[sec_key] = items
        seen_ids[sec_key] = {int(x.get("id", 0)) for x in items}
        seen_urls[sec_key] = {str(x.get("url", "")).strip().lower() for x in items if x.get("url")}
        seen_titles[sec_key] = {normalize_persian(str(x.get("title", ""))) for x in items if x.get("title")}

    futures = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        for sec_key, cfg in SECTIONS.items():
            for src in cfg["sources"]:
                futures.append(executor.submit(fetch_source, sec_key, src))

        for idx, fut in enumerate(as_completed(futures)):
            sec_key, src_name, entries = fut.result()
            added = 0
            skipped_irrelevant = 0

            for entry in entries:
                title = str(entry.get("title", "")).strip()
                link = str(entry.get("link", "")).strip()
                summary = clean_html(str(entry.get("summary", "") or entry.get("description", "")))

                if not title:
                    continue

                if not is_registration_news(title, summary):
                    skipped_irrelevant += 1
                    continue

                norm_title = normalize_persian(title)
                norm_link = link.lower()

                if is_duplicate(norm_title, norm_link, seen_urls[sec_key], seen_titles[sec_key]):
                    continue

                item_id = make_id(f"{sec_key}:{norm_title or norm_link}")
                if item_id in seen_ids[sec_key]:
                    continue

                section_items[sec_key].append({
                    "id": item_id,
                    "type": detect_type(title, summary),
                    "source": src_name,
                    "title": title,
                    "message": summary or "برای مشاهده جزئیات روی لینک کلیک کنید.",
                    "date": today_str,
                    "url": link,
                    "_order": now_stamp - idx,
                })

                seen_ids[sec_key].add(item_id)
                if norm_link:
                    seen_urls[sec_key].add(norm_link)
                seen_titles[sec_key].add(norm_title)
                added += 1

            print(f"[{sec_key}] منبع «{src_name}»: {added} ثبت‌نامی جدید | {skipped_irrelevant} غیرمرتبط رد شد.")

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
