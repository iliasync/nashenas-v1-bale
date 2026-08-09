"""دریافت جایزه‌ی تصادفی روزانه."""
from datetime import datetime, timedelta

from balethon.conditions import equals, private, regex

import database as db
import keyboards as kb
from bot_instance import bot
from filters import get_event_user


def _time_until_tomorrow() -> str:
    now = datetime.now()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    seconds = max(0, int((tomorrow - now).total_seconds()))
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    return f"{hours} ساعت و {minutes} دقیقه"


def _luck_title(reward: int, minimum: int, maximum: int) -> str:
    if reward == maximum and maximum > minimum:
        return "💎 جک‌پات روزانه!"
    span = max(1, maximum - minimum)
    position = (reward - minimum) / span
    if position >= 0.75:
        return "🔥 امروز خیلی خوش‌شانس بودی!"
    if position >= 0.4:
        return "✨ جایزه‌ی خوبی بردی!"
    return "🌱 جایزه‌ی امروزت آماده‌ست!"


async def _claim_and_respond(client, event, from_callback=False):
    user = await get_event_user(event)
    chat_id = event.message.chat.id if from_callback else event.chat.id
    result = await db.claim_daily_coin(event.author.id)
    if not result["claimed"]:
        text = (
            "⏳ *جایزه‌ی امروزت را قبلاً گرفتی!*\n\n"
            f"🪙 جایزه امروز: *{result['reward']}* سکه\n"
            f"🔥 زنجیره دریافت: *{result['streak']} روز*\n"
            f"⏰ فرصت بعدی تا حدود *{_time_until_tomorrow()}* دیگر"
        )
        if from_callback:
            await event.answer("جایزه امروزت را قبلاً گرفتی ⏳", show_alert=True)
        await client.send_message(chat_id, text, reply_markup=kb.kb_main_menu())
        return

    # کش رویداد موجودی قبل از claim را دارد؛ برای جلوگیری از ذخیره‌ی ناخواسته تازه‌سازی می‌کنیم.
    user["coins"] = result["balance"]
    title = _luck_title(result["reward"], result["minimum"], result["maximum"])
    text = (
        f"{title}\n\n"
        "🎁 صندوق امروز باز شد و...\n"
        f"🪙 *{result['reward']} سکه* برنده شدی!\n"
        f"💰 موجودی جدید: *{result['balance']} سکه*\n"
        f"🔥 زنجیره دریافت: *{result['streak']} روز*\n\n"
        "فردا دوباره برگرد و شانست رو امتحان کن 🍀"
    )
    if from_callback:
        await event.answer(f"+{result['reward']} سکه 🎉", show_alert=False)
    await client.send_message(chat_id, text, reply_markup=kb.kb_main_menu())


@bot.on_message(equals("🎁 سکه روزانه") & private)
async def msg_daily_coin(client, message):
    await _claim_and_respond(client, message)


@bot.on_command(name="daily", min_arguments=0, max_arguments=0, condition=private)
async def cmd_daily_coin(client, message):
    await _claim_and_respond(client, message)


@bot.on_callback_query(regex(r"^daily_coin_claim$") & private)
async def cb_daily_coin(client, callback_query):
    await _claim_and_respond(client, callback_query, from_callback=True)
