"""بازی سنگ کاغذ قیچی (چند دست، شانسی یا با لینک)."""
import math

from balethon.conditions import equals, regex,private

import config
import database as db
import keyboards as kb
from bot_links import build_start_link
from bot_instance import bot, runtime
from filters import get_event_user, is_admin_id
from utils import now_ts, safe_int

RPS_CHOICES = {
    "rock": "🪨 سنگ",
    "paper": "📄 کاغذ",
    "scissors": "✂️ قیچی",
}
RPS_BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}


def rps_session_of(uid):
    sid = runtime["rps_user_session"].get(str(uid))
    return runtime["rps_sessions"].get(sid) if sid is not None else None


def clear_rps_queue(uid):
    uid = str(uid)
    while uid in runtime["rps_waiting_random"]:
        runtime["rps_waiting_random"].remove(uid)


def clear_rps_active_binding(session):
    for uid in session["players"]:
        if runtime["rps_user_session"].get(uid) == session["id"]:
            runtime["rps_user_session"].pop(uid, None)


def make_rps_session(player_a, player_b, source):
    runtime["rps_session_counter"] += 1
    session_id = runtime["rps_session_counter"]
    session = {
        "id": session_id, "source": source, "players": [str(player_a), str(player_b)],
        "choices": {}, "current_round": 1, "total_rounds": config.RPS_TOTAL_ROUNDS,
        "scores": {str(player_a): 0, str(player_b): 0}, "history": [], "status": "active",
        "created_at": now_ts(), "deadline": now_ts() + config.RPS_TIMEOUT_SECONDS,
        "message_ids": {}, "last_round_texts": {},
    }
    runtime["rps_sessions"][session_id] = session
    runtime["rps_user_session"][str(player_a)] = session_id
    runtime["rps_user_session"][str(player_b)] = session_id
    return session


def rps_other_player(session, user_id):
    uid = str(user_id)
    return session["players"][0] if session["players"][1] == uid else session["players"][1]


def rps_result(choice_a, choice_b):
    if choice_a == choice_b:
        return None
    if RPS_BEATS.get(choice_a) == choice_b:
        return "a"
    return "b"


def rps_prompt_text(session, viewer_id):
    deadline_left = max(0, safe_int(session.get("deadline", 0), 0) - now_ts())
    minutes = max(1, math.ceil(deadline_left / 60)) if deadline_left else 0
    viewer_id = str(viewer_id)
    other_id = rps_other_player(session, viewer_id)
    picked = viewer_id in session.get("choices", {})
    other_picked = other_id in session.get("choices", {})
    if picked and other_picked:
        status = "هر دو انتخاب کردید"
    elif picked:
        status = "✅ انتخاب شما ثبت شد؛ منتظر حریف"
    elif other_picked:
        status = "🔥 حریف انتخاب کرده؛ نوبت شماست"
    else:
        status = "در انتظار انتخاب"
    last_round = (session.get("last_round_texts") or {}).get(viewer_id)
    return (
        "🎮 سنگ کاغذ قیچی\n\n"
        f"دست {session.get('current_round', 1)} از {session.get('total_rounds', config.RPS_TOTAL_ROUNDS)}\n"
        f"امتیاز شما: {safe_int((session.get('scores') or {}).get(viewer_id, 0), 0)}\n"
        f"امتیاز حریف: {safe_int((session.get('scores') or {}).get(other_id, 0), 0)}\n\n"
        f"{last_round + chr(10) + chr(10) if last_round else ''}"
        "یکی از گزینه‌ها را انتخاب کن 👇\n"
        f"⏳ زمان باقی‌مانده: {minutes} دقیقه\n"
        f"وضعیت: {status}"
    )


