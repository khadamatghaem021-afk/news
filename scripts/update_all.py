from concurrent.futures import ThreadPoolExecutor, as_completed
import calendar
import hashlib
import html as html_lib
import json
import math
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
import urllib.request
import feedparser

IRAN_TZ = timezone(timedelta(hours=3, minutes=30))

DATA_DIR = Path("data")
PAGE_SIZE = 5
MAX_PAGES = 8
MAX_ITEMS_PER_SECTION = PAGE_SIZE * MAX_PAGES  # ۴۰ خبر در ۸ صفحه ۵تایی
DEFAULT_SUMMARY_LEN = 750
DEFAULT_FULL_LEN = 1200

# کلمات کلیدی هر بخش (بدون خبرگزاری‌های عمومی - فقط تلگرام‌های تخصصی و سایت‌های مرجع کافی‌نت)
CAFENET_CORE_KEYWORDS = [
    "کافی نت", "کافی‌نت", "نرخ خدمات", "تعرفه", "ثبت نام", "ثبتنام",
    "نام نویسی", "پیش ثبت نام", "فراخوان", "تمدید مهلت", "مهلت ثبت",
    "وام", "یارانه", "کالابرگ", "کارت سوخت", "سجام", "سهام عدالت",
    "اظهارنامه", "مالیات", "نوبت دهی", "تعویض پلاک", "گذرنامه",
    "نظام وظیفه", "ابلاغیه", "ثنا", "بیمه", "تامین اجتماعی", "مسکن",
    "نهضت ملی", "سیم کارت", "اینترنت", "پاسپورت", "گواهینامه", "خسارت",
    "اطلاعیه", "سامانه", "درگاه", "حساب", "بانک", "پرداخت", "مهلت",
]

CARS_CORE_KEYWORDS = [
    "خودرو", "ایران خودرو", "ایران‌خودرو", "سایپا", "پارس خودرو",
    "بهمن موتور", "مدیران خودرو", "کرمان موتور", "فروش فوری", "پیش فروش",
    "فروش فوق العاده", "فروش فوق‌العاده", "یکپارچه", "قرعه کشی", "قرعه‌کشی",
    "ثبت نام خودرو", "بخشنامه فروش", "مادران", "جوانی جمعیت", "فرسوده",
    "اسقاط", "وارداتی", "ثبت نام", "ثبتنام", "تحویل خودرو", "تکمیل وجه",
    "وکالتی", "حساب وکالتی", "قیمت کارخانه", "ایرانخودرو", "ساینا", "کوییک",
    "تارا", "دنا", "پژو", "رانا", "سورن", "شاهین", "اطلس", "سهند",
]

EXAMS_ACTION_OR_EXAM_KEYWORDS = [
    "ثبت نام", "ثبتنام", "نام نویسی", "پیش ثبت نام", "تمدید مهلت", "مهلت ثبت",
    "آغاز ثبت", "شروع ثبت", "فراخوان", "کنکور", "سنجش", "آزمون", "استخدام",
    "استخدامی", "کارت ورود به جلسه", "اعلام نتایج", "نتایج اولیه", "نتایج نهایی",
    "تراز", "انتخاب رشته", "ظرفیت", "دفترچه", "کارنامه", "مهمانی", "انتقال",
    "اطلاعیه", "پذیرش", "مصاحبه", "امتیاز", "دعوت به همکاری", "آگهی",
    "امتحانات", "امتحان", "نهایی", "مدارس", "مدرسه", "معلم", "فرهنگیان",
    "مای مدیو", "سیدا", "شاد", "هدایت تحصیلی", "سمپاد", "تیزهوشان", "نمونه دولتی",
]

EXAMS_SUBJECT_KEYWORDS = [
    "کنکور", "سنجش", "آزمون", "استخدام", "استخدامی", "دانشگاه", "دانشجو",
    "فرهنگیان", "آموزش و پرورش", "کارشناسی", "ارشد", "دکتری", "ثبت نام",
    "وزارت علوم", "وزارت بهداشت", "فنی و حرفه ای", "فنی و حرفه‌ای", "علمی کاربردی",
    "آزاد اسلامی", "پیام نور", "داوطلب", "تحصیلی", "مدرسه", "مدارس", "دانش آموز",
    "دانش‌آموز", "معلم", "فرهنگیان", "تربیت معلم", "مای مدیو", "سیدا",
]

EXAMS_EXCLUDE_KEYWORDS = [
    "استقبال از نودانشجویان", "نودانشجویان", "روز دانشجو",
    "پست الکترونیکی من", "مدال های", "مدال‌های", "المپیاد",
    "شورای صنفی", "بسیج دانشجویی", "تغذیه دانشجویی",
]

