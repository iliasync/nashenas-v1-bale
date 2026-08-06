"""جریان ثبت‌نام (انتخاب جنسیت → سن → استان) + دستور /start و لینک‌های دعوت/ناشناس/بازی."""
import asyncio

from balethon.conditions import equals,private

import config
import database as db
import keyboards as kb
from bot_instance import bot
from filters import get_event_user, state_is
from utils import safe_int, parse_token_host_id

DOOZ_PREFIXES = ("dooz_", "dooz-", "dooz:")
RPS_PREFIXES = ("rps_", "rps-", "rps:")


# ---------------------------------------------------------------------------
# توابع مشترک جریان ثبت‌نام
# ---------------------------------------------------------------------------
async def start_registration(client, chat_id, first_name, user, reply_to_message_id=None):
    user["state"] = "awaiting_gender"
    user["profile_completed"] = False
    await db.save_user(chat_id, user)
    name = (first_name or "").strip() or "دوست"
    text = (
        f"سلام  {name}  عزیز ✋️\n\n"
        "به 《 چت ناشناس↑cₕₐₜ . 🤖》 خوش اومدی...\n\n"
        "برای شروع جنسیتت رو انتخاب کن 👇"
    )
    await client.send_message(chat_id, text, reply_markup=kb.ikb_gender(), reply_to_message_id=reply_to_message_id)


async def ask_age(client, chat_id, user, reply_to_message_id=None):
    user["state"] = "awaiting_age"
    await db.save_user(chat_id, user)
    await client.send_message(
        chat_id,
        "خب حالا سنت رو بهم بگو ؟:\n\n• از لیست انتخاب کن یا تایپ کن",
        reply_markup=kb.kb_age_1_99(),
        reply_to_message_id=reply_to_message_id,
    )


async def ask_province(client, chat_id, user, reply_to_message_id=None):
    user["state"] = "awaiting_province"
    await db.save_user(chat_id, user)
    await client.send_message(
        chat_id,
        "خب حالا فقط کافیه استانت رو انتخاب کنی 👇",
        reply_markup=kb.kb_provinces(),
        reply_to_message_id=reply_to_message_id,
    )


async def _apply_pending_referral_join(client, chat_id, user):
    pending = (user.get("pending_ref_pid") or "").strip()
    if pending and not (user.get("ref_rewarded", False) or user.get("referred_by")):
        inv_uid, inv_user = await db.get_user_by_public_id(pending)
        if inv_user and inv_uid and str(inv_uid) != str(chat_id):
            user["coins"] = safe_int(user.get("coins", 0), 0) + config.INVITE_JOIN_REWARD_NEW
            user["referred_by"] = pending
            user["ref_rewarded"] = True
            inv_user["coins"] = safe_int(inv_user.get("coins", 0), 0) + config.INVITE_JOIN_REWARD_OWNER
            inv_user["invite_count"] = safe_int(inv_user.get("invite_count", 0), 0) + 1
            await db.save_user(inv_uid, inv_user)
            try:
                await client.send_message(
                    chat_id,
                    f"🎉 تبریک!\n\n✅ شما با لینک دعوت وارد شدید و *{config.INVITE_JOIN_REWARD_NEW}* سکه 💰 دریافت کردید.\n"
                    f"💰 موجودی جدید: *{user['coins']}*",
                )
            except Exception:
                pass
            try:
                await client.send_message(
                    int(inv_uid),
                    "🎉 تبریک!\n\n"
                    f"✅ یک نفر با لینک شما وارد شد و *{config.INVITE_JOIN_REWARD_OWNER}* سکه 💰 دریافت کردید.\n"
                    f"👈 تعداد دعوت‌های شما: *{inv_user['invite_count']}*\n"
                    f"💰 موجودی جدید: *{inv_user['coins']}*",
                )
            except Exception:
                pass
    user["pending_ref_pid"] = None
    await db.save_user(chat_id, user)


