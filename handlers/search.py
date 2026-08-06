"""جستجوی کاربران (هم‌سنی، هم‌استانی، بدون‌چت، جدیدها، جستجوی پیشرفته)."""
from datetime import datetime

from balethon.conditions import equals, regex, private

import config
import database as db
import keyboards as kb
from bot_instance import bot
from filters import get_event_user
from profile_common import show_user_profile_by_pid
from utils import safe_int, last_seen_text

TITLE_MAP = {
    "same_age": "لیست افراد هم سن شما که در 3 روز اخیر آنلاین بوده اند",
    "same_province": "لیست افراد هم استانی شما که در 3 روز اخیر آنلاین بوده اند",
    "no_chat": "لیست کاربران آنلاین بدون چت",
    "new_users": "لیست کاربران جدید (۷ روز اخیر)",
    "adv": "نتایج جستجوی پیشرفته",
}


async def render_search_list_text(results, title, searched_at=None):
    searched_at = searched_at or datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"👥 *{title}*\n"]
    if not results:
        lines.append("❌ نتیجه‌ای یافت نشد.")
        lines.append(f"\nجستجو شده در {searched_at}")
        return "\n".join(lines)

    lines.append("👀 برای مشاهده پروفایل هر نفر، روی /user_ کلیک کن یا از دکمه «مشاهده بصورت کشویی» استفاده کن.\n")
    for i, pid in enumerate(results[:10], start=1):
        _, tu = await db.get_user_by_public_id(pid)
        if not tu:
            continue
        gender_emoji = "🙎‍♂️" if tu.get("gender") == "male" else ("🙎‍♀️" if tu.get("gender") == "female" else "❓")
        nm = (tu.get("display_name") or "❓").strip()
        age = tu.get("age") or "—"
        prov = tu.get("province") or "—"
        ls = last_seen_text(tu)
        lines.append(f"{i}. {gender_emoji} {nm} /user_{pid}\n{age} {prov}\nهم اکنون  {ls}\n")
        lines.append("〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️")
    lines.append(f"\nجستجو شده در {searched_at}")
    return "\n".join(lines)


def adv_gender_label(g):
    if g == "male":
        return "🙎‍♂️ پسر"
    if g == "female":
        return "🙎‍♀️ دختر"
    return "👫 همه"


def render_adv_province_text(user: dict) -> str:
    s = user.get("search") or {}
    g = adv_gender_label(s.get("adv_gender") or "all")
    sel = s.get("adv_selected_provinces") or []
    near = bool(s.get("adv_near_me", False))
    sel_txt = "، ".join(sel) if sel else "—"
    near_txt = "✅ فعال" if near else "❌ غیرفعال"
    return (
        f"👫 جنسیت : [{g}]\n\n"
        f"🎌 استان های انتخاب شده  : [{sel_txt}]\n\n"
        f"📍 افراد نزدیک من : [{near_txt}]\n\n"
        "استان های مورد نظرتو انتخاب کن و در آخر گزینه «➡️ مرحله بعدی » رو بزن 👇"
    )


# ---------------------------------------------------------------------------
# ورود به منوی جستجو
# ---------------------------------------------------------------------------
@bot.on_message(equals("🔍 جستجوی کاربران 🔎") & private)
async def msg_search_main_button(client, message):
    user = await get_event_user(message)
    m = await client.send_message(
        message.chat.id, "🔎 *جستجوی کاربران   زون*\n\nیکی از گزینه‌ها را انتخاب کن 👇",
        reply_markup=kb.ikb_search_main(), reply_to_message_id=message.id,
    )
    if m:
        user["search"]["last_meta"] = {"root_msg_id": m.id}
        await db.save_user(message.chat.id, user)


@bot.on_callback_query(equals("search_back_mainmenu") & private)
async def cb_search_back_mainmenu(client, callback_query):
    await callback_query.answer(None)
    chat_id = callback_query.message.chat.id
    await client.edit_message_text(chat_id, callback_query.message.id, "🏠 بازگشت به منوی اصلی.")
    await client.send_message(chat_id, "منوی اصلی:", reply_markup=kb.kb_main_menu())


@bot.on_callback_query(equals("search_back_root") & private)
async def cb_search_back_root(client, callback_query):
    await callback_query.answer(None)
    await client.edit_message_text(
        callback_query.message.chat.id, callback_query.message.id,
        "🔎 *جستجوی کاربران   زون*\n\nیکی از گزینه‌ها را انتخاب کن 👇", reply_markup=kb.ikb_search_main(),
    )


@bot.on_callback_query(equals("search_same_age") & private)
async def cb_search_same_age(client, callback_query):
    await callback_query.answer(None)
    await client.edit_message_text(
        callback_query.message.chat.id, callback_query.message.id,
        "👥 *هم سنی‌ها*\n\nجنسیت را انتخاب کن 👇", reply_markup=kb.ikb_search_gender_pick("same_age"),
    )