async def send_rps_prompts(client, session, seed_message_ids=None):
    seed_message_ids = {str(k): v for k, v in (seed_message_ids or {}).items() if v}
    for uid in session["players"]:
        try:
            message_id = session.setdefault("message_ids", {}).get(uid) or seed_message_ids.get(uid)
            text = rps_prompt_text(session, uid)
            if message_id:
                try:
                    await client.edit_message_text(int(uid), int(message_id), text, reply_markup=kb.ikb_rps_choice(session["id"]))
                    session["message_ids"][uid] = int(message_id)
                    continue
                except Exception:
                    pass
            sent = await client.send_message(int(uid), text, reply_markup=kb.ikb_rps_choice(session["id"]))
            if sent:
                session["message_ids"][uid] = sent.id
        except Exception:
            pass


async def cleanup_rps_messages(client, session):
    session["message_ids"] = {}


async def edit_rps_message(client, session, uid, text, reply_markup=None):
    message_id = (session.get("message_ids") or {}).get(str(uid))
    if message_id:
        try:
            await client.edit_message_text(int(uid), int(message_id), text, reply_markup=reply_markup)
            return
        except Exception:
            pass
    try:
        sent = await client.send_message(int(uid), text, reply_markup=reply_markup)
        if sent:
            session.setdefault("message_ids", {})[str(uid)] = sent.id
    except Exception:
        pass


def rps_round_winner(session, reason="completed"):
    choices = session.get("choices", {})
    p1, p2 = session["players"]
    c1, c2 = choices.get(p1), choices.get(p2)

    winner = None
    if c1 and c2:
        result = rps_result(c1, c2)
        if result == "a":
            winner = p1
        elif result == "b":
            winner = p2
    elif c1 and not c2:
        winner = p1
    elif c2 and not c1:
        winner = p2
    return winner, c1, c2


def rps_round_result_line(winner, uid, reason, c1, c2):
    if winner is None:
        if reason == "timeout" and not c1 and not c2:
            return "⏳ زمان تمام شد و هیچ‌کدام انتخاب نکردید. این دست بدون امتیاز شد."
        return "🤝 این دست مساوی شد."
    if winner == uid:
        return "🏆 این دست را بردید."
    return "❌ این دست را باختید."


async def finish_rps_round(client, session, reason="completed"):
    if session.get("status") != "active":
        return
    winner, c1, c2 = rps_round_winner(session, reason=reason)
    if winner is not None:
        session["scores"][winner] = safe_int(session["scores"].get(winner, 0), 0) + 1
    session["history"].append({
        "round": session.get("current_round", 1), "choices": dict(session.get("choices") or {}),
        "winner": winner, "reason": reason,
    })
    round_result_texts = {}
    for uid in session["players"]:
        choices = session.get("choices", {})
        my_choice = choices.get(uid)
        other_id = rps_other_player(session, uid)
        other_choice = choices.get(other_id)
        result_line = rps_round_result_line(winner, uid, reason, c1, c2)
        round_result_texts[uid] = (
            f"📍 نتیجه دست قبل\n"
            f"انتخاب شما: {RPS_CHOICES.get(my_choice, 'انتخاب نشد')}\n"
            f"انتخاب حریف: {RPS_CHOICES.get(other_choice, 'انتخاب نشد')}\n"
            f"{result_line}"
        )

    if safe_int(session.get("current_round", 1), 1) >= safe_int(session.get("total_rounds", config.RPS_TOTAL_ROUNDS), config.RPS_TOTAL_ROUNDS):
        session["last_round_texts"] = round_result_texts
        await finish_rps_session(client, session)
        return

    session["current_round"] = safe_int(session.get("current_round", 1), 1) + 1
    session["choices"] = {}
    session["deadline"] = now_ts() + config.RPS_TIMEOUT_SECONDS
    session["last_round_texts"] = round_result_texts
    await send_rps_prompts(client, session)


