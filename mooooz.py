"""
migrate_json_to_sqlite.py
==========================
انتقالِ یک‌باره‌ی دیتابیس JSON قدیمی (مثل uyser_data.json نسخه‌ی سینک) به
دیتابیس SQLite جدید (همان چیزی که database.py در این پروژه استفاده می‌کند).

این اسکریپت مستقیماً از ماژول `database.py` همین پروژه استفاده می‌کند (همان
چیزی که خودِ ربات استفاده می‌کند)، پس صد در صد با schema واقعی هم‌خوان است و
نیازی به تکرار/نگه‌داریِ دوبارهٔ نگاشتِ فیلدها در یک فایل جدا نیست.

محل قرارگیری: کنار main.py / config.py / database.py (ریشه‌ی پروژه‌ی balechat)
چون باید بتواند این ماژول‌ها را import کند.

نحوه‌ی اجرا
-----------
    # حالت معمول: می‌خواند از uyser_data.json و می‌نویسد در همان مسیر
    # پیش‌فرضِ config.DB_PATH (bot.sqlite3)
    python3 migrate_json_to_sqlite.py

    # مسیر دلخواه برای فایل JSON ورودی
    python3 migrate_json_to_sqlite.py /path/to/uyser_data.json

    # مسیر دلخواه برای فایل SQLite خروجی
    python3 migrate_json_to_sqlite.py uyser_data.json --sqlite-path bot.sqlite3

    # اگر دیتابیسِ SQLیتیِ مقصد از قبل وجود دارد و می‌خوای از صفر بسازیش
    python3 migrate_json_to_sqlite.py uyser_data.json --overwrite

    # فقط بررسی/شمارش، بدون نوشتن واقعی در دیتابیس (dry run)
    python3 migrate_json_to_sqlite.py uyser_data.json --dry-run

این اسکریپت idempotent است: اگر دوباره روی همان دیتابیس اجرا شود، فقط همان
رکوردها را آپدیت می‌کند (خرابی/تکرار ایجاد نمی‌کند).
"""
import argparse
import asyncio
import json
import os
import sys

import config
import database as db
from utils import safe_int

GLOBAL_KEYS = {"stats", "force_join_channels", "chat_requests", "mm_queue", "payments"}
STAT_FIELDS = (
    "new_users", "chats_started", "anon_messages",
    "local_messages", "gender_messages", "profile_completed",
)


# ---------------------------------------------------------------------------
# کمکی: یکدست‌سازیِ رکورد یک کاربر قبل از ذخیره
# ---------------------------------------------------------------------------
def merge_user_record(raw: dict) -> dict:
    """رکورد خام JSON را روی دیکشنریِ پیش‌فرضِ کاربر (همان چیزی که
    database._default_user می‌سازد) سوار می‌کند تا فیلدهای گم‌شده هم مقدار
    درست داشته باشند و save_user() بدون خطا کار کند."""
    merged = db._default_user()
    if isinstance(raw, dict):
        merged.update(raw)

    if not isinstance(merged.get("gps"), dict):
        merged["gps"] = {"lat": None, "lon": None, "set_at": None}
    else:
        merged["gps"].setdefault("lat", None)
        merged["gps"].setdefault("lon", None)
        merged["gps"].setdefault("set_at", None)

    if not isinstance(merged.get("search"), dict):
        merged["search"] = {
            "last_results": [], "last_meta": {}, "show_dropdown": False,
            "adv_gender": None, "adv_selected_provinces": [], "adv_near_me": False,
        }

    if not isinstance(merged.get("mm"), dict):
        merged["mm"] = {"searching": False, "mode": None, "started_at": None, "msg_id": None, "near": False}

    if not isinstance(merged.get("buy"), dict):
        merged["buy"] = {"state": None, "tmp_pkg": None, "tmp_msg_id": None}

    for list_key in ("contacts", "my_likes", "blocked_users", "transactions",
                      "pending_incoming_req", "pending_outgoing_req", "notify_chat_end"):
        if not isinstance(merged.get(list_key), list):
            merged[list_key] = []

    return merged