async def send_main_after_start(client, chat_id, user, reply_to_message_id=None):
    await client.send_message(
        chat_id,
        "خب ، حالا چه کاری برات انجام بدم؟\n\nاز منوی پایین انتخاب کن👇",
        reply_markup=kb.kb_main_menu(),
        reply_to_message_id=reply_to_message_id,
    )
    await _apply_pending_referral_join(client, chat_id, user)


async def handle_anonymous_start(client, chat_id, user, token, reply_to_message_id=None, first_name="") -> bool:
    token = (token or "").strip()
    owner_uid, owner_user = await db.get_user_by_anon_code(token)
    if not token or not owner_user or not owner_uid:
        await client.send_message(chat_id, "⚠️ لینک ناشناس نامعتبر است یا منقضی شده.", reply_to_message_id=reply_to_message_id)
        await send_main_after_start(client, chat_id, user)
        return True

    if str(owner_uid) == str(chat_id):
        from handlers.invites import send_anonymous_link
        await send_anonymous_link(client, chat_id, user, reply_to_message_id=reply_to_message_id, first_name=first_name)
        return True

    if owner_user.get("chat_with"):
        await client.send_message(
            chat_id,
            "⛔ فعلا امکان ارسال پیام ناشناس نیست.\n\n"
            "⚠️ صاحب لینک در حال چت است. لطفا چند دقیقه بعد دوباره تلاش کنید.",
            reply_to_message_id=reply_to_message_id,
        )
        await send_main_after_start(client, chat_id, user)
        return True

    if user.get("chat_with"):
        await client.send_message(chat_id, "⚠️ شما درحال چت هستید. ابتدا چت را قطع کنید.", reply_to_message_id=reply_to_message_id)
        return True

    from handlers.chat import start_chat_between
    ok = await start_chat_between(str(chat_id), str(owner_uid))
    if not ok:
        await client.send_message(chat_id, "⚠️ خطا در اتصال. دوباره تلاش کنید.", reply_to_message_id=reply_to_message_id)
        await send_main_after_start(client, chat_id, user)
        return True

    try:
        await client.send_message(
            chat_id,
            "✅ اتصال انجام شد.\n\n"
            "📬 شما وارد چت ناشناس شدید.\n"
            "هر پیامی بفرستید، ناشناس ارسال می‌شود.",
            reply_markup=kb.kb_chat_menu(),
            reply_to_message_id=reply_to_message_id,
        )
    except Exception:
        pass
    try:
        await client.send_message(
            int(owner_uid),
            "📬 یک پیام ناشناس جدید برای شما!\n\n"
            "✅ شما به چت ناشناس متصل شدید.\n"
            "برای مدیریت چت از منوی پایین استفاده کن.",
            reply_markup=kb.kb_chat_menu(),
        )
    except Exception:
        pass
    return True


