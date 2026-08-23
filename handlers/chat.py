"""چت خصوصی: درخواست/پذیرش چت، پیام دایرکت، رله‌ی پیام داخل چت، هدیه‌ی سکه، قطع چت."""
from balethon.conditions import equals, regex,private
from balethon.errors import ContinueDispatching

import config
import database as db
import force_join as fj
import keyboards as kb
import moderation_log as modlog
from bot_instance import bot, runtime
from filters import get_event_user, set_event_user, state_is, in_active_chat
from profile_common import is_blocked_between, show_user_profile_by_pid
from utils import safe_int, now_ts, gen_req_id, user_is_silent, user_is_online_recent

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

CHAT_MENU_TEXTS = {"🎁 هدیه", "👤 پروفایل مخاطب", "🎮 دوز با مخاطب", "✂️ سنگ کاغذ قیچی با مخاطب", "قطع چت"}
END_CHAT_CONFIRM_AFTER_SECONDS = 7


def _is_navigation_text(text: str) -> bool:
    text = (text or "").strip()
    return text in MAIN_MENU_TEXTS or text in CHAT_MENU_TEXTS or text.startswith("/")


async def _clear_state_and_continue(client, event, chat_id, user, *tmp_keys):
    txt = (getattr(event, "text", None) or "").strip()
    user["state"] = None
    for key in tmp_keys:
        user[key] = None
    await db.save_user(chat_id, user)
    set_event_user(event, user)
    if (
        user.get("profile_completed", False)
        and not user.get("chat_with")
        and (txt in MAIN_MENU_TEXTS or txt.startswith("/"))
        and await fj.force_join_gate_needed_for_user(client, chat_id)
    ):
        await fj.send_force_join_gate(client, chat_id, reply_to_message_id=event.id)
        return
    raise ContinueDispatching()


async def _send_not_enough_coins(client, chat_id, balance, needed, reply_to_message_id=None, context="این کار"):
    await client.send_message(
        chat_id,
        "🪙 *موجودی سکه کافی نیست*\n\n"
        f"برای {context} به *{needed}* سکه نیاز دارید.\n"
        f"موجودی فعلی شما: *{balance}* سکه\n\n"
        "می‌توانید از دکمه‌های زیر سکه تهیه کنید یا با معرفی دوستان سکه رایگان بگیرید 👇",
        reply_markup=kb.ikb_coin_buy_menu(),
        reply_to_message_id=reply_to_message_id,
    )


# ---------------------------------------------------------------------------
# توابع مشترک چت (مورد استفاده‌ی matchmaking.py / dooz.py / rps.py / registration.py)
# ---------------------------------------------------------------------------
async def start_chat_between(uid1, uid2) -> bool:
    uid1, uid2 = str(uid1), str(uid2)
    u1 = await db.get_user(uid1, create_if_missing=False)
    u2 = await db.get_user(uid2, create_if_missing=False)
    if not u1 or not u2:
        return False
    u1["chat_with"] = uid2
    u2["chat_with"] = uid1
    u1["chat_started_at"] = now_ts()
    u2["chat_started_at"] = now_ts()
    u1["state"] = None
    u2["state"] = None
    await db.save_user(uid1, u1)
    await db.save_user(uid2, u2)
    await db.inc_stat("chats_started", 1)
    return True


async def end_chat_for(uid):
    uid = str(uid)
    u = await db.get_user(uid, create_if_missing=False)
    if not u:
        return None
    other = u.get("chat_with")
    u["chat_with"] = None
    u["chat_started_at"] = None
    await db.save_user(uid, u)
    return other


def _end_chat_wait_seconds(user):
    started_at = safe_int((user or {}).get("chat_started_at") or 0, 0)
    if started_at <= 0:
        return 0
    elapsed = max(0, now_ts() - started_at)
    return max(0, END_CHAT_CONFIRM_AFTER_SECONDS - elapsed)