@bot.on_callback_query(equals("search_same_province") & private)
async def cb_search_same_province(client, callback_query):
    await callback_query.answer(None)
    await client.edit_message_text(
        callback_query.message.chat.id, callback_query.message.id,
        "🏳 *هم استانی‌ها*\n\nجنسیت را انتخاب کن 👇", reply_markup=kb.ikb_search_gender_pick("same_province"),
    )


@bot.on_callback_query(equals("search_no_chat") & private)
async def cb_search_no_chat(client, callback_query):
    await callback_query.answer(None)
    await client.edit_message_text(
        callback_query.message.chat.id, callback_query.message.id,
        "🚶‍♂ *بدون چت‌ها (آنلاین‌های بدون چت)*\n\nجنسیت را انتخاب کن 👇", reply_markup=kb.ikb_search_gender_pick("no_chat"),
    )


@bot.on_callback_query(equals("search_new_users") & private)
async def cb_search_new_users(client, callback_query):
    await callback_query.answer(None)
    await client.edit_message_text(
        callback_query.message.chat.id, callback_query.message.id,
        "👦👧 *کاربران جدید*\n\nجنسیت را انتخاب کن 👇", reply_markup=kb.ikb_search_gender_pick("new_users"),
    )


@bot.on_callback_query(equals("search_advanced") & private)
async def cb_search_advanced(client, callback_query):
    await callback_query.answer(None)
    await client.edit_message_text(
        callback_query.message.chat.id, callback_query.message.id,
        "🔍 *جستجوی پیشرفته*\n\nابتدا جنسیت را انتخاب کن 👇", reply_markup=kb.ikb_adv_gender_pick(),
    )


@bot.on_callback_query(regex(r"^search_back_category:") & private)
async def cb_search_back_category(client, callback_query):
    await callback_query.answer(None)
    meta = callback_query.data.split(":", 1)[1]
    chat_id, mid = callback_query.message.chat.id, callback_query.message.id
    mapping = {
        "same_age": ("👥 *هم سنی‌ها*\n\nجنسیت را انتخاب کن 👇", kb.ikb_search_gender_pick("same_age")),
        "same_province": ("🏳 *هم استانی‌ها*\n\nجنسیت را انتخاب کن 👇", kb.ikb_search_gender_pick("same_province")),
        "no_chat": ("🚶‍♂ *بدون چت‌ها*\n\nجنسیت را انتخاب کن 👇", kb.ikb_search_gender_pick("no_chat")),
        "new_users": ("👦👧 *کاربران جدید*\n\nجنسیت را انتخاب کن 👇", kb.ikb_search_gender_pick("new_users")),
        "adv": ("🔍 *جستجوی پیشرفته*\n\nابتدا جنسیت را انتخاب کن 👇", kb.ikb_adv_gender_pick()),
    }
    text, markup = mapping.get(meta, ("🔎 *جستجوی کاربران   زون*\n\nیکی از گزینه‌ها را انتخاب کن 👇", kb.ikb_search_main()))
    await client.edit_message_text(chat_id, mid, text, reply_markup=markup)


# ---------------------------------------------------------------------------
# اجرای جستجوهای ساده (هم‌سنی/هم‌استانی/بدون‌چت/جدیدها)
# ---------------------------------------------------------------------------
@bot.on_callback_query(regex(r"^(same_age|same_province|no_chat|new_users):gender:") & private)
async def cb_search_gender_result(client, callback_query):
    await callback_query.answer(None)
    prefix, _, g = callback_query.data.split(":")
    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id

    if prefix == "same_age":
        results = await db.search_same_age(chat_id, user.get("age"), g)
    elif prefix == "same_province":
        results = await db.search_same_province(chat_id, user.get("province"), g)
    elif prefix == "no_chat":
        results = await db.search_no_chat(chat_id, g)
    else:
        results = await db.search_new_users(chat_id, g)

    user["search"]["last_results"] = results
    user["search"]["last_meta"] = {"key": prefix, "gender": g}
    user["search"]["show_dropdown"] = False
    await db.save_user(chat_id, user)

    title = TITLE_MAP.get(prefix, "نتایج")
    text_out = await render_search_list_text(results[:10], title)
    await client.edit_message_text(
        chat_id, callback_query.message.id, text_out,
        reply_markup=kb.ikb_search_results(prefix, 1, len(results), dropdown=False, results=results),
    )


# ---------------------------------------------------------------------------
# جستجوی پیشرفته
# ---------------------------------------------------------------------------
@bot.on_callback_query(regex(r"^adv_gender:") & private)
async def cb_adv_gender(client, callback_query):
    await callback_query.answer(None)
    g = callback_query.data.split(":", 1)[1].strip()
    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id
    user["search"]["adv_gender"] = g
    user["search"]["adv_selected_provinces"] = []
    user["search"]["adv_near_me"] = False
    await db.save_user(chat_id, user)
    await client.edit_message_text(
        chat_id, callback_query.message.id, render_adv_province_text(user), reply_markup=kb.ikb_adv_province_select(user)
    )


