"""
date_formatter.py
-----------------
Module containing functionalities for Jalali (Persian) date conversion, calendar calculations, and formatting.
"""
# === IMPORTS ===
import datetime
import time
import re

try:
    import jdatetime
except ImportError:
    jdatetime = None

JALALI_MONTH_NAMES = [
    "",
    "فروردین", "اردیبهشت", "خرداد",
    "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر",
    "دی", "بهمن", "اسفند"
]

PERSIAN_WEEKDAYS_SHORT = ["ش", "ی", "د", "س", "چ", "پ", "ج"]
PERSIAN_WEEKDAYS_FULL = [
    "شنبه", "یک‌شنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"
]

def normalize_persian_digits(text: str) -> str:
    """Converts Persian and Arabic digits to standard ASCII English digits."""
    if not text:
        return ""
    for i, (p, a) in enumerate(zip('۰۱۲۳۴۵۶۷۸۹', '٠١٢٣٤٥٦٧٨٩')):
        text = text.replace(p, str(i)).replace(a, str(i))
    return text.strip()

def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """Converts Gregorian date (year, month, day) to Jalali (jy, jm, jd)."""
    if jdatetime:
        try:
            jdt = jdatetime.date.fromgregorian(year=gy, month=gm, day=gd)
            return jdt.year, jdt.month, jdt.day
        except Exception:
            pass

    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    jy = -1595 + (33 * (days // 12053))
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
    """Converts Jalali date (year, month, day) to Gregorian (gy, gm, gd)."""
    if jdatetime:
        try:
            gdt = jdatetime.date(jy, jm, jd).togregorian()
            return gdt.year, gdt.month, gdt.day
        except Exception:
            pass

    jy += 1595
    days = -355668 + (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += ((jm - 7) * 30) + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    sal_a = [0, 31, 29 if ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 13 and gd > sal_a[gm]:
        gd -= sal_a[gm]
        gm += 1
    return gy, gm, gd

def is_jalali_leap(jy: int) -> bool:
    """Checks if a Jalali year is a leap year (kabiseh)."""
    if jdatetime:
        try:
            return jdatetime.date(jy, 1, 1).isleap()
        except Exception:
            pass
    try:
        d1 = datetime.date(*jalali_to_gregorian(jy, 1, 1))
        d2 = datetime.date(*jalali_to_gregorian(jy + 1, 1, 1))
        return (d2 - d1).days == 366
    except Exception:
        return False

def get_days_in_jalali_month(jy: int, jm: int) -> int:
    """Returns number of days in the specified Jalali month (1-12)."""
    if 1 <= jm <= 6:
        return 31
    elif 7 <= jm <= 11:
        return 30
    elif jm == 12:
        return 30 if is_jalali_leap(jy) else 29
    return 30

def get_persian_weekday_index(gy: int, gm: int, gd: int) -> int:
    """Returns weekday index: 0=Saturday (شنبه) to 6=Friday (جمعه)."""
    dt = datetime.date(gy, gm, gd)
    return (dt.weekday() + 2) % 7

def get_persian_weekday_name(gy: int, gm: int, gd: int) -> str:
    """Returns full Persian name of the weekday."""
    idx = get_persian_weekday_index(gy, gm, gd)
    return PERSIAN_WEEKDAYS_FULL[idx]

# === JALALI DATE FORMATTER ===
def get_jalali_date(timestamp: int = None, format_str: str = "%Y/%m/%d %H:%M:%S") -> str:
    """
    Converts a UNIX timestamp to a Jalali (Persian) date string.
    Replaces the legacy jdf.php module.
    """
    if timestamp is None:
        timestamp = int(time.time())
        
    dt = datetime.datetime.fromtimestamp(timestamp)
    
    if jdatetime:
        try:
            jdt = jdatetime.datetime.fromgregorian(datetime=dt)
            return jdt.strftime(format_str)
        except Exception:
            pass

    jy, jm, jd = gregorian_to_jalali(dt.year, dt.month, dt.day)
    res = format_str
    res = res.replace('%Y', f'{jy:04d}').replace('%m', f'{jm:02d}').replace('%d', f'{jd:02d}')
    res = res.replace('%H', f'{dt.hour:02d}').replace('%M', f'{dt.minute:02d}').replace('%S', f'{dt.second:02d}')
    return res

def get_current_jalali() -> str:
    """Returns the current date and time in Jalali format."""
    return get_jalali_date(format_str="%Y/%m/%d %H:%M:%S")

def parse_custom_date_input(text: str) -> tuple[str, str, str] | None:
    """
    Parses user input string into (start_datetime_str, end_datetime_str, display_title).
    Supports Persian or Gregorian single dates and ranges.
    Returns None if the format cannot be parsed.
    """
    t = normalize_persian_digits(text)
    if not t:
        return None

    def _parse_single(part: str):
        part = part.strip()
        m = re.match(r'^(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})$', part)
        if not m:
            return None
        y, mo, da = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1600:
            if not (1 <= mo <= 12 and 1 <= da <= 31):
                return None
            gy, gm, gd = jalali_to_gregorian(y, mo, da)
            dt = datetime.date(gy, gm, gd)
            m_name = JALALI_MONTH_NAMES[mo] if 1 <= mo <= 12 else ''
            w_name = get_persian_weekday_name(gy, gm, gd)
            label = f"{w_name} {da} {m_name} {y}"
            return dt, label
        else:
            if not (1 <= mo <= 12 and 1 <= da <= 31):
                return None
            dt = datetime.date(y, mo, da)
            jy, jm, jd = gregorian_to_jalali(y, mo, da)
            m_name = JALALI_MONTH_NAMES[jm] if 1 <= jm <= 12 else ''
            label = f"{jd} {m_name} {jy} ({y}-{mo:02d}-{da:02d})"
            return dt, label

    separators = [' تا ', ' to ', ' - ', ' _ ', ' — ']
    found_sep = None
    for sep in separators:
        if sep in t:
            found_sep = sep
            break

    if found_sep:
        parts = t.split(found_sep, 1)
        r1 = _parse_single(parts[0])
        r2 = _parse_single(parts[1])
        if r1 and r2:
            d1, l1 = r1
            d2, l2 = r2
            if d1 > d2:
                d1, d2 = d2, d1
                l1, l2 = l2, l1
            start_str = d1.strftime('%Y-%m-%d 00:00:00')
            end_str = d2.strftime('%Y-%m-%d 23:59:59')
            title = f"بازه {l1} تا {l2}"
            return start_str, end_str, title
    else:
        r = _parse_single(t)
        if r:
            d, l = r
            start_str = d.strftime('%Y-%m-%d 00:00:00')
            end_str = d.strftime('%Y-%m-%d 23:59:59')
            title = f"{l} ({d.strftime('%Y-%m-%d')})"
            return start_str, end_str, title

    return None
