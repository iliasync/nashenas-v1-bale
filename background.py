"""
تسک‌های دوره‌ای پس‌زمینه.

در نسخه‌ی اصلی این کارها داخل همان حلقه‌ی polling سینک، قبل از هر بار
`getUpdates`، صدا زده می‌شدند (`mm_cleanup_expired()` و
`cleanup_expired_rps_sessions()`). چون بله‌تون خودش polling را مدیریت
می‌کند، این‌ها را به‌صورت یک تسکِ async مستقل (با asyncio.sleep) اجرا
می‌کنیم که توسط `@bot.on_initialize()` در main.py استارت می‌شود.
"""
import asyncio

from handlers.matchmaking import mm_cleanup_expired
from handlers.rps import cleanup_expired_rps_sessions

CLEANUP_INTERVAL_SECONDS = 5


async def periodic_cleanup_loop(client):
    while True:
        try:
            await mm_cleanup_expired(client)
        except Exception as e:
            print(f"[background] mm_cleanup_expired error: {e}")
        try:
            await cleanup_expired_rps_sessions(client)
        except Exception as e:
            print(f"[background] cleanup_expired_rps_sessions error: {e}")
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
