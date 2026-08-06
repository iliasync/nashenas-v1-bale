"""جریان ثبت/به‌روزرسانیِ موقعیت GPS کاربر."""
from balethon.conditions import equals,private

import config
import database as db
import keyboards as kb
from bot_instance import bot
from filters import get_event_user, state_is
from profile_common import maybe_reward_profile_completion
from utils import now_ts, safe_int


async def start_gps_flow(client, chat_id, user, reply_to_message_id=None):
    await client.send_message(
        chat_id,
        "⚠️ هنگام ارسال موقعیت مکانی مطمعن شوید GPS موبایل شما روشن است.\n\n"
        "✅ کسی قادر به دیدن موقعیت مکانی شما در ربات نخواهد بود...\n\n"
        "❓موقعیت GPS خود را ارسال کنید👇",
        reply_to_message_id=reply_to_message_id,
    )
    user["state"] = "awaiting_gps_location"
    await db.save_user(chat_id, user)
    await client.send_message(
        chat_id, "از دکمه زیر استفاده کن:", reply_markup=kb.kb_gps_request_menu(), reply_to_message_id=reply_to_message_id
    )


@bot.on_message(equals("✏️ تغییر موقعیت GPS") & private)
async def msg_edit_gps_button(client, message):
    user = await get_event_user(message)
    await start_gps_flow(client, message.chat.id, user, reply_to_message_id=message.id)


@bot.on_message(state_is("awaiting_gps_location") & private)
async def msg_gps_location_state(client, message):
    user = await get_event_user(message)
    chat_id = message.chat.id
    txt = (message.text or "").strip()

    if txt == "بازگشت 🔙":
        user["state"] = None
        await db.save_user(chat_id, user)
        await client.send_message(
            chat_id, "بازگشت انجام شد.", reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id
        )
        return

    if message.location is not None:
        lat = message.location.latitude
        lon = message.location.longitude
        if lat is None or lon is None:
            await client.send_message(chat_id, "⚠️ لوکیشن نامعتبر است. دوباره ارسال کن.", reply_to_message_id=message.id)
            return

        first_time = not user.get("gps_rewarded", False)
        user["gps"] = {"lat": float(lat), "lon": float(lon), "set_at": now_ts()}
        user["state"] = None

        if first_time:
            user["gps_rewarded"] = True
            user["coins"] = safe_int(user.get("coins", 0), 0) + config.GPS_FIRST_TIME_REWARD
            await db.save_user(chat_id, user)
            await client.send_message(
                chat_id,
                f"✅ موقعیت شما ثبت شد.\n\n🎉 تبریک! {config.GPS_FIRST_TIME_REWARD} سکه 💰 هدیه گرفتی.\n"
                f"💰 موجودی جدید: *{user['coins']}*",
                reply_markup=kb.kb_main_menu(),
                reply_to_message_id=message.id,
            )
        else:
            await db.save_user(chat_id, user)
            await client.send_message(
                chat_id, "✅ موقعیت شما بروزرسانی شد.", reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id
            )

        await maybe_reward_profile_completion(client, chat_id, user)
        return

    await client.send_message(
        chat_id, "❓ لطفاً از دکمه «ثبت موقعیت» استفاده کن.", reply_markup=kb.kb_gps_request_menu(), reply_to_message_id=message.id
    )


@bot.on_callback_query(equals("profile_show_gps") & private)
async def cb_profile_show_gps(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id
    gps = user.get("gps") or {}
    lat, lon = gps.get("lat"), gps.get("lon")
    if lat is None or lon is None:
        await client.send_message(
            chat_id,
            "⚠️ خطا : شما موقعیت مکانی خود را ثبت نکرده اید.\n\n"
            "با زدن گزینه 📍 ثبت موقعیت GPS  ، موقعیت خود را ثبت کرده و "
            f"{config.GPS_FIRST_TIME_REWARD} سکه 💰 دریافت کنید.👇",
        )
    else:
        try:
            await client.send_location(chat_id, latitude=lat, longitude=lon)
        except Exception as e:
            print(f"send_location failed: {e}")


@bot.on_callback_query(equals("nearby_set_gps") & private)
async def cb_nearby_set_gps(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    await start_gps_flow(client, callback_query.message.chat.id, user, reply_to_message_id=callback_query.message.id)
