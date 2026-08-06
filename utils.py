"""توابع کمکی خالص (بدون وابستگی به دیتابیس)."""
import math
import random
import string
import time
from datetime import datetime, timedelta


def safe_int(x, default=0):
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def now_ts() -> int:
    return int(time.time())


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def day_str_plus(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")


def gen_public_id() -> str:
    ln = random.randint(7, 12)
    return "".join(random.choice(string.ascii_lowercase) for _ in range(ln))


def gen_anon_code_12() -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(12))


def gen_req_id() -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(18))


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def last_seen_text(user: dict) -> str:
    ts = safe_int(user.get("last_seen") or 0, 0)
    if not ts:
        return "نامشخص"
    if now_ts() - ts <= 60:
        return "*آنلاین*"
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "نامشخص"


def iran_time_str_from_ts(ts: int) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "نامشخص"


def normalize_gender_text(user: dict) -> str:
    g = user.get("gender")
    if g == "male":
        return "🙎‍♂️ پسر"
    if g == "female":
        return "🙍‍♀️ دختر"
    return "تعیین نشده"


def distance_text(viewer_user: dict, target_user: dict) -> str:
    vg = viewer_user.get("gps") or {}
    tg = target_user.get("gps") or {}
    if vg.get("lat") is None or vg.get("lon") is None:
        return "موقعیت شما ثبت نشده!"
    if tg.get("lat") is None or tg.get("lon") is None:
        return "موقعیت کاربر ثبت نشده!"
    try:
        km = haversine_km(float(vg["lat"]), float(vg["lon"]), float(tg["lat"]), float(tg["lon"]))
        if km < 1:
            return "کمتر از 1 کیلومتر"
        return f"{km:.1f} کیلومتر"
    except Exception:
        return "نامشخص"


def user_is_online_recent(user: dict, minutes: int = 15) -> bool:
    ts = safe_int(user.get("last_seen") or 0, 0)
    if not ts:
        return False
    return (now_ts() - ts) <= minutes * 60


def user_is_silent(user: dict) -> bool:
    if user.get("silent_forever", False):
        return True
    su = user.get("silent_until")
    if su and safe_int(su, 0) > now_ts():
        return True
    return False


def silent_status_text(user: dict) -> str:
    if user.get("silent_forever", False):
        return "🔕 همیشه"
    su = user.get("silent_until")
    if su:
        su = safe_int(su, 0)
        if su > now_ts():
            return f"🔕 تا {iran_time_str_from_ts(su)}"
    return "🔔 خاموش"


def get_profile_missing_fields(user: dict) -> list:
    missing = []
    if not (user.get("display_name") or "").strip():
        missing.append("نام")
    if not (user.get("city") or "").strip():
        missing.append("شهر")
    if not (user.get("profile_photo_file_id") or "").strip():
        missing.append("عکس پروفایل")
    gps = user.get("gps") or {}
    if gps.get("lat") is None or gps.get("lon") is None:
        missing.append("موقعیت مکانی")
    return missing


def normalize_ble_channel_link(s: str):
    s = (s or "").strip()
    if not s:
        return None
    if s == "0":
        return "0"
    if not (s.startswith("https://ble.ir/") or s.startswith("http://ble.ir/")):
        return None
    if s.startswith("http://"):
        s = "https://" + s[len("http://"):]
    return s


def extract_ble_slug(link: str):
    link = (link or "").strip()
    if not link:
        return None
    link = link.replace("http://ble.ir/", "https://ble.ir/")
    if not link.startswith("https://ble.ir/"):
        return None
    slug = link[len("https://ble.ir/"):].strip().strip("/")
    if not slug:
        return None
    return slug


def parse_token_host_id(token: str, prefixes):
    token = (token or "").strip()
    for prefix in prefixes:
        if token.lower().startswith(prefix):
            value = token[len(prefix):].strip()
            return value if value.isdigit() else None
    return None