def _clear_pending_chat_invites(uid, other_uid=None):
    ids = {str(uid)}
    if other_uid:
        ids.add(str(other_uid))
    for user_id in ids:
        runtime["pending_chat_dooz_invites"].pop(user_id, None)
        runtime["pending_chat_rps_invites"].pop(user_id, None)


async def _clear_active_chat_games(client, uid):
    uid = str(uid)
    try:
        from handlers import dooz
        session = dooz.session_of(uid)
        if session and session.get("source") == "chat":
            await dooz._cleanup_board_messages(client, session)
            dooz._clear_binding(session)
            runtime["dooz_sessions"].pop(session["id"], None)
    except Exception:
        pass

    try:
        from handlers import rps
        session = rps.rps_session_of(uid)
        if session and session.get("source") == "chat":
            await rps.cleanup_rps_messages(client, session)
            rps.clear_rps_active_binding(session)
            runtime["rps_sessions"].pop(session["id"], None)
    except Exception:
        pass


async def _finish_chat_end(client, chat_id, user, reply_to_message_id=None):
    other_uid = user.get("chat_with")
    _clear_pending_chat_invites(chat_id, other_uid)
    await _clear_active_chat_games(client, chat_id)

    await end_chat_for(chat_id)
    if other_uid:
        await end_chat_for(other_uid)

    try:
        await client.send_message(
            int(chat_id),
            "✅ چت با موفقیت قطع شد.\n\nهر وقت خواستی، از منوی اصلی می‌تونی دوباره به یک ناشناس وصل بشی.",
            reply_markup=kb.kb_main_menu(),
            reply_to_message_id=reply_to_message_id,
        )
    except Exception:
        pass
    if other_uid:
        try:
            await client.send_message(
                int(other_uid),
                "✅ چت توسط مخاطب قطع شد.\n\nشما به منوی اصلی برگشتید.",
                reply_markup=kb.kb_main_menu(),
            )
        except Exception:
            pass
        await notify_watchers_chat_end(client, other_uid)
    await notify_watchers_chat_end(client, chat_id)


async def notify_watchers_chat_end(client, target_uid_str):
    if not target_uid_str:
        return
    tu = await db.get_user(target_uid_str, create_if_missing=False)
    if not tu:
        return
    watchers = tu.get("notify_chat_end") or []
    keep = []
    for it in watchers:
        if not isinstance(it, dict):
            continue
        wuid = str(it.get("watcher_uid") or "").strip()
        exp = safe_int(it.get("expire_ts") or 0, 0)
        if not wuid or exp <= now_ts():
            continue
        try:
            pid = tu.get("public_id")
            await client.send_message(int(wuid), f"🔔 چت کاربر /user_{pid} به پایان رسید.")
        except Exception:
            pass
        keep.append(it)
    tu["notify_chat_end"] = keep
    await db.save_user(target_uid_str, tu)


