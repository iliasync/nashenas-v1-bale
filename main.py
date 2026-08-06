"""
نقطه‌ی ورود ربات «چت ناشناس» — نسخه‌ی async با بله‌تون (Balethon) و SQLite.

اجرا:
    python main.py
"""
import asyncio
import os

import config
import database as db
from bot_instance import bot
import handlers  # noqa: F401  — ایمپورت بسته‌ی هندلرها (تمام دکوریتورها این‌جا ثبت می‌شوند)
from background import periodic_cleanup_loop


@bot.on_initialize()
async def _on_startup(client):
    await db.init_db()
    asyncio.create_task(periodic_cleanup_loop(client))
    print(
        "✅ ربات چت ناشناس↑cₕₐₜ راه‌اندازی شد "
        f"(pid={os.getpid()}, build={config.BUILD_MARKER}, file={os.path.abspath(__file__)})"
    )


@bot.on_shutdown()
async def _on_shutdown(client):
    await db.close_db()
    print("⏹ ربات متوقف شد.")


if __name__ == "__main__":
    bot.run()