NOTICES_CORE_KEYWORDS = [
    "اطلاعیه", "فراخوان", "ثبت نام", "ثبتنام", "نام نویسی", "تمدید مهلت",
    "مهلت ثبت", "آغاز ثبت", "شروع ثبت", "اعلام نتایج", "وام", "یارانه",
    "کالابرگ", "مالیات", "اظهارنامه", "بیمه", "مسکن", "خودرو", "سجام",
    "سهام عدالت", "نوبت دهی", "ابلاغیه", "ثنا", "کارت سوخت", "سامانه",
    "بخشنامه", "دستورالعمل", "پرداخت", "حمایتی", "بازنشسته",
]

# کلماتی که خبر را واجد شرایط بخش «خبرهای مهم» می‌کنند
IMPORTANT_KEYWORDS = [
    "فوری", "مهم", "تمدید مهلت", "آخرین مهلت", "پایان مهلت", "لغو",
    "آغاز ثبت نام", "شروع ثبت نام", "اعلام نتایج", "کارت ورود به جلسه",
    "حساب وکالتی", "فروش فوری", "فروش فوق العاده", "پیش فروش", "یکپارچه خودرو",
    "کالابرگ", "یارانه", "سهام عدالت", "ابلاغیه", "مالیات", "اظهارنامه",
    "نرخ خدمات", "تعرفه", "امتحان نهایی", "مای مدیو", "کنکور", "استخدامی",
    "هشدار", "اطلاعیه مهم", "تغییر زمان", "اصلاحیه",
]

# فیلتر سخت‌گیرانه تبلیغات، رپورتاژ، تخفیف، فروش کالا/خدمات تجاری و لینک‌های غیررسمی
STRICT_EXCLUDE_KEYWORDS = [
    "قابل توجه همکاران محترم", "ربات های ویژه ثبت نام", "ربات‌های ویژه ثبت نام",
    "مدیریت مغازه یا دفترکار", "هزینه اشتراک ماهانه", "اشتراک ماهانه",
    "تبلیغ", "تبلیغات", "رپورتاژ", "آگهی ویژه", "تخفیف ویژه", "کد تخفیف",
    "فال", "طالع", "قرعه کشی تلگرام", "قرعه‌کشی تلگرام", "پروکسی", "فیلترشکن",
    "خرید مستقیم", "خرید اقساطی", "فروش ویژه", "حراج", "تعداد محدود",
    "همکاری با ما", "کسب درآمد", "بازاریابی", "پورسانت", "گروه تلگرامی",
    "کانال تلگرامی", "لینک گروه", "لینک کانال", "عضویت در گروه",
]

BLOCKED_LINK_DOMAINS = (
    "isna.ir", "mehrnews.com", "tasnimnews.ir", "khabaronline.ir",
    "onlinecofe.ir", "cafeneti.com", "cofeeenet.ir", "farsnews.ir",
    "irna.ir", "yjc.ir", "tabnak.ir", "entekhab.ir", "asriran.com",
    "t.me", "telegram.me", "telegram.org", "eitaa.com", "rubika.ir",
    "ble.ir", "instagram.com", "eestekhdam.com", "e-estekhdam.com",
    "divar.ir", "sheypoor.com", "digikala.com", "torob.com", "emalls.ir",
)

# قوانین دقیق تشخیص شرکت/سامانه خودرویی متناسب با متن خبر
CAR_PORTAL_RULES = [
    (["ایران خودرو", "ایران‌خودرو", "ایرانخودرو", "ikco", "تارا", "دنا", "پژو", "رانا", "سورن", "هایما"], "https://esale.ikco.ir"),
    (["سایپا", "پارس خودرو", "پارس‌خودرو", "saipa", "شاهین", "کوییک", "ساینا", "اطلس", "سهند", "آریا"], "https://saipa.iranecar.com"),
    (["بهمن موتور", "بهمن‌موتور", "bahman", "فیدلیتی", "دیگنیتی", "رسپکت", "کاپرا"], "https://bahman.iranecar.com"),
    (["کرمان موتور", "کرمان‌موتور", "kermanmotor", "جک", "کی ام سی", "kma", "x55", "j7"], "https://customer.kermanmotor.com"),
    (["مدیران خودرو", "mvm", "فونیکس", "fownix", "تیگو", "آریزو", "ایکس"], "https://mvm.iranecar.com"),
    (["وارداتی", "جانبازان", "خودرو وارداتی"], "https://salecars.ir"),
    (["فرسوده", "اسقاط", "نوسازی خودرو"], "https://nnhk.ir"),
    (["تعویض پلاک"], "https://nobatdehi.epolice.ir"),
]

