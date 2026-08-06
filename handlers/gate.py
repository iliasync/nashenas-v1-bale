"""
میدلورِ سراسری (Global Gate).

این ماژول باید قبل از همه‌ی ماژول‌های دیگر handlers ایمپورت شود چون دو
هندلرِ بدون-شرط (on_message / on_callback_query بدون condition) را اول از
همه ثبت می‌کند. منطق بله‌تون این‌طور است که هندلرها به ترتیب ثبت‌شدن بررسی
می‌شوند و وقتی شرطِ یک هندلر True باشد و خودِ تابع بدون خطا برگردد، دیسپچ
برای همان آپدیت متوقف می‌شود (break). اگر تابع استثنای ContinueDispatching
را پرتاب کند، دیسپچر سراغ هندلر بعدی می‌رود — دقیقاً معادل رفتار
`if ...: ... ; continue` در حلقه‌ی polling نسخه‌ی اصلی.

کارهایی که اینجا انجام می‌شود (دقیقاً مثل ابتدای حلقه‌ی نسخه‌ی اصلی):
    1) ساخت/آپدیت رکورد کاربر + ثبت last_seen + شمارش new_users
    2) اگر کاربر بن شده (و ادمین نیست) → سکوت کامل
    3) اگر «جوین اجباری» لازم است → نمایش گیت و توقف
"""
from balethon.errors import ContinueDispatching
from balethon.conditions import private

import database as db
import force_join as fj
import keyboards as kb
from bot_instance import bot
from filters import set_event_user, is_admin_id
from utils import now_ts

MAIN_MENU_TEXTS = {
    "🔗 به یه ناشناس وصلم کن!️",
    "🔍 جستجوی کاربران 🔎",
    "📍افراد نزدیک",
    "👤پروفایل",
    "💰سکه بات",
    "🤔راهنما",
    "🚸 معرفی به دوستان (سکه رایگان)",
    "لینک ناشناس من 📬",
}

ALLOWED_MAIN_COMMANDS = {
    "/start", "/help", "/ghavanin", "/help_chat", "/help_credit", "/help_gps",
    "/help_profile", "/help_sendchat", "/help_direct", "/help_shortcuts",
    "/help_onw", "/help_chw", "/help_contacts", "/help_search",
    "/help_deleteMessage", "/profile", "/credit", "/link", "/contacts",
}


async def _touch_user(author):
    uid = str(author.id)
    user = await db.get_user(uid)
    if user.get("created_at") is None:
        user["created_at"] = now_ts()
        await db.inc_stat("new_users", 1)
    await db.ensure_unique_public_id(uid)
    user["last_seen"] = now_ts()
    await db.save_user(uid, user)
    await db.ensure_stats_days()
    return uid, user


@bot.on_message(private)
async def _global_message_gate(client, message):
    if not message.author:
        raise ContinueDispatching()

    uid, user = await _touch_user(message.author)
    set_event_user(message, user)

    if user.get("bot_banned") and not is_admin_id(uid):
        return  # سکوت کامل برای کاربران بن‌شده

    txt = (message.text or "").strip()
    is_main_command = txt.split(maxsplit=1)[0] in ALLOWED_MAIN_COMMANDS if txt.startswith("/") else False
    if (
        user.get("profile_completed", False)
        and user.get("state") is None
        and not user.get("chat_with")
        and (txt in MAIN_MENU_TEXTS or is_main_command)
        and await fj.force_join_gate_needed_for_user(client, uid)
    ):
        await fj.send_force_join_gate(client, message.chat.id, reply_to_message_id=message.id)
        return

    raise ContinueDispatching()


@bot.on_callback_query(private)
async def _global_callback_gate(client, callback_query):
    if not callback_query.author:
        raise ContinueDispatching()

    uid, user = await _touch_user(callback_query.author)
    set_event_user(callback_query, user)

    if user.get("bot_banned") and not is_admin_id(uid):
        await callback_query.answer(None)
        return

    data = (callback_query.data or "").strip()
    if (
        data != "forcejoin_check"
        and user.get("profile_completed", False)
        and user.get("state") is None
        and not user.get("chat_with")
        and await fj.force_join_gate_needed_for_user(client, uid)
    ):
        try:
            await callback_query.answer("اول عضویت را تایید کن ✅", show_alert=False)
        except Exception:
            pass
        await fj.send_force_join_gate(client, callback_query.message.chat.id, reply_to_message_id=callback_query.message.id)
        return

    raise ContinueDispatching()


@bot.on_callback_query(private)
async def _on_forcejoin_check(client, callback_query):
    if (callback_query.data or "") != "forcejoin_check":
        raise ContinueDispatching()
    await callback_query.answer(None)
    uid = str(callback_query.author.id)
    if await fj.force_join_gate_needed_for_user(client, uid):
        await fj.send_force_join_gate(client, callback_query.message.chat.id)
    else:
        user = await db.get_user(uid, create_if_missing=False)
        if user and not user.get("profile_completed", False):
            state = user.get("state")
            if state == "awaiting_age":
                from handlers.registration import ask_age
                await ask_age(client, callback_query.message.chat.id, user, reply_to_message_id=callback_query.message.id)
            elif state == "awaiting_province":
                from handlers.registration import ask_province
                await ask_province(client, callback_query.message.chat.id, user, reply_to_message_id=callback_query.message.id)
            elif state == "awaiting_gender":
                from handlers.registration import start_registration
                first_name = callback_query.author.first_name or ""
                await start_registration(
                    client, callback_query.message.chat.id, first_name, user,
                    reply_to_message_id=callback_query.message.id,
                )
            return
        await client.send_message(
            callback_query.message.chat.id,
            "✅ عضویت شما تایید شد.\nبه منوی اصلی برگشتید.",
            reply_markup=kb.kb_main_menu(),
        )
