"""افراد نزدیک (بر اساس GPS)."""
from balethon.conditions import equals, regex,private

import config
import database as db
import keyboards as kb
from bot_instance import bot
from filters import get_event_user
from profile_common import is_blocked_between
from utils import distance_text, last_seen_text


async def render_nearby_list(viewer_uid, viewer_user: dict, gender_filter="all", limit=12):
    vg = viewer_user.get("gps") or {}
    if vg.get("lat") is None or vg.get("lon") is None:
        return None, []

    candidates = await db.search_nearby_candidates(
        viewer_uid, gender_filter, vg, radius_km=config.NEARBY_RADIUS_KM, limit=limit * 5
    )
    pids = []
    for pid in candidates:
        _, tu = await db.get_user_by_public_id(pid)
        if not tu:
            continue
        if is_blocked_between(viewer_user, tu):
            continue
        pids.append(pid)
        if len(pids) >= limit:
            break

    gf = "👫 همه" if gender_filter == "all" else ("🙎‍♂️ فقط پسرها" if gender_filter == "male" else "🙍‍♀️ فقط دخترها")
    lines = [
        "📍 *افراد نزدیک شما*",
        "",
        f"🛰 فیلتر: {gf}",
        f"📏 شعاع: {config.NEARBY_RADIUS_KM} کیلومتر",
        "",
    ]
    if not pids:
        lines.append("❌ کسی نزدیک شما پیدا نشد.")
        return "\n".join(lines), pids

    for i, pid in enumerate(pids, start=1):
        _, tu = await db.get_user_by_public_id(pid)
        if not tu:
            continue
        nm = (tu.get("display_name") or "❓").strip()
        gender_emoji = "🙎‍♂️" if tu.get("gender") == "male" else ("🙎‍♀️" if tu.get("gender") == "female" else "❓")
        dist = distance_text(viewer_user, tu)
        ls = last_seen_text(tu)
        lines.append(f"{i}. {gender_emoji} {nm}  /user_{pid}\n🏁 فاصله: {dist}\n⏳ {ls}\n")
        lines.append("〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️")
    return "\n".join(lines), pids


@bot.on_message(equals("📍افراد نزدیک") & private)
async def msg_nearby_button(client, message):
    user = await get_event_user(message)
    m = await client.send_message(
        message.chat.id, "🛰 چه کسایی رو نشونت بدم؟ انتخاب کن👇", reply_markup=kb.ikb_nearby_pick(),
        reply_to_message_id=message.id,
    )
    if m:
        user["nearby_root_msg_id"] = m.id
        await db.save_user(message.chat.id, user)


@bot.on_callback_query(regex(r"^nearby_gender:") & private)
async def cb_nearby_gender(client, callback_query):
    await callback_query.answer(None)
    g = callback_query.data.split(":", 1)[1].strip()
    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id

    gps = user.get("gps") or {}
    if gps.get("lat") is None or gps.get("lon") is None:
        txt = (
            "انتظار نداری که بدون دونستن موقعیتت بتونم افراد نزدیکتو پیدا کنم؟\n\n"
            "⚠️ خطا: شما موقعیت مکانی خود را ثبت نکرده اید.\n\n"
            "با زدن گزینه 📍 ثبت موقعیت GPS  ، موقعیت خود را ثبت کنید 👇"
        )
        await client.edit_message_text(chat_id, callback_query.message.id, txt, reply_markup=kb.ikb_nearby_need_gps())
        return

    out_text, _ = await render_nearby_list(chat_id, user, gender_filter=g, limit=12)
    if not out_text:
        out_text = "⚠️ خطا در دریافت لیست."
    await client.edit_message_text(chat_id, callback_query.message.id, out_text, reply_markup=None)