async def finish_rps_session(client, session):
    if session.get("status") != "active":
        return
    session["status"] = "finished"
    p1, p2 = session["players"]
    s1 = safe_int((session.get("scores") or {}).get(p1, 0), 0)
    s2 = safe_int((session.get("scores") or {}).get(p2, 0), 0)
    winner = p1 if s1 > s2 else (p2 if s2 > s1 else None)
    session["winner_id"] = winner
    clear_rps_active_binding(session)

    for uid in session["players"]:
        other_id = rps_other_player(session, uid)
        if winner is None:
            result_line = "🤝 بازی نهایی مساوی شد."
        elif winner == uid:
            result_line = "🏆 بازی را بردید."
        else:
            result_line = "❌ بازی را باختید."
        text = (
            "🎮 نتیجه نهایی سنگ کاغذ قیچی\n\n"
            f"{((session.get('last_round_texts') or {}).get(uid) or '')}\n\n"
            f"تعداد دست‌ها: {safe_int(session.get('total_rounds', config.RPS_TOTAL_ROUNDS), config.RPS_TOTAL_ROUNDS)}\n"
            f"امتیاز شما: {safe_int(session['scores'].get(uid, 0), 0)}\n"
            f"امتیاز حریف: {safe_int(session['scores'].get(other_id, 0), 0)}\n\n"
            f"{result_line}"
        )
        reply_markup = kb.kb_chat_menu() if session.get("source") == "chat" else kb.kb_main_menu()
        await edit_rps_message(client, session, uid, text, reply_markup=reply_markup)


async def cleanup_expired_rps_sessions(client):
    """فراخوانی دوره‌ای (در background.py) برای پایان‌دادن به دست‌های منقضی‌شده."""
    now = now_ts()
    for session_id, session in list(runtime["rps_sessions"].items()):
        if session.get("status") != "active":
            continue
        if safe_int(session.get("deadline", 0), 0) <= now:
            await finish_rps_round(client, session, reason="timeout")


async def start_rps_game(client, player_a, player_b, source="random", seed_message_ids=None):
    player_a, player_b = str(player_a), str(player_b)
    if not player_a or not player_b or player_a == player_b:
        return None
    if rps_session_of(player_a) or rps_session_of(player_b):
        return None
    ua = await db.get_user(player_a, create_if_missing=False)
    ub = await db.get_user(player_b, create_if_missing=False)
    if (ua and ua.get("bot_banned") and not is_admin_id(player_a)) or (ub and ub.get("bot_banned") and not is_admin_id(player_b)):
        return None
    clear_rps_queue(player_a)
    clear_rps_queue(player_b)
    session = make_rps_session(player_a, player_b, source)
    await send_rps_prompts(client, session, seed_message_ids=seed_message_ids)
    return session


async def start_rps_random(client, chat_id, user):
    uid = str(chat_id)
    if rps_session_of(uid):
        await client.send_message(chat_id, "شما الان داخل یک بازی سنگ کاغذ قیچی فعال هستی.")
        return
    if uid in runtime["rps_waiting_random"]:
        await client.send_message(chat_id, "⏳ برای سنگ کاغذ قیچی شانسی در صف هستی.", reply_markup=kb.ikb_rps_queue_cancel(uid))
        return

    opponent_id = None
    while runtime["rps_waiting_random"]:
        candidate = runtime["rps_waiting_random"].pop(0)
        if candidate != uid and not rps_session_of(candidate):
            opponent_id = candidate
            break

    if opponent_id is None:
        runtime["rps_waiting_random"].append(uid)
        await client.send_message(
            chat_id, "⏳ برای سنگ کاغذ قیچی شانسی در صف قرار گرفتی. به محض ورود نفر دوم بازی شروع می‌شود.",
            reply_markup=kb.ikb_rps_queue_cancel(uid),
        )
        return

    session = await start_rps_game(client, opponent_id, uid, source="random")
    if session is None:
        await client.send_message(chat_id, "اتصال برای سنگ کاغذ قیچی شانسی انجام نشد. دوباره تلاش کن.")