async def relay_message_to_partner(client, from_uid_str, message):
    fu = await db.get_user(from_uid_str, create_if_missing=False)
    if not fu:
        return
    other_uid = fu.get("chat_with")
    if not other_uid:
        return
    ou = await db.get_user(other_uid, create_if_missing=False)
    if not ou:
        return

    if is_blocked_between(fu, ou):
        try:
            await client.send_message(int(from_uid_str), "⛔ به دلیل بلاک، چت قطع شد.", reply_markup=kb.kb_main_menu())
        except Exception:
            pass
        try:
            await client.send_message(int(other_uid), "⛔ به دلیل بلاک، چت قطع شد.", reply_markup=kb.kb_main_menu())
        except Exception:
            pass
        await end_chat_for(from_uid_str)
        await end_chat_for(other_uid)
        return

    # پیام ریپلای‌شده در این چت به پیام متناظرِ طرف مقابل نگاشت می‌شود.
    reply_to = getattr(getattr(message, "reply_to_message", None), "id", None)
    link = await db.get_chat_message_link(from_uid_str, reply_to) if reply_to else None
    target_reply_id = link[1] if link and str(link[0]) == str(other_uid) else None

    async def remember(sent_message):
        target_id = getattr(sent_message, "id", None)
        if target_id is not None:
            await db.save_chat_message_link(from_uid_str, message.id, other_uid, target_id)
            await db.save_chat_message_link(other_uid, target_id, from_uid_str, message.id)

    if message.text:
        try:
            sent = await client.send_message(int(other_uid), message.text, reply_markup=kb.kb_chat_menu(), reply_to_message_id=target_reply_id)
            await remember(sent)
        except Exception:
            pass
        return

    if message.photo:
        try:
            sent = await client.copy_message(int(other_uid), message.chat.id, message.id, reply_to_message_id=target_reply_id)
            await remember(sent)
            await modlog.log_media(client, message, from_uid_str, fu, other_uid, ou)
        except Exception:
            pass
        return

    if modlog.is_loggable_media(message):
        try:
            # copyMessage رسانه را بدون نمایش هویت فرستنده منتقل می‌کند و همه‌ی
            # انواع فایل بله (ویدئو، ویس، صوت، سند، گیف، استیکر و مخاطب) را پوشش می‌دهد.
            sent = await client.copy_message(int(other_uid), message.chat.id, message.id, reply_to_message_id=target_reply_id)
            await remember(sent)
            await modlog.log_media(client, message, from_uid_str, fu, other_uid, ou)
        except Exception:
            pass
        return

    if message.location is not None:
        try:
            await client.send_message(int(from_uid_str), "⚠️ ارسال لوکیشن داخل چت غیرفعال است.")
        except Exception:
            pass
        return


# ---------------------------------------------------------------------------
# پیام دایرکت (1 سکه)
# ---------------------------------------------------------------------------
@bot.on_callback_query(regex(r"^direct:") & private)
async def cb_direct(client, callback_query):
    pid = callback_query.data.split(":", 1)[1].strip()
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id

    target_uid, target_user = await db.get_user_by_public_id(pid)
    if not target_user:
        await callback_query.answer("کاربر یافت نشد")
        return
    if is_blocked_between(user, target_user):
        await callback_query.answer("امکان پیام نیست (بلاک)")
        return

    user["state"] = "direct_wait_text"
    user["tmp_direct_pid"] = pid
    await db.save_user(chat_id, user)
    await client.send_message(
        chat_id,
        "📨 *ارسال پیام دایرکت*\n\n"
        "متن پیام خود را ارسال کنید.\n"
        f"⛔ هزینه: *{config.DIRECT_MESSAGE_COST}* سکه (در صورت ارسال موفق)\n"
        "⚠️ حداکثر 200 کاراکتر ارسال می‌شود.\n\n"
        "برای لغو: «بازگشت 🔙»",
        reply_markup=kb.kb_back_only(),
    )