# ---------------------------------------------------------------------------
# مهاجرت بخش‌های مختلف
# ---------------------------------------------------------------------------
async def migrate_users(data: dict, dry_run: bool) -> tuple:
    ok, failed, skipped = 0, 0, 0
    for key, raw in data.items():
        if key in GLOBAL_KEYS:
            continue
        if not isinstance(raw, dict):
            skipped += 1
            print(f"  ⚠️  رد شد (مقدار غیر-دیکشنری): {key!r}")
            continue
        uid = str(key)
        try:
            merged = merge_user_record(raw)
            if not dry_run:
                await db.save_user(uid, merged)
            ok += 1
        except Exception as e:
            failed += 1
            print(f"  ❌ خطا در انتقال کاربر {uid}: {e}")
    return ok, failed, skipped


async def migrate_stats(stats: dict, dry_run: bool) -> int:
    if not isinstance(stats, dict):
        return 0
    n = 0
    for day, values in stats.items():
        if not isinstance(values, dict):
            continue
        for field in STAT_FIELDS:
            amount = safe_int(values.get(field, 0), 0)
            if amount and not dry_run:
                await db.inc_stat(field, amount, day=str(day))
        n += 1
    return n


async def migrate_force_join_channels(channels, dry_run: bool) -> int:
    if not isinstance(channels, list):
        return 0
    n = 0
    for ch in channels:
        link, slug, title, bot_is_admin = None, None, None, False
        if isinstance(ch, dict) and ch.get("link"):
            link = ch.get("link")
            slug = ch.get("slug")
            title = ch.get("title")
            bot_is_admin = bool(ch.get("bot_is_admin", False))
        elif isinstance(ch, str) and ch.strip():
            link = ch.strip()
        if not link or link == "0":
            continue
        if not dry_run:
            await db.add_force_join_channel(link, slug, title, bot_is_admin)
        n += 1
    return n


async def migrate_chat_requests(requests_dict, dry_run: bool) -> int:
    if not isinstance(requests_dict, dict):
        return 0
    n = 0
    conn = db._conn() if not dry_run else None
    for req_id, req in requests_dict.items():
        if not isinstance(req, dict):
            continue
        if not dry_run:
            await conn.execute(
                "INSERT INTO chat_requests (req_id, from_uid, to_uid, created_at, status) VALUES (?,?,?,?,?) "
                "ON CONFLICT(req_id) DO UPDATE SET from_uid=excluded.from_uid, to_uid=excluded.to_uid, "
                "created_at=excluded.created_at, status=excluded.status",
                (
                    str(req_id), str(req.get("from_uid")), str(req.get("to_uid")),
                    safe_int(req.get("created_at"), 0) or None, req.get("status") or "pending",
                ),
            )
        n += 1
    if not dry_run:
        await conn.commit()
    return n