async def send_rps_link(client, chat_id, user):
    if str(chat_id) in runtime["rps_waiting_random"]:
        await client.send_message(
            chat_id, "شما در صف شانسی هستی. اول از صف خارج شو، بعد لینک بساز.", reply_markup=kb.ikb_rps_queue_cancel(str(chat_id))
        )
        return
    rps_link = await build_start_link(client, f"rps_{chat_id}")
    await client.send_message(
        chat_id,
        "با این لینک می‌تونی با دوستت سنگ کاغذ قیچی بازی کنی.\n"
        "بعد از ورود طرف مقابل، تایید شروع بازی برای شما ارسال می‌شود.\n\n"
        "*لینک اختصاصی شما👇*\n"
        f"{rps_link}",
    )


async def send_chat_rps_invite(client, chat_id, user):
    inviter_id = str(chat_id)
    peer_id = str(user.get("chat_with") or "")
    if not peer_id:
        await client.send_message(chat_id, "💬 هنوز به مخاطبی وصل نیستی. اول وارد چت ناشناس شو، بعد سنگ کاغذ قیچی رو شروع کن.", reply_markup=kb.kb_chat_menu())
        return
    if rps_session_of(inviter_id) or rps_session_of(peer_id):
        await client.send_message(chat_id, "✂️ یک بازی سنگ کاغذ قیچی بین شما فعاله. اول همون رو تموم کن، بعد بازی تازه بساز.", reply_markup=kb.kb_chat_menu())
        return

    peer_user = await db.get_user(peer_id, create_if_missing=False)
    if not peer_user or str(peer_user.get("chat_with") or "") != inviter_id:
        await client.send_message(chat_id, "⛔ این چت دیگر فعال نیست. برگشتی به منوی اصلی.", reply_markup=kb.kb_main_menu())
        return

    for pending_inviter, pending_peer in list(runtime["pending_chat_rps_invites"].items()):
        pending_peer_id = pending_peer.get("peer_id") if isinstance(pending_peer, dict) else pending_peer
        if pending_inviter in (inviter_id, peer_id) or pending_peer_id in (inviter_id, peer_id):
            runtime["pending_chat_rps_invites"].pop(pending_inviter, None)

    pending_payload = {"peer_id": peer_id, "inviter_msg_id": None}
    inviter_name = (user.get("display_name") or "هم‌صحبت ناشناس").strip()
    await client.send_message(
        int(peer_id),
        "✂️ *دعوت به سنگ کاغذ قیچی داخل چت*\n\n"
        f"{inviter_name} می‌خواد باهات چند دست بازی کنه.\n"
        "قبول می‌کنی؟ 👇",
        reply_markup=kb.ikb_chat_rps_invite(inviter_id),
    )
    sent = await client.send_message(
        chat_id,
        "✅ دعوت سنگ کاغذ قیچی ارسال شد.\n\nمنتظر جواب مخاطبت بمون؛ نتیجه همین‌جا مشخص می‌شه.",
        reply_markup=kb.ikb_chat_rps_cancel(inviter_id),
    )
    if sent:
        pending_payload["inviter_msg_id"] = sent.id
    runtime["pending_chat_rps_invites"][inviter_id] = pending_payload