@bot.on_message(state_is("direct_wait_text") & private)
async def msg_direct_wait_text(client, message):
    user = await get_event_user(message)
    chat_id = message.chat.id
    txt = message.text or ""

    if _is_navigation_text(txt):
        await _clear_state_and_continue(client, message, chat_id, user, "tmp_direct_pid")

    if txt.strip() == "بازگشت 🔙":
        user["state"] = None
        user["tmp_direct_pid"] = None
        await db.save_user(chat_id, user)
        await client.send_message(chat_id, "✅ لغو شد.", reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id)
        return

    pid = str(user.get("tmp_direct_pid") or "").strip()
    target_uid, target_user = await db.get_user_by_public_id(pid)
    if not target_user:
        user["state"] = None
        user["tmp_direct_pid"] = None
        await db.save_user(chat_id, user)
        await client.send_message(chat_id, "⚠️ کاربر پیدا نشد.", reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id)
        return

    if is_blocked_between(user, target_user):
        user["state"] = None
        user["tmp_direct_pid"] = None
        await db.save_user(chat_id, user)
        await client.send_message(chat_id, "⛔ امکان ارسال پیام نیست (بلاک).", reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id)
        return

    cost = config.DIRECT_MESSAGE_COST
    balance = safe_int(user.get("coins", 0), 0)
    if balance < cost:
        user["state"] = None
        user["tmp_direct_pid"] = None
        await db.save_user(chat_id, user)
        await _send_not_enough_coins(client, chat_id, balance, cost, reply_to_message_id=message.id, context="ارسال پیام دایرکت")
        return

    msg_txt = txt[:200]
    try:
        await client.send_message(
            int(target_uid), f"📨 *پیام دایرکت جدید*\n\nاز طرف: /user_{user.get('public_id')}\n\n{msg_txt}"
        )
        user["coins"] = safe_int(user.get("coins", 0), 0) - cost
        user["state"] = None
        user["tmp_direct_pid"] = None
        await db.save_user(chat_id, user)
        await client.send_message(
            chat_id, f"✅ ارسال شد.\n💰 موجودی جدید: *{user['coins']}*", reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id
        )
    except Exception:
        user["state"] = None
        user["tmp_direct_pid"] = None
        await db.save_user(chat_id, user)
        await client.send_message(chat_id, "❌ ارسال ناموفق بود.", reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id)


# ---------------------------------------------------------------------------
# درخواست چت
# ---------------------------------------------------------------------------
@bot.on_callback_query(regex(r"^chatreq:") & private)
async def cb_chatreq(client, callback_query):
    pid = callback_query.data.split(":", 1)[1].strip()
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id

    target_uid, target_user = await db.get_user_by_public_id(pid)
    if not target_user:
        await callback_query.answer("کاربر یافت نشد")
        return
    if is_blocked_between(user, target_user):
        await callback_query.answer("امکان درخواست نیست (بلاک)")
        return
    if user.get("chat_with"):
        await callback_query.answer("شما درحال چت هستید")
        return
    if target_user.get("chat_with"):
        await callback_query.answer("خطا: کاربر درحال چت هست")
        return
    if user_is_silent(target_user):
        await callback_query.answer("کاربر در حالت سایلنت است")
        return
    if not user_is_online_recent(target_user, minutes=15):
        await callback_query.answer("کاربر اخیراً آنلاین نبوده")
        return

    req_id = gen_req_id()
    await db.create_chat_request(req_id, chat_id, target_uid)

    from_pid = user.get("public_id")
    try:
        await client.send_message(
            int(target_uid),
            "💬 *درخواست چت جدید*\n\n"
            f"کاربر /user_{from_pid} درخواست چت ارسال کرده است.\n\n"
            "اگر *قبول* کنید، شما و ارسال‌کننده وارد چت خصوصی می‌شوید.\n"
            f"⚠️ در صورت تایید، از ارسال‌کننده *{config.CHAT_REQUEST_COST} سکه* کسر می‌شود.\n\n"
            "انتخاب کنید 👇",
            reply_markup=kb.ikb([("✅ قبول", f"chat_accept:{req_id}")], [("❌ رد", f"chat_decline:{req_id}")]),
        )
    except Exception:
        pass

    await client.send_message(chat_id, "✅ درخواست چت ارسال شد. منتظر تایید کاربر باش.", reply_to_message_id=callback_query.message.id)


