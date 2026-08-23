"""
نقطه‌ی ورود ربات «چت ناشناس» — نسخه‌ی async با بله‌تون (Balethon) و SQLite.

اجرا:
    python main.py
"""
import asyncio
import os
import time

import config
import database as db
from bot_instance import bot
import handlers  # noqa: F401  — ایمپورت بسته‌ی هندلرها (تمام دکوریتورها این‌جا ثبت می‌شوند)
from background import periodic_cleanup_loop


@bot.on_initialize()
async def _on_startup(client):
    await db.init_db()
    asyncio.create_task(periodic_cleanup_loop(client))
    # اگر ربات وسط همگانی خاموش شده باشد، worker از checkpoint آخر ادامه می‌دهد.
    from handlers.admin import resume_pending_broadcasts
    await resume_pending_broadcasts(client)
    print(
        "✅ ربات چت ناشناس↑cₕₐₜ راه‌اندازی شد "
        f"(pid={os.getpid()}, build={config.BUILD_MARKER}, file={os.path.abspath(__file__)})"
    )


@bot.on_shutdown()
async def _on_shutdown(client):
    from handlers.admin import stop_broadcast_worker
    await stop_broadcast_worker()
    await db.close_db()
    print("⏹ ربات متوقف شد.")


if __name__ == "__main__":
    # خطای موقت شبکه/کتابخانه نباید کل پردازش را برای همیشه خاموش کند.
    # خودِ polling بعد از خطا با همان PID دوباره راه‌اندازی می‌شود.
    while True:
        try:
            bot.run()
            break
        except KeyboardInterrupt:
            break
        except Exception as exc:
            print(f"polling crashed; retrying: {type(exc).__name__}")
            time.sleep(5)