async def start_rps_from_link(client, joiner_id, host_id) -> bool:
    joiner_id, host_id = str(joiner_id), str(host_id)
    if not joiner_id or not host_id or joiner_id == host_id:
        return False
    host_user = await db.get_user(host_id, create_if_missing=False)
    if not host_user:
        return False
    if rps_session_of(joiner_id):
        await client.send_message(int(joiner_id), "شما الان داخل یک بازی سنگ کاغذ قیچی فعال هستی.")
        return True
    if rps_session_of(host_id):
        await client.send_message(int(joiner_id), "این کاربر الان داخل بازی سنگ کاغذ قیچی است. کمی بعد دوباره تلاش کن.")
        return True

    for rid, payload in list(runtime["rps_link_requests"].items()):
        if str(payload.get("joiner_id")) == joiner_id:
            runtime["rps_link_requests"].pop(rid, None)

    runtime["rps_link_request_counter"] += 1
    request_id = runtime["rps_link_request_counter"]
    runtime["rps_link_requests"][request_id] = {"host_id": host_id, "joiner_id": joiner_id, "status": "pending"}

    joiner_user = await db.get_user(joiner_id, create_if_missing=False) or {}
    joiner_pid = joiner_user.get("public_id") or "-"
    sent = None
    try:
        sent = await client.send_message(
            int(host_id),
            f"کاربر `{joiner_id}` /user_{joiner_pid} با لینک سنگ کاغذ قیچی شما وارد شد.\n"
            "برای شروع بازی، درخواست را تایید کن👇",
            reply_markup=kb.ikb_rps_link_request(request_id),
        )
    except Exception:
        sent = None
    if not sent:
        runtime["rps_link_requests"].pop(request_id, None)
        await client.send_message(int(joiner_id), "ارسال درخواست به صاحب لینک ناموفق بود.")
        return True
    await client.send_message(int(joiner_id), "درخواست بازی برای طرف مقابل ارسال شد. منتظر تایید بمان.")
    return True


# ---------------------------------------------------------------------------
# دکمه‌های منو
# ---------------------------------------------------------------------------
@bot.on_message(equals("سنگ کاغذ قیچی ✂️") & private)
async def msg_rps_menu_button(client, message):
    await client.send_message(
        message.chat.id,
        "*یکی از گزینه های زیر را انتخاب کنید:*\nسنگ کاغذ قیچی شانسی🎲\nسنگ کاغذ قیچی با لینک🎮",
        reply_markup=kb.kb_rps_menu(), reply_to_message_id=message.id,
    )


@bot.on_message(equals("سنگ کاغذ قیچی شانسی🎲") & private)
async def msg_rps_random_button(client, message):
    user = await get_event_user(message)
    await start_rps_random(client, message.chat.id, user)


@bot.on_message(equals("سنگ کاغذ قیچی با لینک🎮") & private)
async def msg_rps_link_button(client, message):
    user = await get_event_user(message)
    await send_rps_link(client, message.chat.id, user)


# ---------------------------------------------------------------------------
# کال‌بک‌های بازی
# ---------------------------------------------------------------------------
@bot.on_callback_query(regex(r"^rps:qcancel:") & private)
async def cb_rps_qcancel(client, callback_query):
    parts = callback_query.data.split(":")
    owner_id = parts[2] if len(parts) == 3 else ""
    uid = str(callback_query.author.id)
    if owner_id != uid:
        await callback_query.answer("این دکمه برای شما نیست.", show_alert=True)
        return
    if owner_id not in runtime["rps_waiting_random"]:
        await callback_query.answer("شما داخل صف جستجو نیستی.", show_alert=True)
        return
    clear_rps_queue(owner_id)
    await callback_query.answer("از صف جستجو خارج شدی ✅")
    await client.edit_message_text(callback_query.message.chat.id, callback_query.message.id, "✅ جستجوی سنگ کاغذ قیچی شانسی لغو شد.")