@bot.on_callback_query(regex(r"^(chat_accept|chat_decline):") & private)
async def cb_chat_accept_decline(client, callback_query):
    act, req_id = callback_query.data.split(":", 1)
    await callback_query.answer(None)
    chat_id = callback_query.message.chat.id

    req = await db.get_chat_request(req_id)
    if not req or req.get("status") != "pending":
        await callback_query.answer("درخواست نامعتبر/منقضی")
        return
    if str(req.get("to_uid")) != str(chat_id):
        await callback_query.answer("دسترسی ندارید")
        return

    from_uid = str(req.get("from_uid"))
    to_uid = str(req.get("to_uid"))
    from_user = await db.get_user(from_uid, create_if_missing=False)
    to_user = await db.get_user(to_uid, create_if_missing=False)
    if not from_user or not to_user:
        await db.update_chat_request_status(req_id, "expired")
        return

    if act == "chat_decline":
        await db.update_chat_request_status(req_id, "declined")
        try:
            await client.send_message(int(from_uid), "❌ درخواست چت شما رد شد.")
        except Exception:
            pass
        await client.edit_message_text(chat_id, callback_query.message.id, "❌ درخواست رد شد.")
        return

    if from_user.get("chat_with") or to_user.get("chat_with"):
        await db.update_chat_request_status(req_id, "failed_busy")
        await callback_query.answer("یکی از کاربران درحال چت است")
        await client.edit_message_text(chat_id, callback_query.message.id, "⚠️ امکان اتصال نیست (درحال چت).")
        return

    if safe_int(from_user.get("coins", 0), 0) < config.CHAT_REQUEST_COST:
        await db.update_chat_request_status(req_id, "failed_no_coin")
        try:
            await client.send_message(
                int(from_uid), f"❌ موجودی سکه برای شروع چت کافی نیست (نیاز: {config.CHAT_REQUEST_COST} سکه)."
            )
        except Exception:
            pass
        await client.edit_message_text(chat_id, callback_query.message.id, "❌ سکه کاربر ارسال‌کننده کافی نبود.")
        return

    from_user["coins"] = safe_int(from_user.get("coins", 0), 0) - config.CHAT_REQUEST_COST
    await db.save_user(from_uid, from_user)
    await db.update_chat_request_status(req_id, "accepted")

    await start_chat_between(from_uid, to_uid)

    try:
        await client.send_message(
            int(from_uid),
            "✅ درخواست چت شما *تایید شد*.\n\n💬 شما به چت متصل شدید.\n\nبرای مدیریت چت از منوی پایین استفاده کن.",
            reply_markup=kb.kb_chat_menu(),
        )
    except Exception:
        pass
    try:
        await client.send_message(
            int(to_uid),
            "✅ شما *درخواست چت* را پذیرفتید.\n\n💬 شما به چت متصل شدید.\n\nبرای مدیریت چت از منوی پایین استفاده کن.",
            reply_markup=kb.kb_chat_menu(),
        )
    except Exception:
        pass

    await client.edit_message_text(chat_id, callback_query.message.id, "✅ تایید شد. چت شروع شد.")


# ---------------------------------------------------------------------------
# دکمه‌های منوی چتِ فعال (ترتیب ثبت این هندلرها مهم است؛ relay باید آخرین باشد!)
# ---------------------------------------------------------------------------
@bot.on_message(equals("قطع چت") & private & in_active_chat)
async def msg_end_chat(client, message):
    user = await get_event_user(message)
    chat_id = message.chat.id
    wait_seconds = _end_chat_wait_seconds(user)
    if wait_seconds > 0:
        await client.send_message(
            chat_id,
            "⏳ *قطع چت هنوز فعال نشده*\n\n"
            "برای جلوگیری از قطع اشتباهی، قطع چت از ۷ ثانیه بعد از شروع گفتگو فعال می‌شود.\n"
            f"فقط *{wait_seconds}* ثانیه دیگر صبر کن و دوباره بزن.",
            reply_markup=kb.kb_chat_menu(),
            reply_to_message_id=message.id,
        )
        return

    await client.send_message(
        chat_id,
        "⚠️ *مطمئنی می‌خوای چت رو قطع کنی؟*\n\n"
        "با تایید، ارتباط ناشناس برای هر دو نفر بسته می‌شه و شما به منوی اصلی برمی‌گردید.",
        reply_markup=kb.ikb_end_chat_confirm(chat_id),
        reply_to_message_id=message.id,
    )


