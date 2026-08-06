"""
نمونه‌ی مشترکِ Client بله‌تون.
همه‌ی ماژول‌های handlers این آبجکت را ایمپورت می‌کنند و با دکوریتورهای
bot.on_message / bot.on_callback_query / bot.on_command هندلر ثبت می‌کنند.
"""
from balethon import Client

import config

bot = Client(config.BALE_BOT_TOKEN)

# دیکشنری‌های in-memory برای وضعیت‌های کاملاً موقتی (صف matchmaking، سشن‌های
# دوز و سنگ‌کاغذقیچی). این‌ها عمداً در دیتابیس ذخیره نمی‌شوند چون با هر ری‌استارت
# منطقاً باید از نو شروع شوند (دقیقاً مانند نسخه‌ی اصلی).
runtime = {
    "mm_queue": [],            # [{"uid":..., "mode":..., "near":..., "started_at":...}]
    "dooz_sessions": {},
    "dooz_user_session": {},
    "dooz_waiting_random": [],
    "dooz_session_counter": 0,
    "dooz_pair_next_starter": {},
    "dooz_link_requests": {},
    "dooz_link_request_counter": 0,
    "pending_chat_dooz_invites": {},
    "rps_sessions": {},
    "rps_user_session": {},
    "rps_waiting_random": [],
    "rps_session_counter": 0,
    "rps_link_requests": {},
    "rps_link_request_counter": 0,
    "pending_chat_rps_invites": {},
}
