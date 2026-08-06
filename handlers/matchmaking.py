"""اتصال به یک ناشناس (Matchmaking): جستجوی شانسی / پسر / دختر / اطراف."""
from balethon.conditions import equals,private
from balethon.errors import ContinueDispatching

import config
import database as db
import keyboards as kb
from bot_instance import bot, runtime
from filters import get_event_user
from profile_common import is_blocked_between
from utils import haversine_km, now_ts, safe_int


async def _send_not_enough_coins(client, chat_id, balance, needed):
    await client.send_message(
        chat_id,
        "🪙 *موجودی سکه کافی نیست*\n\n"
        f"برای این نوع جستجو به *{needed}* سکه نیاز دارید.\n"
        f"موجودی فعلی شما: *{balance}* سکه\n\n"
        "جستجوی شانسی کاملاً رایگان است؛ اگر نمی‌خواهید سکه مصرف کنید، گزینه «🎲 جستجو شانسی (رایگان)» را بزنید.",
        reply_markup=kb.ikb_coin_buy_menu(),
    )


# ---------------------------------------------------------------------------
# منطق matchmaking (صف در حافظه + وضعیت mm در دیتابیس برای نمایش)
# ---------------------------------------------------------------------------
async def mm_is_compatible(a_uid, a_mode, a_near, b_uid, b_mode, b_near) -> bool:
    if str(a_uid) == str(b_uid):
        return False
    au = await db.get_user(a_uid, create_if_missing=False) or {}
    bu = await db.get_user(b_uid, create_if_missing=False) or {}
    if au.get("chat_with") or bu.get("chat_with"):
        return False
    if is_blocked_between(au, bu):
        return False
    if bool(a_near) != bool(b_near):
        return False

    a_gender = au.get("gender")
    b_gender = bu.get("gender")

    def wants_ok(mode, target_gender):
        if mode == "boy":
            return target_gender == "male"
        if mode == "girl":
            return target_gender == "female"
        return True

    if not wants_ok(a_mode, b_gender):
        return False
    if not wants_ok(b_mode, a_gender):
        return False

    if a_near and b_near:
        ag, bg = au.get("gps") or {}, bu.get("gps") or {}
        if ag.get("lat") is None or ag.get("lon") is None or bg.get("lat") is None or bg.get("lon") is None:
            return False
        try:
            km = haversine_km(float(ag["lat"]), float(ag["lon"]), float(bg["lat"]), float(bg["lon"]))
            if km > config.NEAR_RADIUS_KM:
                return False
        except Exception:
            return False

    return True


async def mm_try_match(client, new_uid) -> bool:
    new_uid = str(new_uid)
    nu = await db.get_user(new_uid, create_if_missing=False)
    if not nu or not (nu.get("mm") or {}).get("searching"):
        return False

    n_mode = (nu.get("mm") or {}).get("mode") or "random"
    n_near = bool((nu.get("mm") or {}).get("near", False))

    for it in list(runtime["mm_queue"]):
        ouid = str(it.get("uid") or "")
        if not ouid or ouid == new_uid:
            continue
        ou = await db.get_user(ouid, create_if_missing=False)
        if not ou or not (ou.get("mm") or {}).get("searching"):
            continue
        o_mode = (ou.get("mm") or {}).get("mode") or "random"
        o_near = bool((ou.get("mm") or {}).get("near", False))

        if await mm_is_compatible(new_uid, n_mode, n_near, ouid, o_mode, o_near):
            runtime["mm_queue"] = [x for x in runtime["mm_queue"] if str(x.get("uid")) not in (new_uid, ouid)]

            empty_mm = {"searching": False, "mode": None, "started_at": None, "msg_id": None, "near": False}
            nu["mm"] = dict(empty_mm)
            ou["mm"] = dict(empty_mm)
            await db.save_user(new_uid, nu)
            await db.save_user(ouid, ou)

            from handlers.chat import start_chat_between
            await start_chat_between(new_uid, ouid)

            for uid in (new_uid, ouid):
                try:
                    await client.send_message(
                        int(uid),
                        "✅ مخاطب پیدا شد.\n💬 شما به چت متصل شدید.\n\nبرای مدیریت چت از منوی پایین استفاده کن.",
                        reply_markup=kb.kb_chat_menu(),
                    )
                except Exception:
                    pass
            return True
    return False


async def mm_start_search(client, chat_id, user, mode="random", near=False, cost=0, info_gender_line=""):
    chat_id = str(chat_id)
    if user.get("chat_with"):
        await client.send_message(chat_id, "⚠️ شما درحال چت هستید.", reply_markup=kb.kb_chat_menu())
        return
    if (user.get("mm") or {}).get("searching"):
        await client.send_message(chat_id, "⚠️ شما همین الان درحال جستجو هستید.\nبرای لغو: «لغو»", reply_markup=kb.kb_cancel_only())
        return

    if cost > 0:
        balance = safe_int(user.get("coins", 0), 0)
        if balance < cost:
            await _send_not_enough_coins(client, chat_id, balance, cost)
            return
        user["coins"] = balance - cost

    if near:
        g = user.get("gps") or {}
        if g.get("lat") is None or g.get("lon") is None:
            await client.send_message(
                chat_id,
                "⚠️ برای «جستجو اطراف» باید GPS خود را ثبت کرده باشید.\nاز پروفایل → «✏️ تغییر موقعیت GPS»",
                reply_markup=kb.kb_main_menu(),
            )
            return

    user["mm"] = {"searching": True, "mode": mode, "near": bool(near), "started_at": now_ts(), "msg_id": None}
    await db.save_user(chat_id, user)

    runtime["mm_queue"] = [x for x in runtime["mm_queue"] if str(x.get("uid")) != chat_id]
    runtime["mm_queue"].append({"uid": chat_id, "mode": mode, "near": bool(near), "started_at": now_ts()})

    searching_text = (
        "🔎 درحال جستجوی مخاطب ناشناس شما\n"
        f"- {info_gender_line}\n\n"
        "⏳ حداکثر تا 2 دقیقه صبر کنید."
    )
    m = await client.send_message(chat_id, searching_text, reply_markup=kb.kb_cancel_only())
    if m:
        user["mm"]["msg_id"] = m.id
        await db.save_user(chat_id, user)

    await mm_try_match(client, chat_id)