@bot.on_callback_query(regex(r"^chat_end:") & private)
async def cb_chat_end_confirm(client, callback_query):
    parts = (callback_query.data or "").split(":")
    if len(parts) != 3 or parts[1] not in ("yes", "no"):
        await callback_query.answer("دکمه نامعتبر است.", show_alert=True)
        return

    action, owner_id = parts[1], str(parts[2])
    chat_id = str(callback_query.author.id)
    if owner_id != chat_id:
        await callback_query.answer("این دکمه برای شما نیست.", show_alert=True)
        return

    user = await get_event_user(callback_query)
    if not user.get("chat_with"):
        await callback_query.answer("چت فعالی برای قطع کردن وجود ندارد.", show_alert=True)
        try:
            await client.edit_message_text(int(chat_id), callback_query.message.id, "ℹ️ این چت قبلاً بسته شده است.")
        except Exception:
            pass
        return

    if action == "no":
        await callback_query.answer("باشه؛ چت ادامه دارد 💬")
        try:
            await client.edit_message_text(
                int(chat_id),
                callback_query.message.id,
                "✅ قطع چت لغو شد.\n\nگفتگو همچنان فعاله؛ از منوی پایین ادامه بده.",
            )
        except Exception:
            pass
        return

    wait_seconds = _end_chat_wait_seconds(user)
    if wait_seconds > 0:
        await callback_query.answer(f"هنوز {wait_seconds} ثانیه باقی مانده.", show_alert=True)
        return

    await callback_query.answer("چت قطع شد ✅")
    try:
        await client.edit_message_text(int(chat_id), callback_query.message.id, "✅ تایید شد؛ چت در حال بسته شدن است.")
    except Exception:
        pass
    await _finish_chat_end(client, chat_id, user, reply_to_message_id=callback_query.message.id)


@bot.on_message(equals("🎁 هدیه") & private & in_active_chat)
async def msg_gift_button(client, message):
    user = await get_event_user(message)
    chat_id = message.chat.id
    user["state"] = "chat_gift_wait_amount"
    await db.save_user(chat_id, user)
    await client.send_message(
        chat_id,
        "🎁 *هدیه‌ی سکه به مخاطب!*\n\n"
        "فقط کافیه *عدد صحیح* رو بفرستی.\n\n"
        "⚠️ توجه: سکه‌های هدیه از موجودی خودت کم می‌شن.\n"
        "برای لغو هم فقط بنویس: *لغو*",
        reply_markup=kb.kb_chat_menu(),
        reply_to_message_id=message.id,
    )


@bot.on_message(state_is("chat_gift_wait_amount") & private)
async def msg_gift_amount(client, message):
    user = await get_event_user(message)
    chat_id = message.chat.id
    txt = (message.text or "").strip()

    if _is_navigation_text(txt) and txt != "🎁 هدیه":
        await _clear_state_and_continue(client, message, chat_id, user)

    if txt == "لغو":
        user["state"] = None
        await db.save_user(chat_id, user)
        await client.send_message(chat_id, "✅ لغو شد.", reply_markup=kb.kb_chat_menu(), reply_to_message_id=message.id)
        return

    amount = safe_int(txt, 0)
    if amount <= 0:
        await client.send_message(
            chat_id, "⚠️ فقط یک عدد صحیح مثبت بفرست. برای لغو: *لغو*", reply_markup=kb.kb_chat_menu(), reply_to_message_id=message.id
        )
        return
    balance = safe_int(user.get("coins", 0), 0)
    if balance < amount:
        user["state"] = None
        await db.save_user(chat_id, user)
        await _send_not_enough_coins(client, chat_id, balance, amount, reply_to_message_id=message.id, context="ارسال هدیه")
        return

    other_uid = user.get("chat_with")
    if not other_uid:
        user["state"] = None
        await db.save_user(chat_id, user)
        await client.send_message(chat_id, "⚠️ چت فعال نیست.", reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id)
        return
    other_user = await db.get_user(other_uid, create_if_missing=False)
    if not other_user:
        user["state"] = None
        await db.save_user(chat_id, user)
        await client.send_message(chat_id, "⚠️ خطا در مخاطب.", reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id)
        return

    user["coins"] = safe_int(user.get("coins", 0), 0) - amount
    other_user["coins"] = safe_int(other_user.get("coins", 0), 0) + amount
    user["state"] = None
    await db.save_user(chat_id, user)
    await db.save_user(other_uid, other_user)

    await client.send_message(
        chat_id, f"✅ هدیه ارسال شد.\n💰 موجودی جدید شما: *{user['coins']}*", reply_markup=kb.kb_chat_menu(), reply_to_message_id=message.id
    )
    try:
        await client.send_message(
            int(other_uid),
            "🎉 *تبریک!*\n\n"
            f"✅ مخاطبت بهت *{amount}* 🪙 سکه هدیه داد.\n"
            f"💰 موجودی جدید شما: *{other_user['coins']}* 🪙",
            reply_markup=kb.kb_chat_menu(),
        )
    except Exception:
        pass