@bot.on_callback_query(regex(r"^adv_prov_toggle:") & private)
async def cb_adv_prov_toggle(client, callback_query):
    await callback_query.answer(None)
    prov = callback_query.data.split(":", 1)[1]
    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id
    sel = [x for x in (user["search"].get("adv_selected_provinces") or []) if x in config.PROVINCES]
    if prov in sel:
        sel = [x for x in sel if x != prov]
    else:
        sel.append(prov)
    user["search"]["adv_selected_provinces"] = sel
    await db.save_user(chat_id, user)
    await client.edit_message_text(
        chat_id, callback_query.message.id, render_adv_province_text(user), reply_markup=kb.ikb_adv_province_select(user)
    )


@bot.on_callback_query(equals("adv_prov_all") & private)
async def cb_adv_prov_all(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id
    user["search"]["adv_selected_provinces"] = config.PROVINCES[:]
    await db.save_user(chat_id, user)
    await client.edit_message_text(
        chat_id, callback_query.message.id, render_adv_province_text(user), reply_markup=kb.ikb_adv_province_select(user)
    )


@bot.on_callback_query(equals("adv_near_toggle") & private)
async def cb_adv_near_toggle(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id
    user["search"]["adv_near_me"] = not bool(user["search"].get("adv_near_me", False))
    await db.save_user(chat_id, user)
    await client.edit_message_text(
        chat_id, callback_query.message.id, render_adv_province_text(user), reply_markup=kb.ikb_adv_province_select(user)
    )


@bot.on_callback_query(equals("adv_prov_next") & private)
async def cb_adv_prov_next(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id
    s = user.get("search") or {}
    gfilter = s.get("adv_gender") or "all"
    provinces = s.get("adv_selected_provinces") or []
    near = bool(s.get("adv_near_me", False))

    results = await db.search_advanced(
        chat_id, gfilter, provinces, near, user.get("gps") or {}, near_radius_km=config.NEAR_RADIUS_KM
    )
    user["search"]["last_results"] = results
    user["search"]["last_meta"] = {"key": "adv", "gender": gfilter, "provinces": provinces, "near": near}
    user["search"]["show_dropdown"] = False
    await db.save_user(chat_id, user)

    text_out = await render_search_list_text(results[:10], TITLE_MAP["adv"])
    await client.edit_message_text(
        chat_id, callback_query.message.id, text_out,
        reply_markup=kb.ikb_search_results("adv", 1, len(results), dropdown=False, results=results),
    )


# ---------------------------------------------------------------------------
# صفحه‌بندی / حالت کشویی / باز کردن پروفایل از نتایج
# ---------------------------------------------------------------------------
@bot.on_callback_query(regex(r"^search_page:") & private)
async def cb_search_page(client, callback_query):
    await callback_query.answer(None)
    _, meta_key, page_s = callback_query.data.split(":", 2)
    page = safe_int(page_s, 1)
    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id
    results = (user.get("search") or {}).get("last_results") or []
    total = len(results)
    title = TITLE_MAP.get(meta_key, "نتایج")
    chunk = results[(page - 1) * 10: (page - 1) * 10 + 10]
    text_out = await render_search_list_text(chunk, title)
    dropdown = bool((user.get("search") or {}).get("show_dropdown", False))
    await client.edit_message_text(
        chat_id, callback_query.message.id, text_out,
        reply_markup=kb.ikb_search_results(meta_key, page, total, dropdown=dropdown, results=results),
    )


@bot.on_callback_query(regex(r"^search_dropdown:") & private)
async def cb_search_dropdown(client, callback_query):
    await callback_query.answer(None)
    _, meta_key, page_s, flag_s = callback_query.data.split(":")
    page = safe_int(page_s, 1)
    flag = safe_int(flag_s, 0)
    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id
    user["search"]["show_dropdown"] = bool(flag)
    await db.save_user(chat_id, user)

    results = user["search"].get("last_results") or []
    total = len(results)
    title = TITLE_MAP.get(meta_key, "نتایج")
    chunk = results[(page - 1) * 10: (page - 1) * 10 + 10]
    text_out = await render_search_list_text(chunk, title)
    await client.edit_message_text(
        chat_id, callback_query.message.id, text_out,
        reply_markup=kb.ikb_search_results(meta_key, page, total, dropdown=bool(flag), results=results),
    )


@bot.on_callback_query(regex(r"^search_open_user:") & private)
async def cb_search_open_user(client, callback_query):
    await callback_query.answer(None)
    pid = callback_query.data.split(":", 1)[1].strip()
    user = await get_event_user(callback_query)
    await show_user_profile_by_pid(client, callback_query.message.chat.id, user, pid)