@bot.on_callback_query(regex(r"^rps:linkreq:") & private)
async def cb_rps_linkreq(client, callback_query):
    parts = callback_query.data.split(":")
    if len(parts) != 4 or parts[2] not in ("yes", "no"):
        await callback_query.answer("داده نامعتبر است.", show_alert=True)
        return
    action, request_id = parts[2], safe_int(parts[3], 0)
    payload = runtime["rps_link_requests"].get(request_id)
    if not payload:
        await callback_query.answer("این درخواست منقضی شده.", show_alert=True)
        return
    host_id, joiner_id = str(payload.get("host_id") or ""), str(payload.get("joiner_id") or "")
    uid = str(callback_query.author.id)
    if uid != host_id:
        await callback_query.answer("این دکمه برای شما نیست.", show_alert=True)
        return
    if payload.get("status") != "pending":
        await callback_query.answer("این درخواست قبلا رسیدگی شده.", show_alert=True)
        return
    if action == "no":
        payload["status"] = "rejected"
        runtime["rps_link_requests"].pop(request_id, None)
        await callback_query.answer("درخواست رد شد.")
        await client.edit_message_text(callback_query.message.chat.id, callback_query.message.id, "❌ دعوت سنگ کاغذ قیچی رد شد.")
        await client.send_message(int(joiner_id), "درخواست بازی سنگ کاغذ قیچی شما توسط طرف مقابل رد شد.")
        return
    if rps_session_of(host_id) or rps_session_of(joiner_id):
        payload["status"] = "expired"
        runtime["rps_link_requests"].pop(request_id, None)
        await callback_query.answer("یکی از بازیکن‌ها الان داخل بازی است.", show_alert=True)
        await client.edit_message_text(
            callback_query.message.chat.id, callback_query.message.id,
            "⛔ شروع بازی ممکن نیست (یکی از بازیکن‌ها داخل بازی است).",
        )
        await client.send_message(int(joiner_id), "شروع بازی ممکن نشد؛ یکی از بازیکن‌ها داخل بازی است.")
        return
    payload["status"] = "approved"
    runtime["rps_link_requests"].pop(request_id, None)
    await callback_query.answer("درخواست تایید شد ✅")
    await client.edit_message_text(callback_query.message.chat.id, callback_query.message.id, "✅ درخواست تایید شد. بازی شروع می‌شود...")
    session = await start_rps_game(client, host_id, joiner_id, source="link", seed_message_ids={host_id: callback_query.message.id})
    if session is None:
        await client.send_message(int(host_id), "شروع بازی ممکن نشد. دوباره تلاش کن.")
        await client.send_message(int(joiner_id), "شروع بازی ممکن نشد. دوباره تلاش کن.")


@bot.on_callback_query(regex(r"^rps:pick:") & private)
async def cb_rps_pick(client, callback_query):
    parts = callback_query.data.split(":")
    if len(parts) != 4:
        await callback_query.answer("داده نامعتبر است.", show_alert=True)
        return
    session_id, choice = safe_int(parts[2], 0), parts[3]
    session = runtime["rps_sessions"].get(session_id)
    uid = str(callback_query.author.id)
    if not session or session.get("status") != "active":
        await callback_query.answer("این بازی دیگر فعال نیست.", show_alert=True)
        return
    if uid not in session["players"]:
        await callback_query.answer("این بازی برای شما نیست.", show_alert=True)
        return
    if choice not in RPS_CHOICES:
        await callback_query.answer("انتخاب نامعتبر است.", show_alert=True)
        return
    if uid in session["choices"]:
        await callback_query.answer("قبلا انتخاب کردی.", show_alert=True)
        return
    if safe_int(session.get("deadline", 0), 0) <= now_ts():
        await finish_rps_round(client, session, reason="timeout")
        await callback_query.answer("زمان بازی تمام شده.", show_alert=True)
        return

    session["choices"][uid] = choice
    other_id = rps_other_player(session, uid)
    if other_id in session["choices"]:
        await callback_query.answer("انتخاب ثبت شد؛ نتیجه همین‌جا میاد ✅")
        await finish_rps_round(client, session)
    else:
        await callback_query.answer("انتخاب ثبت شد؛ منتظر حریف بمان ✅")
        await send_rps_prompts(client, session)


@bot.on_callback_query(regex(r"^rps:leave:") & private)
async def cb_rps_leave(client, callback_query):
    parts = callback_query.data.split(":")
    session_id = safe_int(parts[2], 0) if len(parts) == 3 else 0
    session = runtime["rps_sessions"].get(session_id)
    uid = str(callback_query.author.id)
    if not session or session.get("status") != "active":
        await callback_query.answer("این بازی دیگر فعال نیست.", show_alert=True)
        return
    if uid not in session["players"]:
        await callback_query.answer("این بازی برای شما نیست.", show_alert=True)
        return
    other_id = rps_other_player(session, uid)
    session["status"] = "cancelled"
    clear_rps_active_binding(session)
    runtime["rps_sessions"].pop(session_id, None)
    await callback_query.answer("از بازی خارج شدی ✅")
    await edit_rps_message(client, session, uid, "✅ از سنگ کاغذ قیچی خارج شدی. بازی لغو شد.")
    reply_markup = kb.kb_chat_menu() if session.get("source") == "chat" else kb.kb_main_menu()
    await edit_rps_message(client, session, other_id, "🚪 مخاطبت از سنگ کاغذ قیچی خارج شد؛ بازی لغو شد.", reply_markup=reply_markup)