@bot.on_message(equals("🎮 دوز با مخاطب") & private & in_active_chat)
async def msg_chat_dooz_invite(client, message):
    user = await get_event_user(message)
    from handlers.dooz import send_chat_dooz_invite
    await send_chat_dooz_invite(client, message.chat.id, user)


@bot.on_message(equals("✂️ سنگ کاغذ قیچی با مخاطب") & private & in_active_chat)
async def msg_chat_rps_invite(client, message):
    user = await get_event_user(message)
    from handlers.rps import send_chat_rps_invite
    await send_chat_rps_invite(client, message.chat.id, user)


@bot.on_message(equals("👤 پروفایل مخاطب") & private & in_active_chat)
async def msg_chat_partner_profile(client, message):
    user = await get_event_user(message)
    chat_id = message.chat.id
    other_uid = user.get("chat_with")
    if not other_uid:
        await client.send_message(chat_id, "⚠️ چت فعال نیست.", reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id)
        return
    other_user = await db.get_user(other_uid, create_if_missing=False)
    if not other_user:
        await client.send_message(chat_id, "⚠️ خطا در مخاطب.", reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id)
        return
    pid = await db.ensure_unique_public_id(other_uid)

    await show_user_profile_by_pid(client, chat_id, user, pid, reply_to_message_id=message.id)
    try:
        await client.send_message(
            int(other_uid),
            "🤖 پیام سیستم 👇\n\n"
            "مخاطب شما 《 پروفایلِ  چت ناشناس↑cₕₐₜ  》  شما را مشاهده کرد.\n\n"
            "⚠️ توجه: پروفایل  چت ناشناس↑cₕₐₜ  اطلاعاتی است که در بخش پروفایل ربات ثبت کرده اید!",
        )
    except Exception:
        pass

@bot.on_message(equals("/start") & in_active_chat & private)
async def msg_start(client, message):
    try:
        await client.send_message(int(message.chat.id),"""🔔 *پیام سیستم*

شما هم‌اکنون درون یک چت فعال با ربات قرار دارید.  
در صورت تمایل به استارت مجدد یا شروع دوباره ربات، لطفاً از منوی زیر گزینه *«قطع چت»* را انتخاب نمایید.""",reply_markup=kb.kb_chat_menu())
    except Exception:
        pass

# نکته‌ی بسیار مهم: این هندلر باید آخرین هندلرِ «in_active_chat» در کل پروژه باشد
# (هر پیامِ دیگری که در چتِ فعال بیاید و بالا match نشده، رله می‌شود).
@bot.on_message(in_active_chat & private)
async def msg_relay_to_partner(client, message):
    await relay_message_to_partner(client, str(message.chat.id), message)