async def mm_cancel_search(client, chat_id, user):
    chat_id = str(chat_id)
    if not (user.get("mm") or {}).get("searching"):
        await client.send_message(chat_id, "جستجویی فعال نیست.", reply_markup=kb.kb_main_menu())
        return
    user["mm"] = {"searching": False, "mode": None, "started_at": None, "msg_id": None, "near": False}
    await db.save_user(chat_id, user)
    runtime["mm_queue"] = [x for x in runtime["mm_queue"] if str(x.get("uid")) != chat_id]
    await client.send_message(chat_id, "✅ لغو شد.", reply_markup=kb.kb_main_menu())


async def mm_cleanup_expired(client):
    """فراخوانی دوره‌ای (در background.py) برای کنسل‌کردن جستجوهای منقضی‌شده."""
    keep = []
    for it in list(runtime["mm_queue"]):
        uid = str(it.get("uid") or "")
        st = safe_int(it.get("started_at") or 0, 0)
        if not uid or not st:
            continue
        if now_ts() - st >= config.MM_TIMEOUT:
            u = await db.get_user(uid, create_if_missing=False)
            if u:
                u["mm"] = {"searching": False, "mode": None, "started_at": None, "msg_id": None, "near": False}
                await db.save_user(uid, u)
                try:
                    await client.send_message(
                        int(uid), "⏳ زمان جستجو به پایان رسید.\nاز منوی اصلی دوباره تلاش کن.", reply_markup=kb.kb_main_menu()
                    )
                except Exception:
                    pass
            continue
        keep.append(it)
    runtime["mm_queue"] = keep


# ---------------------------------------------------------------------------
# هندلرها
# ---------------------------------------------------------------------------
@bot.on_message(equals("لغو") & private)
async def msg_cancel_text(client, message):
    user = await get_event_user(message)
    if (user.get("mm") or {}).get("searching"):
        await mm_cancel_search(client, message.chat.id, user)
        return
    raise ContinueDispatching()


@bot.on_message(equals("🔗 به یه ناشناس وصلم کن!️") & private)
async def msg_connect_anon_button(client, message):
    await client.send_message(
        message.chat.id,
        "به کی وصلت کنم؟ انتخاب کن👇\n\n🎲 جستجوی شانسی/تصادفی رایگانه.",
        reply_markup=kb.ikb_connect_menu(), reply_to_message_id=message.id
    )


@bot.on_callback_query(equals("mm_back") & private)
async def cb_mm_back(client, callback_query):
    await callback_query.answer(None)
    await client.send_message(
        callback_query.message.chat.id,
        "به کی وصلت کنم؟ انتخاب کن👇\n\n🎲 جستجوی شانسی/تصادفی رایگانه.",
        reply_markup=kb.ikb_connect_menu(),
    )


@bot.on_callback_query(equals("mm_near") & private)
async def cb_mm_near(client, callback_query):
    await callback_query.answer(None)
    await client.send_message(
        callback_query.message.chat.id, "🪃 جستحو اطراف\n\nیکی از گزینه‌ها را انتخاب کن 👇",
        reply_markup=kb.ikb_near_menu(), reply_to_message_id=callback_query.message.id,
    )


@bot.on_callback_query(equals("mm_random") & private)
async def cb_mm_random(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    await mm_start_search(client, callback_query.message.chat.id, user, mode="random", near=False, cost=0, info_gender_line="جستجو شانسی 🎲 (رایگان)")


@bot.on_callback_query(equals("mm_boy") & private)
async def cb_mm_boy(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    await mm_start_search(client, callback_query.message.chat.id, user, mode="boy", near=False, cost=0, info_gender_line="جستجو پسر 🙋‍♂️")


@bot.on_callback_query(equals("mm_girl") & private)
async def cb_mm_girl(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    await mm_start_search(client, callback_query.message.chat.id, user, mode="girl", near=False, cost=0, info_gender_line="جستجو دختر 🙋‍♀️")


@bot.on_callback_query(equals("mm_near_any") & private)
async def cb_mm_near_any(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    await mm_start_search(client, callback_query.message.chat.id, user, mode="random", near=True, cost=0, info_gender_line="جستجوی اطراف 🪃 (رایگان)")


@bot.on_callback_query(equals("mm_near_girl") & private)
async def cb_mm_near_girl(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    await mm_start_search(
        client, callback_query.message.chat.id, user, mode="girl", near=True,
        cost=config.NEAR_SEARCH_COST, info_gender_line="جستجوی اطراف دختر 🙋‍♀️",
    )


@bot.on_callback_query(equals("mm_near_boy") & private)
async def cb_mm_near_boy(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    await mm_start_search(
        client, callback_query.message.chat.id, user, mode="boy", near=True,
        cost=config.NEAR_SEARCH_COST, info_gender_line="جستجوی اطراف پسر 🙋‍♂️",
    )