async def finalize_profile(client, chat_id, user, reply_to_message_id=None):
    user["state"] = None
    user["profile_completed"] = True
    await db.inc_stat("profile_completed", 1)
    user["public_id"] = await db.ensure_unique_public_id(chat_id)
    await db.save_user(chat_id, user)

    msg1 = await client.send_message(
        chat_id, "✅اطلاعات شما ثبت شد.\n\nاز منوی پایین👇 انتخاب کن", reply_to_message_id=reply_to_message_id
    )
    if msg1:
        try:
            await client.send_message(chat_id, "👆اطلاعات شما کامل ذخیره شد و قابل تغییر میباشد.", reply_to_message_id=msg1.id)
        except Exception:
            pass
    await asyncio.sleep(1)
    await client.send_message(
        chat_id, "منوی اصلی آماده شد.", reply_markup=kb.kb_main_menu(), reply_to_message_id=reply_to_message_id
    )

    pending_dooz_host = (user.get("pending_dooz_host") or "").strip()
    if pending_dooz_host:
        user["pending_dooz_host"] = None
        await db.save_user(chat_id, user)
        from handlers.dooz import start_dooz_from_link
        await start_dooz_from_link(client, str(chat_id), pending_dooz_host)

    pending_rps_host = (user.get("pending_rps_host") or "").strip()
    if pending_rps_host:
        user["pending_rps_host"] = None
        await db.save_user(chat_id, user)
        from handlers.rps import start_rps_from_link
        await start_rps_from_link(client, str(chat_id), pending_rps_host)

    pending_anon_token = (user.get("pending_anon_token") or "").strip()
    if pending_anon_token:
        user["pending_anon_token"] = None
        await db.save_user(chat_id, user)
        await handle_anonymous_start(client, chat_id, user, pending_anon_token, reply_to_message_id=reply_to_message_id)


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------
@bot.on_command(name="start", min_arguments=0, max_arguments=1,condition=private)
async def cmd_start(*_extra_args, client, message):
    # نکته: بله‌تون آرگومان‌های اضافه‌ی بعد از «/start» را به‌صورت پوزیشنال هم
    # به callback پاس می‌دهد؛ برای جلوگیری از تصادمِ آن با پارامترهای
    # client/message (که آن‌ها هم به‌صورت kwarg تزریق می‌شوند) این مقدار را
    # عمداً داخل *_extra_args می‌ریزیم و خودمان مستقیماً از message.text پارس
    # می‌کنیم (دقیقاً مثل نسخه‌ی اصلی).
    user = await get_event_user(message)
    chat_id = message.chat.id
    first_name = message.author.first_name or ""
    parts = (message.text or "").strip().split(maxsplit=1)
    start_param = parts[1].strip() if len(parts) > 1 else ""

    if not user.get("profile_completed", False):
        await start_registration(client, chat_id, first_name, user, reply_to_message_id=message.id)
        if start_param.startswith("z_"):
            user["pending_ref_pid"] = start_param[2:].strip()
        elif start_param.startswith("anon_"):
            user["pending_anon_token"] = start_param[5:].strip()
        dooz_host = parse_token_host_id(start_param, DOOZ_PREFIXES)
        if dooz_host:
            user["pending_dooz_host"] = dooz_host
        rps_host = parse_token_host_id(start_param, RPS_PREFIXES)
        if rps_host:
            user["pending_rps_host"] = rps_host
        await db.save_user(chat_id, user)
        return

    # --- لینک دعوت ---
    if start_param.startswith("z_"):
        inviter_pid = start_param[2:].strip()
        if user.get("ref_rewarded", False) or user.get("referred_by"):
            await send_main_after_start(client, chat_id, user, reply_to_message_id=message.id)
            return
        inv_uid, inv_user = await db.get_user_by_public_id(inviter_pid)
        if not inv_user or not inv_uid or str(inv_uid) == str(chat_id):
            await send_main_after_start(client, chat_id, user, reply_to_message_id=message.id)
            return
        user["coins"] = safe_int(user.get("coins", 0), 0) + config.INVITE_JOIN_REWARD_NEW
        user["referred_by"] = inviter_pid
        user["ref_rewarded"] = True
        inv_user["coins"] = safe_int(inv_user.get("coins", 0), 0) + config.INVITE_JOIN_REWARD_OWNER
        inv_user["invite_count"] = safe_int(inv_user.get("invite_count", 0), 0) + 1
        await db.save_user(chat_id, user)
        await db.save_user(inv_uid, inv_user)
        try:
            await client.send_message(
                chat_id,
                f"🎉 تبریک!\n\n✅ شما با لینک دعوت وارد شدید و *{config.INVITE_JOIN_REWARD_NEW}* سکه 💰 دریافت کردید.\n"
                f"💰 موجودی جدید: *{user['coins']}*",
                reply_to_message_id=message.id,
            )
        except Exception:
            pass
        try:
            await client.send_message(
                int(inv_uid),
                "🎉 تبریک!\n\n"
                f"✅ یک نفر با لینک شما وارد شد و *{config.INVITE_JOIN_REWARD_OWNER}* سکه 💰 دریافت کردید.\n"
                f"👈 تعداد دعوت‌های شما: *{inv_user['invite_count']}*\n"
                f"💰 موجودی جدید: *{inv_user['coins']}*",
            )
        except Exception:
            pass
        await send_main_after_start(client, chat_id, user, reply_to_message_id=message.id)
        return

    # --- لینک بازی دوز ---
    dooz_host_id = parse_token_host_id(start_param, DOOZ_PREFIXES)
    if dooz_host_id:
        from handlers.dooz import start_dooz_from_link
        handled = await start_dooz_from_link(client, str(chat_id), dooz_host_id)
        if not handled:
            await client.send_message(chat_id, "⚠️ لینک دوز نامعتبر است یا منقضی شده.", reply_to_message_id=message.id)
            await send_main_after_start(client, chat_id, user)
        return

    # --- لینک سنگ‌کاغذقیچی ---
    rps_host_id = parse_token_host_id(start_param, RPS_PREFIXES)
    if rps_host_id:
        from handlers.rps import start_rps_from_link
        handled = await start_rps_from_link(client, str(chat_id), rps_host_id)
        if not handled:
            await client.send_message(
                chat_id, "⚠️ لینک سنگ کاغذ قیچی نامعتبر است یا منقضی شده.", reply_to_message_id=message.id
            )
            await send_main_after_start(client, chat_id, user)
        return

    # --- لینک ناشناس ---
    if start_param.startswith("anon_"):
        token = start_param[5:].strip()
        await handle_anonymous_start(client, chat_id, user, token, reply_to_message_id=message.id, first_name=first_name)
        return

    # --- /start معمولی ---
    await send_main_after_start(client, chat_id, user, reply_to_message_id=message.id)


