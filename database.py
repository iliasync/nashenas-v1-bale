"""
لایه‌ی دیتابیس (SQLite سریع و async با aiosqlite).

طراحی:
- جدول `users`: ستون‌های پُرکاربرد و قابل-جستجو (جنسیت، سن، استان، last_seen، chat_with و ...)
  به صورت ستون مستقیم + ایندکس ذخیره می‌شوند تا کوئری‌های جستجو/مچ‌میکینگ سریع باشند.
  فیلدهای تو‌در‌توی کم‌کاربرد (contacts، my_likes، blocked_users، search، mm، buy،
  transactions، pending_* و ...) داخل ستون JSON به نام `extra` نگه داشته می‌شوند تا هم
  ساختار اصلیِ دیتای کاربر (دیکشنری مشابه نسخه‌ی JSON قبلی) حفظ شود و هم نیازی به
  نُرمال‌سازیِ کامل و پیچیده نباشد.
- جدول‌های global سابق (stats / force_join_channels / chat_requests / mm_queue / payments)
  هرکدام جدول مستقل خودشان را دارند.
- mm_queue (صف matchmaking) و سشن‌های دوز/سنگ‌کاغذقیچی، چون کاملاً موقتی (ephemeral) هستند
  و با ری‌استارت شدن ربات منطقاً باید از نو شروع شوند، در حافظه (RAM) نگه داشته می‌شوند
  (داخل ماژول‌های handlers/matchmaking.py، handlers/dooz.py، handlers/rps.py) نه در DB.
"""
import json
from typing import Optional

import aiosqlite

from config import DB_PATH
from utils import now_ts, today_str, day_str_plus, safe_int, haversine_km, gen_public_id, gen_anon_code_12

_db: Optional[aiosqlite.Connection] = None

# کلیدهایی که به صورت ستون مستقیم در جدول users ذخیره می‌شوند (بقیه در extra/JSON می‌روند)
_COLUMN_KEYS = {
    "user_id",
    "coins", "admin_state", "bot_banned", "panel_tmp_target", "state", "gender", "age",
    "province", "city", "display_name", "profile_photo_file_id", "profile_completed",
    "profile_completion_rewarded", "public_id", "likes", "created_at", "last_seen",
    "gps_rewarded", "invite_count", "referred_by", "ref_rewarded", "anon_code",
    "silent_until", "silent_forever", "chat_with", "chat_started_at",
}

GLOBAL_STAT_KEYS = (
    "new_users", "chats_started", "anon_messages", "local_messages",
    "gender_messages", "profile_completed",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    coins INTEGER NOT NULL DEFAULT 0,
    admin_state TEXT,
    bot_banned INTEGER NOT NULL DEFAULT 0,
    panel_tmp_target TEXT,
    state TEXT,
    gender TEXT,
    age INTEGER,
    province TEXT,
    city TEXT,
    display_name TEXT,
    profile_photo_file_id TEXT,
    profile_completed INTEGER NOT NULL DEFAULT 0,
    profile_completion_rewarded INTEGER NOT NULL DEFAULT 0,
    public_id TEXT UNIQUE,
    likes INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER,
    last_seen INTEGER,
    gps_lat REAL,
    gps_lon REAL,
    gps_set_at INTEGER,
    gps_rewarded INTEGER NOT NULL DEFAULT 0,
    invite_count INTEGER NOT NULL DEFAULT 0,
    referred_by TEXT,
    ref_rewarded INTEGER NOT NULL DEFAULT 0,
    anon_code TEXT UNIQUE,
    silent_until INTEGER,
    silent_forever INTEGER NOT NULL DEFAULT 0,
    chat_with TEXT,
    chat_started_at INTEGER,
    extra TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_users_gender ON users(gender);
CREATE INDEX IF NOT EXISTS idx_users_province ON users(province);
CREATE INDEX IF NOT EXISTS idx_users_age ON users(age);
CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users(last_seen);
CREATE INDEX IF NOT EXISTS idx_users_chat_with ON users(chat_with);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);
CREATE INDEX IF NOT EXISTS idx_users_profile_completed ON users(profile_completed);