PORTAL_RULES = [
    (["کنکور", "سنجش", "پزشکی", "آزمون استخدامی", "تخصصی", "دکتری", "کارشناسی ارشد", "کارت ورود به جلسه", "اعلام نتایج"], "https://my.sanjesh.org"),
    (["آموزش و پرورش", "مدارس", "مای مدیو", "my.medu", "سیدا", "هدایت تحصیلی"], "https://my.medu.ir"),
    (["یارانه", "کالابرگ", "حمایتی"], "https://hemayat.mcls.gov.ir"),
    (["سجام"], "https://www.sejam.ir"),
    (["سهام عدالت"], "https://www.sahamedalat.ir"),
    (["مالیات", "اظهارنامه", "مودیان", "مالیاتی", "استرداد مالیات"], "https://my.tax.gov.ir"),
    (["کارت سوخت", "سوخت"], "https://fcp.niopdc.ir"),
    (["گذرنامه", "نظام وظیفه", "سخا", "پلیس من"], "https://sakha.epolice.ir"),
    (["حج", "عتبات", "عمره"], "https://my.haj.ir"),
    (["ثبت احوال", "شناسنامه", "کارت ملی"], "https://ncr.ir"),
    (["ثنا", "ابلاغیه", "قوه قضاییه", "عدل ایران"], "https://adliran.ir"),
]

SECTIONS = {
    "important": {
        "file": DATA_DIR / "important.json",
        "sources": [],
    },
    "cafenet": {
        "file": DATA_DIR / "cafenet.json",
        "sources": [
            {"type": "telegram", "name": "تلگرام کافی‌نت منیجر", "url": "https://t.me/s/CoffeenetManager"},
            {"type": "telegram", "name": "تلگرام اخبار کافی‌نت", "url": "https://t.me/s/akhbar_cafenet"},
            {"type": "telegram", "name": "تلگرام نرخ‌نامه", "url": "https://t.me/s/nerkh_net"},
            {"type": "telegram", "name": "تلگرام ارتباط با ادمین‌ها", "url": "https://t.me/s/ertebat_ba_adminhaa2"},
            {"type": "rss", "name": "دستیار کافی‌نت", "url": "https://onlinecofe.ir/news/feed/"},
            {"type": "rss", "name": "کافی نتی", "url": "https://cafeneti.com/feed/"},
            {"type": "rss", "name": "کافی نت آنلاین", "url": "https://cofeeenet.ir/feed/"},
        ],
    },
    "cars": {
        "file": DATA_DIR / "cars.json",
        "sources": [
            {"type": "telegram", "name": "تلگرام ثبت‌نام خودرو", "url": "https://t.me/s/sabtnamkh0dro"},
        ],
    },
    "exams": {
        "file": DATA_DIR / "exams.json",
        "sources": [
            {"type": "telegram", "name": "تلگرام اخبار آموزش و پرورش", "url": "https://t.me/s/madaras_da"},
            {"type": "telegram", "name": "تلگرام استخدامی", "url": "https://t.me/s/eestekhdam_com"},
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
        ],
    },
}

CHANNEL_TAG_PHRASES = [
    "کانال نرخنامه و اخبار کافی نت",
    "کانال نرخنامه و اخبار کافی‌نت",
    "نرخنامه و اخبار کافی نت",
    "نرخنامه و اخبار کافی‌نت",
    "اخبار کافی نت کشوری",
    "اخبار کافی‌نت کشوری",
    "کانال اخبار کافی نت",
    "کانال اخبار کافی‌نت",
    "کانال نرخ نامه",
    "کانال نرخنامه",
    "کانال استخدامی",
    "کانال استخدام",
    "کانال مالیاتی",
    "کانال مالیات",
    "لطفا به اشتراک بگذارید",
    "لطفاً به اشتراک بگذارید",
    "به اشتراک بگذارید",
]

PERSIAN_MONTHS = {
    "فروردین": 1, "اردیبهشت": 2, "خرداد": 3,
    "تیر": 4, "مرداد": 5, "شهریور": 6,
    "مهر": 7, "آبان": 8, "آذر": 9,
    "دی": 10, "بهمن": 11, "اسفند": 12,
}

MAX_STALE_DAYS = 14  # خبرهای قدیمی‌تر از ۱۴ روز به عنوان خبر جدید پذیرفته نمی‌شوند