# ---------------------------------------------------------------------------
# انتخاب جنسیت (اینلاین)
# ---------------------------------------------------------------------------
@bot.on_callback_query(equals("reg_gender_male", "reg_gender_female") & private)
async def cb_reg_gender(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id
    if user.get("profile_completed", False):
        await send_main_after_start(client, chat_id, user, reply_to_message_id=callback_query.message.id)
        return
    user["gender"] = "male" if callback_query.data == "reg_gender_male" else "female"
    await db.save_user(chat_id, user)
    await ask_age(client, chat_id, user, reply_to_message_id=callback_query.message.id)


# ---------------------------------------------------------------------------
# مراحل متنی ثبت‌نام
# ---------------------------------------------------------------------------
@bot.on_message(state_is("awaiting_age") & private)
async def msg_awaiting_age(client, message):
    user = await get_event_user(message)
    chat_id = message.chat.id
    txt = (message.text or "").strip()
    if txt == "بازگشت 🔙":
        await start_registration(client, chat_id, message.author.first_name, user, reply_to_message_id=message.id)
        return
    age = safe_int(txt, 0)
    if age < 1 or age > 99:
        await client.send_message(chat_id, "⚠️ سن نامعتبره. 1 تا 99", reply_to_message_id=message.id)
        return
    user["age"] = age
    await db.save_user(chat_id, user)
    await ask_province(client, chat_id, user, reply_to_message_id=message.id)


@bot.on_message(state_is("awaiting_province") & private)
async def msg_awaiting_province(client, message):
    user = await get_event_user(message)
    chat_id = message.chat.id
    txt = (message.text or "").strip()
    if txt == "بازگشت 🔙":
        await ask_age(client, chat_id, user, reply_to_message_id=message.id)
        return
    if txt not in config.PROVINCES:
        await client.send_message(chat_id, "⚠️ استان را فقط از لیست انتخاب کن.", reply_to_message_id=message.id)
        return
    user["province"] = txt
    await db.save_user(chat_id, user)
    await finalize_profile(client, chat_id, user, reply_to_message_id=message.id)