@bot.on_callback_query(regex(r"^chat_rps:") & private)
async def cb_chat_rps(client, callback_query):
    parts = callback_query.data.split(":")
    if len(parts) != 3 or parts[1] not in ("accept", "reject", "cancel"):
        await callback_query.answer("داده نامعتبر است.", show_alert=True)
        return
    action, inviter_id = parts[1], parts[2]
    receiver_id = str(callback_query.author.id)

    if action == "cancel":
        if receiver_id != inviter_id:
            await callback_query.answer("این دکمه برای شما نیست.", show_alert=True)
            return
        payload = runtime["pending_chat_rps_invites"].pop(inviter_id, None)
        target_peer = payload.get("peer_id") if isinstance(payload, dict) else payload
        await callback_query.answer("دعوت لغو شد ✅")
        await client.edit_message_text(callback_query.message.chat.id, callback_query.message.id, "❎ دعوت سنگ کاغذ قیچی لغو شد.")
        if target_peer:
            await client.send_message(int(target_peer), "❎ مخاطبت دعوت سنگ کاغذ قیچی رو لغو کرد.", reply_markup=kb.kb_chat_menu())
        return

    payload = runtime["pending_chat_rps_invites"].get(inviter_id)
    target_peer = payload.get("peer_id") if isinstance(payload, dict) else payload
    if target_peer != receiver_id:
        await callback_query.answer("این درخواست منقضی شده.", show_alert=True)
        return

    if action == "reject":
        runtime["pending_chat_rps_invites"].pop(inviter_id, None)
        await callback_query.answer("دعوت رد شد")
        await client.send_message(int(inviter_id), "❌ مخاطبت دعوت سنگ کاغذ قیچی رو رد کرد.", reply_markup=kb.kb_chat_menu())
        await client.edit_message_text(callback_query.message.chat.id, callback_query.message.id, "❌ دعوت سنگ کاغذ قیچی رد شد.")
        return

    inviter_user = await db.get_user(inviter_id, create_if_missing=False)
    receiver_user = await db.get_user(receiver_id, create_if_missing=False)
    if (
        not inviter_user
        or not receiver_user
        or str(inviter_user.get("chat_with") or "") != receiver_id
        or str(receiver_user.get("chat_with") or "") != inviter_id
    ):
        runtime["pending_chat_rps_invites"].pop(inviter_id, None)
        await callback_query.answer("چت فعال نیست.", show_alert=True)
        await client.edit_message_text(callback_query.message.chat.id, callback_query.message.id, "⛔ این چت دیگر فعال نیست.")
        return

    if rps_session_of(inviter_id) or rps_session_of(receiver_id):
        await callback_query.answer("یکی از بازیکن‌ها داخل بازی است.", show_alert=True)
        return

    runtime["pending_chat_rps_invites"].pop(inviter_id, None)
    seed_message_ids = {receiver_id: callback_query.message.id}
    if isinstance(payload, dict) and payload.get("inviter_msg_id"):
        seed_message_ids[inviter_id] = payload["inviter_msg_id"]
    session = await start_rps_game(client, inviter_id, receiver_id, source="chat", seed_message_ids=seed_message_ids)
    if session is None:
        await callback_query.answer("شروع بازی ناموفق بود.", show_alert=True)
        return
    await callback_query.answer("بازی شروع شد ✅")