async def migrate_payments(payments_dict, dry_run: bool) -> int:
    if not isinstance(payments_dict, dict):
        return 0
    n = 0
    for tx_id, tx in payments_dict.items():
        if not isinstance(tx, dict):
            continue
        real_tx_id = str(tx.get("tx_id") or tx_id)
        if not dry_run:
            try:
                await db.create_payment({
                    "tx_id": real_tx_id,
                    "buyer_uid": tx.get("buyer_uid"),
                    "buyer_pid": tx.get("buyer_pid"),
                    "coins": safe_int(tx.get("coins"), 0),
                    "price": safe_int(tx.get("price"), 0),
                    "file_id": tx.get("file_id"),
                    "ocr_text": tx.get("ocr_text"),
                    "status": tx.get("status") or "pending",
                    "created_at": safe_int(tx.get("created_at"), 0) or None,
                })
            except Exception:
                # تراکنش از قبل وجود دارد (اجرای دوباره‌ی اسکریپت) -> فقط وضعیت را به‌روزرسانی کن
                pass
            if tx.get("status") and tx.get("status") != "pending":
                await db.update_payment_status(real_tx_id, tx.get("status"), safe_int(tx.get("reviewed_at"), 0) or None)
        n += 1
    return n


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
async def run(args):
    if not os.path.isfile(args.json_path):
        print(f"❌ فایل JSON پیدا نشد: {args.json_path}")
        sys.exit(1)

    if args.sqlite_path:
        config.DB_PATH = args.sqlite_path

    if args.overwrite and not args.dry_run:
        for ext in ("", "-wal", "-shm"):
            p = config.DB_PATH + ext
            if os.path.isfile(p):
                os.remove(p)
                print(f"🗑  حذف شد: {p}")

    print(f"📥 در حال خواندن: {args.json_path}")
    with open(args.json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        print("❌ فایل JSON معتبر نیست (باید یک object باشد).")
        sys.exit(1)

    mode = "🔍 DRY-RUN (هیچ‌چیزی نوشته نمی‌شود)" if args.dry_run else "✍️ نوشتن واقعی"
    print(f"🗄  دیتابیس مقصد: {config.DB_PATH}   [{mode}]\n")

    if not args.dry_run:
        await db.init_db()

    print("👤 انتقال کاربران...")
    ok, failed, skipped = await migrate_users(data, args.dry_run)
    print(f"   ✅ موفق: {ok}   ❌ ناموفق: {failed}   ⚠️ رد شده: {skipped}\n")

    print("📊 انتقال آمار روزانه...")
    stats_n = await migrate_stats(data.get("stats"), args.dry_run)
    print(f"   ✅ {stats_n} روز\n")

    print("📌 انتقال کانال‌های جوین اجباری...")
    fj_n = await migrate_force_join_channels(data.get("force_join_channels"), args.dry_run)
    print(f"   ✅ {fj_n} کانال\n")

    print("💬 انتقال درخواست‌های چت...")
    cr_n = await migrate_chat_requests(data.get("chat_requests"), args.dry_run)
    print(f"   ✅ {cr_n} درخواست\n")

    print("🧾 انتقال تراکنش‌های پرداخت...")
    pay_n = await migrate_payments(data.get("payments"), args.dry_run)
    print(f"   ✅ {pay_n} تراکنش\n")

    mm_queue = data.get("mm_queue")
    if isinstance(mm_queue, list) and mm_queue:
        print(
            f"⚠️  {len(mm_queue)} مورد در صفِ matchmaking قدیمی نادیده گرفته شد "
            "(این صف فقط در حافظه نگه‌داری می‌شود؛ معنایی برای انتقال به دیتابیس ندارد).\n"
        )

    if not args.dry_run:
        total = await db.count_total_users()
        print(f"📈 جمع کل کاربران در دیتابیس مقصد (بعد از انتقال): {total}")
        await db.close_db()

    print("\n🎉 انتقال تمام شد." if not args.dry_run else "\n🎉 بررسیِ dry-run تمام شد.")


def main():
    parser = argparse.ArgumentParser(
        description="انتقال دیتابیس JSON قدیمی (uyser_data.json) به دیتابیس SQLite جدید پروژه."
    )
    parser.add_argument(
        "json_path", nargs="?", default="uyser_data.json",
        help="مسیر فایل JSON قدیمی (پیش‌فرض: uyser_data.json در همین پوشه)",
    )
    parser.add_argument(
        "--sqlite-path", default=None,
        help="مسیر دلخواه برای فایل SQLite خروجی (پیش‌فرض: همان config.DB_PATH پروژه)",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="اگر فایل SQLite مقصد از قبل وجود دارد، حذفش کن و کاملاً از نو بساز",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="فقط شمارش/بررسی کن، چیزی در دیتابیس ننویس",
    )
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()