CREATE TABLE IF NOT EXISTS stats (
    day TEXT PRIMARY KEY,
    new_users INTEGER NOT NULL DEFAULT 0,
    chats_started INTEGER NOT NULL DEFAULT 0,
    anon_messages INTEGER NOT NULL DEFAULT 0,
    local_messages INTEGER NOT NULL DEFAULT 0,
    gender_messages INTEGER NOT NULL DEFAULT 0,
    profile_completed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS force_join_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT UNIQUE NOT NULL,
    title TEXT,
    bot_is_admin INTEGER NOT NULL DEFAULT 0,
    bot_can_invite INTEGER NOT NULL DEFAULT 0,
    invite_link TEXT,
    created_at INTEGER
);

CREATE TABLE IF NOT EXISTS chat_requests (
    req_id TEXT PRIMARY KEY,
    from_uid TEXT NOT NULL,
    to_uid TEXT NOT NULL,
    created_at INTEGER,
    status TEXT NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS payments (
    tx_id TEXT PRIMARY KEY,
    buyer_uid TEXT,
    buyer_pid TEXT,
    coins INTEGER,
    price INTEGER,
    file_id TEXT,
    ocr_text TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at INTEGER,
    reviewed_at INTEGER
);
"""


async def init_db():
    global _db
    _db = await aiosqlite.connect(DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL;")
    await _db.execute("PRAGMA synchronous=NORMAL;")
    await _db.execute("PRAGMA foreign_keys=ON;")

    # مایگریشن: اگر جدول قدیمی با ستون link وجود دارد، حذف و بازسازی کن
    cur = await _db.execute("PRAGMA table_info(force_join_channels)")
    cols = {row[1] for row in await cur.fetchall()}
    if cols and "chat_id" not in cols:
        await _db.execute("DROP TABLE IF EXISTS force_join_channels")

    await _db.executescript(SCHEMA)
    await _db.commit()
    await ensure_stats_days()


async def close_db():
    global _db
    if _db is not None:
        await _db.close()
        _db = None


def _conn() -> aiosqlite.Connection:
    if _db is None:
        raise RuntimeError("Database is not initialized yet. Call init_db() first.")
    return _db


# ---------------------------------------------------------------------------
# کاربران
# ---------------------------------------------------------------------------
def _default_user() -> dict:
    return {
        "user_id": None,
        "coins": 0, "admin_state": None, "bot_banned": False, "panel_tmp_target": None,
        "state": None, "gender": None, "age": None, "province": None, "city": None,
        "display_name": None, "profile_photo_file_id": None,
        "profile_completed": False, "profile_completion_rewarded": False,
        "public_id": None, "likes": 0, "created_at": None,
        "gps": {"lat": None, "lon": None, "set_at": None}, "gps_rewarded": False,
        "last_seen": None,
        "invite_count": 0, "referred_by": None, "ref_rewarded": False,
        "anon_code": None,
        "contacts": [], "my_likes": [], "blocked_users": [],
        "silent_until": None, "silent_forever": False,
        "search": {
            "last_results": [], "last_meta": {}, "show_dropdown": False,
            "adv_gender": None, "adv_selected_provinces": [], "adv_near_me": False,
        },
        "mm": {"searching": False, "mode": None, "started_at": None, "msg_id": None, "near": False},
        "buy": {"state": None, "tmp_pkg": None, "tmp_msg_id": None},
        "transactions": [],
        "chat_with": None, "chat_started_at": None,
        "pending_incoming_req": [], "pending_outgoing_req": [], "notify_chat_end": [],
        "pending_ref_pid": None, "pending_anon_token": None,
        "pending_dooz_host": None, "pending_rps_host": None,
        "tmp_direct_pid": None, "tmp_contact_pid": None, "nearby_root_msg_id": None,
    }


def _row_to_dict(row: aiosqlite.Row) -> dict:
    try:
        extra = json.loads(row["extra"] or "{}")
    except Exception:
        extra = {}
    user = _default_user()
    user.update(extra)
    user.update({
        "user_id": row["user_id"],
        "coins": row["coins"],
        "admin_state": row["admin_state"],
        "bot_banned": bool(row["bot_banned"]),
        "panel_tmp_target": row["panel_tmp_target"],
        "state": row["state"],
        "gender": row["gender"],
        "age": row["age"],
        "province": row["province"],
        "city": row["city"],
        "display_name": row["display_name"],
        "profile_photo_file_id": row["profile_photo_file_id"],
        "profile_completed": bool(row["profile_completed"]),
        "profile_completion_rewarded": bool(row["profile_completion_rewarded"]),
        "public_id": row["public_id"],
        "likes": row["likes"],
        "created_at": row["created_at"],
        "last_seen": row["last_seen"],
        "gps": {"lat": row["gps_lat"], "lon": row["gps_lon"], "set_at": row["gps_set_at"]},
        "gps_rewarded": bool(row["gps_rewarded"]),
        "invite_count": row["invite_count"],
        "referred_by": row["referred_by"],
        "ref_rewarded": bool(row["ref_rewarded"]),
        "anon_code": row["anon_code"],
        "silent_until": row["silent_until"],
        "silent_forever": bool(row["silent_forever"]),
        "chat_with": row["chat_with"],
        "chat_started_at": row["chat_started_at"],
    })
    return user


async def get_user(uid, create_if_missing: bool = True) -> Optional[dict]:
    uid = str(uid)
    db = _conn()
    cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (uid,))
    row = await cur.fetchone()
    if row is None:
        if not create_if_missing:
            return None
        user = _default_user()
        user["user_id"] = uid
        await save_user(uid, user)
        return user
    return _row_to_dict(row)


async def save_user(uid, user: dict):
    uid = str(uid)
    db = _conn()
    gps = user.get("gps") or {}
    extra = {k: v for k, v in user.items() if k not in _COLUMN_KEYS and k != "gps"}
    await db.execute(
        """
        INSERT INTO users (
            user_id, coins, admin_state, bot_banned, panel_tmp_target, state, gender, age, province, city,
            display_name, profile_photo_file_id, profile_completed, profile_completion_rewarded, public_id,
            likes, created_at, last_seen, gps_lat, gps_lon, gps_set_at, gps_rewarded, invite_count,
            referred_by, ref_rewarded, anon_code, silent_until, silent_forever, chat_with, chat_started_at, extra
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
            coins=excluded.coins, admin_state=excluded.admin_state, bot_banned=excluded.bot_banned,
            panel_tmp_target=excluded.panel_tmp_target, state=excluded.state, gender=excluded.gender,
            age=excluded.age, province=excluded.province, city=excluded.city, display_name=excluded.display_name,
            profile_photo_file_id=excluded.profile_photo_file_id, profile_completed=excluded.profile_completed,
            profile_completion_rewarded=excluded.profile_completion_rewarded, public_id=excluded.public_id,
            likes=excluded.likes, created_at=excluded.created_at, last_seen=excluded.last_seen,
            gps_lat=excluded.gps_lat, gps_lon=excluded.gps_lon, gps_set_at=excluded.gps_set_at,
            gps_rewarded=excluded.gps_rewarded, invite_count=excluded.invite_count,
            referred_by=excluded.referred_by, ref_rewarded=excluded.ref_rewarded, anon_code=excluded.anon_code,
            silent_until=excluded.silent_until, silent_forever=excluded.silent_forever,
            chat_with=excluded.chat_with, chat_started_at=excluded.chat_started_at, extra=excluded.extra
        """,
        (
            uid, safe_int(user.get("coins"), 0), user.get("admin_state"), int(bool(user.get("bot_banned"))),
            user.get("panel_tmp_target"), user.get("state"), user.get("gender"), user.get("age"),
            user.get("province"), user.get("city"), user.get("display_name"), user.get("profile_photo_file_id"),
            int(bool(user.get("profile_completed"))), int(bool(user.get("profile_completion_rewarded"))),
            user.get("public_id"), safe_int(user.get("likes"), 0), user.get("created_at"), user.get("last_seen"),
            gps.get("lat"), gps.get("lon"), gps.get("set_at"), int(bool(user.get("gps_rewarded"))),
            safe_int(user.get("invite_count"), 0), user.get("referred_by"), int(bool(user.get("ref_rewarded"))),
            user.get("anon_code"), user.get("silent_until"), int(bool(user.get("silent_forever"))),
            user.get("chat_with"), user.get("chat_started_at"), json.dumps(extra, ensure_ascii=False),
        ),
    )
    await db.commit()


async def get_user_by_public_id(pid: str):
    pid = (pid or "").strip()
    if not pid:
        return None, None
    db = _conn()
    cur = await db.execute("SELECT * FROM users WHERE public_id = ?", (pid,))
    row = await cur.fetchone()
    if row is None:
        return None, None
    return row["user_id"], _row_to_dict(row)


async def get_user_by_anon_code(code: str):
    code = (code or "").strip().strip('"')
    if not code:
        return None, None
    db = _conn()
    cur = await db.execute("SELECT * FROM users WHERE anon_code = ?", (code,))
    row = await cur.fetchone()
    if row is None:
        return None, None
    return row["user_id"], _row_to_dict(row)


async def ensure_unique_public_id(uid) -> str:
    user = await get_user(uid)
    if user.get("public_id"):
        return user["public_id"]
    db = _conn()
    while True:
        pid = gen_public_id()
        cur = await db.execute("SELECT 1 FROM users WHERE public_id = ?", (pid,))
        if await cur.fetchone() is None:
            break
    user["public_id"] = pid
    await save_user(uid, user)
    return pid


async def ensure_unique_anon_code(uid) -> str:
    user = await get_user(uid)
    if (user.get("anon_code") or "").strip():
        return user["anon_code"]
    db = _conn()
    while True:
        code = gen_anon_code_12()
        cur = await db.execute("SELECT 1 FROM users WHERE anon_code = ?", (code,))
        if await cur.fetchone() is None:
            break
    user["anon_code"] = code
    await save_user(uid, user)
    return code


async def count_total_users() -> int:
    db = _conn()
    cur = await db.execute("SELECT COUNT(*) AS c FROM users")
    row = await cur.fetchone()
    return row["c"] if row else 0


async def iter_all_user_ids():
    """فقط آیدی‌ها (برای ارسال همگانی/سکه همگانی) - حافظه‌ی کمتری مصرف می‌کند."""
    db = _conn()
    cur = await db.execute("SELECT user_id, bot_banned FROM users")
    rows = await cur.fetchall()
    return [(r["user_id"], bool(r["bot_banned"])) for r in rows]


async def add_coins_to_all_users(amount: int, include_banned: bool = False) -> int:
    """افزایش سکه کاربران در یک تراکنش؛ مناسب برای سکه همگانی."""
    amount = safe_int(amount, 0)
    if amount <= 0:
        return 0
    db = _conn()
    if include_banned:
        cur = await db.execute("UPDATE users SET coins = coins + ?", (amount,))
    else:
        cur = await db.execute("UPDATE users SET coins = coins + ? WHERE bot_banned = 0", (amount,))
    await db.commit()
    return max(0, cur.rowcount or 0)


# ---------------------------------------------------------------------------
# جستجو (کوئری‌های ایندکس‌شده‌ی سریع)
# ---------------------------------------------------------------------------
def _gender_clause(gfilter):
    if gfilter in ("male", "female"):
        return " AND gender = ?", [gfilter]
    return "", []


async def search_same_age(viewer_uid, age, gfilter, recent_days=3, limit=500):
    if age is None:
        return []
    db = _conn()
    min_ts = now_ts() - recent_days * 86400
    clause, gparams = _gender_clause(gfilter)
    sql = (
        "SELECT public_id FROM users WHERE user_id != ? AND profile_completed=1 "
        f"AND public_id IS NOT NULL AND age = ? AND last_seen >= ?{clause} "
        "ORDER BY last_seen DESC LIMIT ?"
    )
    cur = await db.execute(sql, [str(viewer_uid), age, min_ts, *gparams, limit])
    rows = await cur.fetchall()
    return [r["public_id"] for r in rows]


async def search_same_province(viewer_uid, province, gfilter, recent_days=3, limit=500):
    province = (province or "").strip()
    if not province:
        return []
    db = _conn()
    min_ts = now_ts() - recent_days * 86400
    clause, gparams = _gender_clause(gfilter)
    sql = (
        "SELECT public_id FROM users WHERE user_id != ? AND profile_completed=1 "
        f"AND public_id IS NOT NULL AND province = ? AND last_seen >= ?{clause} "
        "ORDER BY last_seen DESC LIMIT ?"
    )
    cur = await db.execute(sql, [str(viewer_uid), province, min_ts, *gparams, limit])
    rows = await cur.fetchall()
    return [r["public_id"] for r in rows]


async def search_no_chat(viewer_uid, gfilter, online_minutes=15, limit=500):
    db = _conn()
    min_ts = now_ts() - online_minutes * 60
    clause, gparams = _gender_clause(gfilter)
    sql = (
        "SELECT public_id FROM users WHERE user_id != ? AND profile_completed=1 "
        f"AND public_id IS NOT NULL AND last_seen >= ? AND chat_with IS NULL{clause} "
        "ORDER BY last_seen DESC LIMIT ?"
    )
    cur = await db.execute(sql, [str(viewer_uid), min_ts, *gparams, limit])
    rows = await cur.fetchall()
    return [r["public_id"] for r in rows]


async def search_new_users(viewer_uid, gfilter, days=7, limit=500):
    db = _conn()
    min_ts = now_ts() - days * 86400
    clause, gparams = _gender_clause(gfilter)
    sql = (
        "SELECT public_id FROM users WHERE user_id != ? AND profile_completed=1 "
        f"AND public_id IS NOT NULL AND created_at >= ?{clause} "
        "ORDER BY created_at DESC LIMIT ?"
    )
    cur = await db.execute(sql, [str(viewer_uid), min_ts, *gparams, limit])
    rows = await cur.fetchall()
    return [r["public_id"] for r in rows]


async def search_advanced(viewer_uid, gfilter, provinces, near, viewer_gps, limit=500, near_radius_km=25):
    db = _conn()
    clause, gparams = _gender_clause(gfilter)
    province_clause, province_params = "", []
    if provinces:
        placeholders = ",".join("?" for _ in provinces)
        province_clause = f" AND province IN ({placeholders})"
        province_params = list(provinces)

    if near:
        if viewer_gps.get("lat") is None or viewer_gps.get("lon") is None:
            return []
        sql = (
            "SELECT public_id, last_seen, gps_lat, gps_lon FROM users "
            "WHERE user_id != ? AND profile_completed=1 AND public_id IS NOT NULL "
            f"AND gps_lat IS NOT NULL AND gps_lon IS NOT NULL{clause}{province_clause}"
        )
        cur = await db.execute(sql, [str(viewer_uid), *gparams, *province_params])
        rows = await cur.fetchall()
        scored = []
        for r in rows:
            try:
                km = haversine_km(float(viewer_gps["lat"]), float(viewer_gps["lon"]), float(r["gps_lat"]), float(r["gps_lon"]))
            except Exception:
                continue
            if km > near_radius_km:
                continue
            scored.append((km, -safe_int(r["last_seen"] or 0, 0), r["public_id"]))
        scored.sort(key=lambda x: (x[0], x[1]))
        return [pid for _, _, pid in scored[:limit]]

    sql = (
        "SELECT public_id FROM users WHERE user_id != ? AND profile_completed=1 "
        f"AND public_id IS NOT NULL{clause}{province_clause} "
        "ORDER BY last_seen DESC LIMIT ?"
    )
    cur = await db.execute(sql, [str(viewer_uid), *gparams, *province_params, limit])
    rows = await cur.fetchall()
    return [r["public_id"] for r in rows]


async def search_nearby_candidates(viewer_uid, gfilter, viewer_gps, radius_km=25, limit=60):
    """کاندیدهای نزدیک (مرتب بر اساس فاصله)، بدون فیلتر بلاک (در handler فیلتر می‌شود)."""
    db = _conn()
    if viewer_gps.get("lat") is None or viewer_gps.get("lon") is None:
        return []
    clause, gparams = _gender_clause(gfilter)
    sql = (
        "SELECT public_id, last_seen, gps_lat, gps_lon FROM users "
        "WHERE user_id != ? AND profile_completed=1 AND public_id IS NOT NULL "
        f"AND gps_lat IS NOT NULL AND gps_lon IS NOT NULL{clause}"
    )
    cur = await db.execute(sql, [str(viewer_uid), *gparams])
    rows = await cur.fetchall()
    scored = []
    for r in rows:
        try:
            km = haversine_km(float(viewer_gps["lat"]), float(viewer_gps["lon"]), float(r["gps_lat"]), float(r["gps_lon"]))
        except Exception:
            continue
        if km > radius_km:
            continue
        scored.append((km, -safe_int(r["last_seen"] or 0, 0), r["public_id"]))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [pid for _, _, pid in scored[:limit]]


# ---------------------------------------------------------------------------
# آمار روزانه
# ---------------------------------------------------------------------------
async def ensure_stats_days():
    db = _conn()
    for d in (today_str(), day_str_plus(1), day_str_plus(2)):
        await db.execute(
            "INSERT INTO stats (day) VALUES (?) ON CONFLICT(day) DO NOTHING", (d,)
        )
    await db.commit()


async def inc_stat(key: str, amount: int = 1, day: str = None):
    if key not in GLOBAL_STAT_KEYS:
        return
    db = _conn()
    d = day or today_str()
    await db.execute(
        f"INSERT INTO stats (day, {key}) VALUES (?, ?) "
        f"ON CONFLICT(day) DO UPDATE SET {key} = {key} + excluded.{key}",
        (d, amount),
    )
    await db.commit()


async def get_stats_day(day: str) -> dict:
    db = _conn()
    cur = await db.execute("SELECT * FROM stats WHERE day = ?", (day,))
    row = await cur.fetchone()
    if not row:
        return {k: 0 for k in GLOBAL_STAT_KEYS}
    return {k: row[k] for k in GLOBAL_STAT_KEYS}


async def render_stats_text() -> str:
    await ensure_stats_days()
    t, f, p = today_str(), day_str_plus(1), day_str_plus(2)

    async def fmt_day(d):
        s = await get_stats_day(d)
        return (
            f"📅 *{d}*\n"
            f"├ 👤 کاربران جدید: *{s['new_users']}*\n"
            f"├ 💬 شروع چت‌ها: *{s['chats_started']}*\n"
            f"├ 🕵️ پیام‌های ناشناس: *{s['anon_messages']}*\n"
            f"├ 🏙 پیام‌های همشهری: *{s['local_messages']}*\n"
            f"├ ⚧ پیام‌های فیلتر جنسیت/رندوم: *{s['gender_messages']}*\n"
            f"└ ✅ پروفایل‌های تکمیل‌شده: *{s['profile_completed']}*\n"
        )

    total_users = await count_total_users()
    return (
        "📊 *آمار ربات*\n\n"
        f"👥 *کل اعضا:* {total_users}\n\n"
        f"{await fmt_day(t)}\n"
        f"{await fmt_day(f)}\n"
        f"{await fmt_day(p)}"
    )


# ---------------------------------------------------------------------------
# جوین اجباری
# ---------------------------------------------------------------------------
async def get_force_join_channels() -> list:
    db = _conn()
    cur = await db.execute("SELECT * FROM force_join_channels ORDER BY id ASC LIMIT 10")
    rows = await cur.fetchall()
    return [
        {
            "id": r["id"], "chat_id": r["chat_id"], "title": r["title"],
            "bot_is_admin": bool(r["bot_is_admin"]), "bot_can_invite": bool(r["bot_can_invite"]),
            "invite_link": r["invite_link"],
        }
        for r in rows
    ]


async def add_force_join_channel(chat_id, title, bot_is_admin, bot_can_invite, invite_link=None):
    db = _conn()
    await db.execute(
        "INSERT INTO force_join_channels (chat_id, title, bot_is_admin, bot_can_invite, invite_link, created_at) "
        "VALUES (?,?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET "
        "title=excluded.title, bot_is_admin=excluded.bot_is_admin, "
        "bot_can_invite=excluded.bot_can_invite, invite_link=excluded.invite_link",
        (str(chat_id), title, int(bool(bot_is_admin)), int(bool(bot_can_invite)), invite_link, now_ts()),
    )
    await db.commit()


async def remove_force_join_channel(channel_id: int):
    db = _conn()
    await db.execute("DELETE FROM force_join_channels WHERE id = ?", (channel_id,))
    await db.commit()


async def clear_force_join_channels():
    db = _conn()
    await db.execute("DELETE FROM force_join_channels")
    await db.commit()


async def count_force_join_channels() -> int:
    db = _conn()
    cur = await db.execute("SELECT COUNT(*) AS c FROM force_join_channels")
    row = await cur.fetchone()
    return row["c"] if row else 0


# ---------------------------------------------------------------------------
# درخواست‌های چت
# ---------------------------------------------------------------------------
async def create_chat_request(req_id, from_uid, to_uid):
    db = _conn()
    await db.execute(
        "INSERT INTO chat_requests (req_id, from_uid, to_uid, created_at, status) VALUES (?,?,?,?,?)",
        (req_id, str(from_uid), str(to_uid), now_ts(), "pending"),
    )
    await db.commit()


async def get_chat_request(req_id) -> Optional[dict]:
    db = _conn()
    cur = await db.execute("SELECT * FROM chat_requests WHERE req_id = ?", (req_id,))
    row = await cur.fetchone()
    if not row:
        return None
    return dict(row)


async def update_chat_request_status(req_id, status):
    db = _conn()
    await db.execute("UPDATE chat_requests SET status = ? WHERE req_id = ?", (status, req_id))
    await db.commit()


# ---------------------------------------------------------------------------
# پرداخت‌ها
# ---------------------------------------------------------------------------
async def create_payment(tx: dict):
    db = _conn()
    await db.execute(
        "INSERT INTO payments (tx_id, buyer_uid, buyer_pid, coins, price, file_id, ocr_text, status, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            tx["tx_id"], str(tx.get("buyer_uid")), tx.get("buyer_pid"), safe_int(tx.get("coins"), 0),
            safe_int(tx.get("price"), 0), tx.get("file_id"), tx.get("ocr_text"), tx.get("status", "pending"),
            tx.get("created_at") or now_ts(),
        ),
    )
    await db.commit()


async def get_payment(tx_id) -> Optional[dict]:
    db = _conn()
    cur = await db.execute("SELECT * FROM payments WHERE tx_id = ?", (tx_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def update_payment_status(tx_id, status, reviewed_at=None):
    db = _conn()
    await db.execute(
        "UPDATE payments SET status = ?, reviewed_at = ? WHERE tx_id = ?",
        (status, reviewed_at or now_ts(), tx_id),
    )
    await db.commit()


async def list_recent_payments(limit=15) -> list:
    db = _conn()
    cur = await db.execute("SELECT * FROM payments ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = await cur.fetchall()
    return [dict(r) for r in rows]