def get_iran_now(dt: datetime | None = None) -> datetime:
    base = dt or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base.astimezone(IRAN_TZ)


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


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    if jy > 979:
        gy = 1600
        jy -= 979
    else:
        gy = 621
    days = (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + 78 + jd + (
        (jm - 1) * 31 if jm < 7 else ((jm - 7) * 30) + 186
    )
    gy += 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        gy += 100 * ((days - 1) // 36524)
        days = (days - 1) % 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    for gm, month_len in enumerate([31, 29 if (gy % 4 == 0 and (gy % 100 != 0 or gy % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31], start=1):
        if gd <= month_len:
            return gy, gm, gd
        gd -= month_len
    return gy, 12, gd


def jalali_str_to_ts(jalali_str: str, fallback_ts: int) -> int:
    m = re.match(r"^(\d{4})/(\d{2})/(\d{2})$", jalali_str or "")
    if not m:
        return fallback_ts
    jy, jm, jd = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1300 <= jy <= 1500 and 1 <= jm <= 12 and 1 <= jd <= 31):
        return fallback_ts
    try:
        gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
        dt_ir = datetime(gy, gm, gd, 12, 0, 0, tzinfo=IRAN_TZ)
        return int(dt_ir.timestamp())
    except Exception:
        return fallback_ts


def get_today_jalali_str(dt: datetime | None = None) -> str:
    now_ir = get_iran_now(dt)
    jy, jm, jd = gregorian_to_jalali(now_ir.year, now_ir.month, now_ir.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d}"


def _persian_digits_to_latin(s: str) -> str:
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return s.translate(trans)


def datetime_to_iran_jalali_and_ts(dt_obj: datetime, fallback_ts: int) -> tuple[str, int]:
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=timezone.utc)
    ir_dt = dt_obj.astimezone(IRAN_TZ)
    jy, jm, jd = gregorian_to_jalali(ir_dt.year, ir_dt.month, ir_dt.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d}", int(ir_dt.timestamp())


def extract_text_embedded_jalali(text: str, current_jalali: str, fallback_ts: int) -> tuple[str, int]:
    """بررسی تاریخ‌های ذکرشده داخل متن خبر (مثل ۱۴۰۴/۰۸/۱۲ یا ۱۲ آبان ۱۴۰۴ یا تا ۱۵ آذر)"""
    if not text:
        return "", fallback_ts
    lat = _persian_digits_to_latin(text)
    cur_y = int(current_jalali.split("/")[0]) if "/" in current_jalali else 1404
    cur_m = int(current_jalali.split("/")[1]) if "/" in current_jalali else 1

    m_full = re.search(r"\b(13\d{2}|14\d{2})[/-](\d{1,2})[/-](\d{1,2})\b", lat)
    if m_full:
        jy, jm, jd = int(m_full.group(1)), int(m_full.group(2)), int(m_full.group(3))
        if 1 <= jm <= 12 and 1 <= jd <= 31:
            j_str = f"{jy:04d}/{jm:02d}/{jd:02d}"
            return j_str, jalali_str_to_ts(j_str, fallback_ts)

    for m_name, m_num in PERSIAN_MONTHS.items():
        pat = rf"\b(\d{{1,2}})\s+{re.escape(m_name)}(?:\s+(13\d{{2}}|14\d{{2}}))?\b"
        m_p = re.search(pat, lat)
        if m_p:
            jd = int(m_p.group(1))
            jy = int(m_p.group(2)) if m_p.group(2) else (cur_y - 1 if m_num - cur_m > 6 else cur_y)
            if 1 <= jd <= 31:
                j_str = f"{jy:04d}/{m_num:02d}/{jd:02d}"
                return j_str, jalali_str_to_ts(j_str, fallback_ts)
    return "", fallback_ts


def parse_feed_entry_date(entry: dict, fallback_jalali: str, fallback_ts: int) -> tuple[str, int]:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        st = entry.get(key)
        if st:
            try:
                ts_utc = int(calendar.timegm(st))
                dt_utc = datetime.fromtimestamp(ts_utc, tz=timezone.utc)
                return datetime_to_iran_jalali_and_ts(dt_utc, fallback_ts)
            except Exception:
                pass
    for key in ("published", "updated", "dc_date", "created", "pubDate"):
        raw_val = _persian_digits_to_latin(str(entry.get(key, "") or "").strip())
        if not raw_val:
            continue
        m_j = re.search(r"\b(13\d{2}|14\d{2})[/-](\d{1,2})[/-](\d{1,2})\b", raw_val)
        if m_j:
            jy, jm, jd = int(m_j.group(1)), int(m_j.group(2)), int(m_j.group(3))
            if 1 <= jm <= 12 and 1 <= jd <= 31:
                j_str = f"{jy:04d}/{jm:02d}/{jd:02d}"
                return j_str, jalali_str_to_ts(j_str, fallback_ts)
        try:
            from dateutil import parser as du_parser
            parsed = du_parser.parse(raw_val)
            return datetime_to_iran_jalali_and_ts(parsed, fallback_ts)
        except Exception:
            pass
        m_g = re.search(r"\b(20\d{2}|19\d{2})[/-](\d{1,2})[/-](\d{1,2})\b", raw_val)
        if m_g:
            gy, gm, gd = int(m_g.group(1)), int(m_g.group(2)), int(m_g.group(3))
            if 1 <= gm <= 12 and 1 <= gd <= 31:
                jy, jm, jd = gregorian_to_jalali(gy, gm, gd)
                j_str = f"{jy:04d}/{jm:02d}/{jd:02d}"
                return j_str, jalali_str_to_ts(j_str, fallback_ts)
    return fallback_jalali, fallback_ts


def parse_iso_datetime_str(dt_str: str, fallback_jalali: str, fallback_ts: int) -> tuple[str, int]:
    cleaned = _persian_digits_to_latin((dt_str or "").strip())
    if not cleaned:
        return fallback_jalali, fallback_ts
    try:
        iso_norm = cleaned.replace("Z", "+00:00")
        dt_obj = datetime.fromisoformat(iso_norm)
        return datetime_to_iran_jalali_and_ts(dt_obj, fallback_ts)
    except Exception:
        pass
    try:
        from dateutil import parser as du_parser
        dt_obj = du_parser.parse(cleaned)
        return datetime_to_iran_jalali_and_ts(dt_obj, fallback_ts)
    except Exception:
        return fallback_jalali, fallback_ts


def normalize_date_to_jalali(date_str: str, fallback_str: str) -> str:
    if not date_str:
        return fallback_str
    cleaned = _persian_digits_to_latin(date_str).strip()
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


def is_fresh_news(item_date_jalali: str, text_content: str, today_jalali: str, now_stamp: int) -> bool:
    """بررسی تازه‌بودن خبر بر اساس تاریخ انتشار و تاریخ‌های داخل متن خبر"""
    pub_ts = jalali_str_to_ts(item_date_jalali, now_stamp)
    age_days_pub = (now_stamp - pub_ts) / 86400.0
    if age_days_pub > MAX_STALE_DAYS:
        return False

    emb_date, emb_ts = extract_text_embedded_jalali(text_content, today_jalali, now_stamp)
    if emb_date:
        age_days_emb = (now_stamp - emb_ts) / 86400.0
        norm_t = normalize_persian(text_content)
        is_deadline_past = ("مهلت" in norm_t or "تا تاریخ" in norm_t or "پایان" in norm_t) and age_days_emb > 7
        if age_days_emb > 25 or is_deadline_past:
            return False
    return True


def normalize_persian(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u200c", " ")
    text = text.replace("ي", "ی").replace("ك", "ک").replace("ة", "ه")
    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def is_ad_or_promo(title: str, summary: str, full_text: str = "") -> bool:
    """تشخیص تبلیغات، لینک‌های تبلیغاتی، شماره تماس تبلیغاتی و متن‌های بازاریابی"""
    combined = f"{title} {summary} {full_text}"
    norm = normalize_persian(combined)
    if any(normalize_persian(bad) in norm for bad in STRICT_EXCLUDE_KEYWORDS):
        return True
    if re.search(r"(?:شماره\s*تماس|تماس\s*با\s*ما|سفارش|پشتیبانی)\s*[:\s]*09\d{9}", _persian_digits_to_latin(combined)):
        return True
    return False


def strip_channel_promos(text: str) -> str:
    if not text:
        return ""
    text = re.sub(
        r"(?:کانال\s+)?نرخنامه\s+و\s+اخبار\s+کافی\s*[‌\s]?نت[^\n\.!؟]{0,90}(?:[\.!؟]|$)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\|?\s*لطف[ااً]?\s*به\s*اشتراک\s*بگذارید[^\n\.!؟]{0,80}(?:[\.!؟]|$)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"اخبار\s+کافی\s*[‌\s]?نت\s+کشوری[^\n\.!؟]{0,40}(?:[\.!؟]|$)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    for phrase in CHANNEL_TAG_PHRASES:
        text = re.sub(re.escape(phrase), "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\|\s*(?:نت\s*کشوری|کشوری|کانال[^\n|]{0,40})?\s*\|?\s*", " ", text)
    text = re.sub(r"\s*\|\s*", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(?:[\.\-–—|]+\s*)+$", "", text).strip()
    if text and not text.endswith((".", "!", "؟", ":", "»", ")")):
        if len(text.split()[-1]) <= 2 and "." in text:
            text = text.rsplit(".", 1)[0].strip()
    return text


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
    text = strip_channel_promos(text)
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


def detect_portal_url(title: str, summary: str, raw_html: str, section_key: str = "") -> str:
    """انتخاب لینک هماهنگ با محتوای دقیق خبر (به‌ویژه شرکت خودرویی مربوطه)"""
    norm_text = normalize_persian(f"{title} {summary}")

    if section_key == "cars" or any(normalize_persian(k) in norm_text for k in ["خودرو", "ایران خودرو", "سایپا", "بهمن موتور", "کرمان موتور", "مدیران خودرو", "فروش فوری", "پیش فروش", "یکپارچه خودرو", "وکالتی"]):
        for keywords, car_url in CAR_PORTAL_RULES:
            if any(normalize_persian(kw) in norm_text for kw in keywords):
                return car_url
        explicit_car = extract_official_url(f"{summary} {raw_html}")
        if explicit_car:
            return explicit_car
        if any(normalize_persian(w) in norm_text for w in ["ثبت نام", "ثبتنام", "فروش فوری", "پیش فروش", "فروش فوق العاده", "یکپارچه", "وکالتی"]):
            return "https://saleauto.ir"
        return ""

    explicit = extract_official_url(f"{summary} {raw_html}")
    if explicit:
        return explicit

    action_words = ["ثبت نام", "ثبتنام", "نام نویسی", "دریافت کارت", "کارت ورود به جلسه", "اعلام نتایج", "فراخوان", "اظهارنامه", "نوبت دهی", "وام", "یارانه", "کالابرگ", "سجام", "سهام عدالت", "کارت سوخت", "ابلاغیه", "ثنا", "فروش فوری", "پیش فروش", "یکپارچه", "وکالتی", "مای مدیو"]
    if not any(normalize_persian(aw) in norm_text for aw in action_words):
        return ""
    for keywords, portal_url in PORTAL_RULES:
        if any(normalize_persian(kw) in norm_text for kw in keywords):
            return portal_url
    return ""


def is_section_relevant(section_key: str, title: str, summary: str, full_text: str = "") -> bool:
    if is_ad_or_promo(title, summary, full_text):
        return False
    norm_text = normalize_persian(f"{title} {summary}")
    if not norm_text:
        return False
    if section_key == "important":
        return any(normalize_persian(kw) in norm_text for kw in IMPORTANT_KEYWORDS)
    if section_key == "cafenet":
        return any(normalize_persian(kw) in norm_text for kw in CAFENET_CORE_KEYWORDS)
    if section_key == "cars":
        return any(normalize_persian(kw) in norm_text for kw in CARS_CORE_KEYWORDS)
    if section_key == "exams":
        if any(normalize_persian(bad_ex) in norm_text for bad_ex in EXAMS_EXCLUDE_KEYWORDS):
            return False
        has_action = any(normalize_persian(kw) in norm_text for kw in EXAMS_ACTION_OR_EXAM_KEYWORDS)
        has_subj = any(normalize_persian(kw) in norm_text for kw in EXAMS_SUBJECT_KEYWORDS)
        return has_action or has_subj
    if section_key == "notices":
        return any(normalize_persian(kw) in norm_text for kw in NOTICES_CORE_KEYWORDS)
    return False


def is_important_item(title: str, summary: str, item_type: str) -> bool:
    if is_ad_or_promo(title, summary):
        return False
    if item_type == "alert":
        return True
    norm_text = normalize_persian(f"{title} {summary}")
    return any(normalize_persian(kw) in norm_text for kw in IMPORTANT_KEYWORDS)


def detect_type(title: str, summary: str) -> str:
    norm_text = normalize_persian(f"{title} {summary}")
    if any(k in norm_text for k in ["فوری", "لغو", "تمدید", "هشدار", "پایان مهلت", "آخرین مهلت", "اطلاعیه مهم"]):
        return "alert"
    if any(k in norm_text for k in ["ثبت نام", "نام نویسی", "آغاز", "شروع", "اعلام نتایج", "فراخوان", "فروش فوری", "پیش فروش", "فروش فوق العاده", "وکالتی"]):
        return "update"
    return "info"


def make_id(seed: str) -> int:
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def is_duplicate(norm_title: str, seen_titles: set[str]) -> bool:
    if norm_title in seen_titles:
        return True
    words_a = set(norm_title.split())
    if len(words_a) >= 5:
        for existing in seen_titles:
            words_b = set(existing.split())
            if words_b:
                overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
                if overlap >= 0.90:
                    return True
    return False


def load_json_data(path: Path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def build_clean_title_and_summary(raw_block: str, is_estekhdam: bool = False) -> tuple[str, str, str]:
    clean_full = clean_text_content(raw_block, max_len=DEFAULT_FULL_LEN, strip_links_and_tags_text=is_estekhdam)
    if not clean_full or len(clean_full) < 8:
        return "", "", ""
    parts = re.split(r"<br\s*/?>|\n", raw_block)
    cleaned_parts = [
        clean_text_content(p, max_len=160, strip_links_and_tags_text=is_estekhdam)
        for p in parts
    ]
    cleaned_parts = [p for p in cleaned_parts if p and len(p) >= 4 and not p.startswith(("<i", "class=", "style="))]
    title = cleaned_parts[0] if cleaned_parts else clean_full[:115]
    if len(title) > 120:
        title = title[:117] + "..."
    summary = clean_text_content(raw_block, max_len=DEFAULT_SUMMARY_LEN, strip_links_and_tags_text=is_estekhdam)
    return title, summary, clean_full


def parse_telegram_channel(url: str, fallback_jalali: str, fallback_ts: int) -> list[dict]:
    is_estekhdam = "eestekhdam" in url.lower()
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        page_html = resp.read().decode("utf-8", errors="ignore")
    text_matches = list(re.finditer(
        r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
        page_html,
        flags=re.DOTALL,
    ))
    entries = []
    for idx_m, tm_obj in enumerate(text_matches[-30:]):
        raw_block = tm_obj.group(1)
        start_pos = tm_obj.end()
        next_start = text_matches[text_matches.index(tm_obj) + 1].start() if text_matches.index(tm_obj) + 1 < len(text_matches) else len(page_html)
        window_html = page_html[start_pos:next_start]
        time_m = re.search(r'<time[^>]*datetime="([^"]+)"', window_html)
        dt_str = time_m.group(1) if time_m else ""
        item_jalali, item_ts = parse_iso_datetime_str(dt_str, fallback_jalali, fallback_ts - (30 - idx_m))
        title, summary, full_text = build_clean_title_and_summary(raw_block, is_estekhdam=is_estekhdam)
        if not title or not summary:
            continue
        entries.append({
            "title": title,
            "summary": summary,
            "full_text": full_text,
            "raw_html": raw_block,
            "date": item_jalali,
            "ts": item_ts,
        })
    return list(reversed(entries))


def fetch_source(section_key: str, source: dict, fallback_jalali: str, fallback_ts: int) -> tuple[str, str, list[dict]]:
    try:
        if source.get("type") == "telegram":
            entries = parse_telegram_channel(source["url"], fallback_jalali, fallback_ts)
            return section_key, source["name"], entries
        feed = feedparser.parse(source["url"])
        entries = []
        for i, e in enumerate(getattr(feed, "entries", [])):
            raw_html = str(e.get("summary", "") or e.get("description", "") or e.get("content", [{}])[0].get("value", "") if isinstance(e.get("content"), list) and e.get("content") else (e.get("summary", "") or e.get("description", "")))
            title_clean = clean_text_content(str(e.get("title", "")), max_len=130)
            summary_clean = clean_text_content(raw_html, max_len=DEFAULT_SUMMARY_LEN)
            full_clean = clean_text_content(raw_html, max_len=DEFAULT_FULL_LEN)
            item_jalali, item_ts = parse_feed_entry_date(dict(e), fallback_jalali, fallback_ts - i)
            entries.append({
                "title": title_clean,
                "summary": summary_clean,
                "full_text": full_clean,
                "raw_html": raw_html,
                "date": item_jalali,
                "ts": item_ts,
            })
        return section_key, source["name"], entries
    except Exception as e:
        print(f"[{section_key}] خطا در {source['name']}: {e}")
        return section_key, source["name"], []


def write_paginated_section(sec_key: str, base_file: Path, items: list[dict], updated_jalali: str) -> None:
    capped_items = items[:MAX_ITEMS_PER_SECTION]
    total_items = len(capped_items)
    total_pages = max(1, math.ceil(total_items / PAGE_SIZE)) if total_items > 0 else 1

    for p in range(1, MAX_PAGES + 1):
        start_idx = (p - 1) * PAGE_SIZE
        end_idx = start_idx + PAGE_SIZE
        page_items = capped_items[start_idx:end_idx]
        next_page_file = f"{sec_key}_p{p + 1}.json" if p < total_pages else ""
        page_payload = {
            "section": sec_key,
            "updated_at": updated_jalali,
            "page": p,
            "page_size": PAGE_SIZE,
            "max_pages": MAX_PAGES,
            "total_items": total_items,
            "total_pages": total_pages,
            "has_more": p < total_pages,
            "next_page": (p + 1) if p < total_pages else None,
            "next_file": next_page_file,
            "items": page_items,
        }
        target_path = base_file if p == 1 else base_file.with_name(f"{sec_key}_p{p}.json")
        target_path.write_text(
            json.dumps(page_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now_ir = get_iran_now()
    now_stamp = int(now_ir.timestamp())
    today_jalali = get_today_jalali_str(now_ir)
    section_items: dict[str, list[dict]] = {}
    seen_ids: dict[str, set[int]] = {}
    global_seen_titles: set[str] = set()

    for sec_key, cfg in SECTIONS.items():
        if sec_key == "important":
            section_items[sec_key] = []
            seen_ids[sec_key] = set()
            continue

        raw_items = []
        for p in range(1, MAX_PAGES + 1):
            p_path = cfg["file"] if p == 1 else cfg["file"].with_name(f"{sec_key}_p{p}.json")
            raw_data = load_json_data(p_path)
            if isinstance(raw_data, dict):
                if isinstance(raw_data.get("items"), list):
                    raw_items.extend(raw_data["items"])
                if p == 1 and isinstance(raw_data.get("pages"), dict):
                    for pk in sorted(raw_data["pages"].keys(), key=lambda k: int(k) if str(k).isdigit() else 999):
                        if pk != "1" and isinstance(raw_data["pages"][pk], list):
                            raw_items.extend(raw_data["pages"][pk])
            elif isinstance(raw_data, list):
                raw_items.extend(raw_data)

        items = []
        for x in raw_items:
            t = clean_text_content(str(x.get("title", "")), max_len=130)
            raw_msg = str(x.get("full_text") or x.get("message") or "")
            is_est = ("e-estekhdam" in raw_msg.lower()) or ("eestekhdam" in raw_msg.lower())
            m = clean_text_content(raw_msg, max_len=DEFAULT_SUMMARY_LEN, strip_links_and_tags_text=is_est)
            full_m = clean_text_content(raw_msg, max_len=DEFAULT_FULL_LEN, strip_links_and_tags_text=is_est)
            item_date = normalize_date_to_jalali(str(x.get("date", "")), today_jalali)
            if not is_section_relevant(sec_key, t, m, full_m):
                continue
            if not is_fresh_news(item_date, f"{t} {full_m}", today_jalali, now_stamp):
                continue
            existing_reg = detect_portal_url(t, m, "", section_key=sec_key)
            if not existing_reg:
                cand_reg = str(x.get("reg_url", "")).strip()
                if cand_reg and not is_blocked_url(cand_reg):
                    existing_reg = cand_reg
            order_ts = int(x.get("_order") or jalali_str_to_ts(item_date, now_stamp))
            cleaned_item = {
                "id": int(x.get("id", make_id(normalize_persian(t)))),
                "type": detect_type(t, m),
                "category": sec_key,
                "title": t,
                "message": m,
                "full_text": full_m,
                "date": item_date,
                "_order": order_ts,
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
                futures.append(executor.submit(fetch_source, sec_key, src, today_jalali, now_stamp))
        for idx, fut in enumerate(as_completed(futures)):
            sec_key, src_name, entries = fut.result()
            added = 0
            sample_dates = []
            for entry in entries:
                is_est = "e-estekhdam" in (src_name.lower() + " " + str(entry.get("summary", "")).lower())
                title = clean_text_content(str(entry.get("title", "")), max_len=130, strip_links_and_tags_text=is_est)
                summary = clean_text_content(str(entry.get("summary", "")), max_len=DEFAULT_SUMMARY_LEN, strip_links_and_tags_text=is_est)
                full_text = clean_text_content(str(entry.get("full_text") or summary), max_len=DEFAULT_FULL_LEN, strip_links_and_tags_text=is_est)
                raw_html = str(entry.get("raw_html", ""))
                item_date = normalize_date_to_jalali(str(entry.get("date", "")), today_jalali)
                if not title:
                    continue
                if not is_section_relevant(sec_key, title, summary, full_text):
                    continue
                if not is_fresh_news(item_date, f"{title} {full_text}", today_jalali, now_stamp):
                    continue
                norm_title = normalize_persian(title)
                if not norm_title or is_duplicate(norm_title, global_seen_titles):
                    continue
                item_id = make_id(norm_title)
                if item_id in seen_ids[sec_key]:
                    continue
                reg_url = detect_portal_url(title, summary, raw_html, section_key=sec_key)
                item_ts = int(entry.get("ts") or jalali_str_to_ts(item_date, now_stamp - idx))
                item_obj = {
                    "id": item_id,
                    "type": detect_type(title, summary),
                    "category": sec_key,
                    "title": title,
                    "message": summary or title,
                    "full_text": full_text or summary or title,
                    "date": item_date,
                    "_order": item_ts,
                }
                if reg_url:
                    item_obj["reg_url"] = reg_url
                section_items[sec_key].append(item_obj)
                seen_ids[sec_key].add(item_id)
                global_seen_titles.add(norm_title)
                added += 1
                if len(sample_dates) < 3:
                    sample_dates.append(item_date)
            print(f"[{sec_key}] منبع «{src_name}»: {added} اطلاعیه مرتبط جدید اضافه شد. (نمونه تاریخ‌ها: {sample_dates})")

    important_candidates = []
    important_seen_ids = set()
    for sec_key in ("cafenet", "cars", "exams", "notices"):
        for item in section_items.get(sec_key, []):
            if item["id"] in important_seen_ids:
                continue
            if is_important_item(item.get("title", ""), item.get("message", ""), item.get("type", "info")):
                imp_copy = dict(item)
                imp_copy["source_section"] = sec_key
                important_candidates.append(imp_copy)
                important_seen_ids.add(item["id"])

    section_items["important"] = important_candidates
    print(f"[important] مجموع خبرهای مهم گلچین‌شده: {len(important_candidates)} مورد.")

    for sec_key, cfg in SECTIONS.items():
        sorted_sec = sorted(
            section_items[sec_key],
            key=lambda x: int(x.get("_order", x.get("id", 0))),
            reverse=True,
        )[:MAX_ITEMS_PER_SECTION]
        write_paginated_section(sec_key, cfg["file"], sorted_sec, today_jalali)


if __name__ == "__main__":
    main()
