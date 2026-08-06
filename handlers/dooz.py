"""بازی دوز (Tic-Tac-Toe): شانسی، با لینک، یا داخل چت با مخاطب."""
import os

from balethon.conditions import equals, regex,private

import config
import database as db
import keyboards as kb
from bot_links import build_start_link
from bot_instance import bot, runtime
from filters import get_event_user, is_admin_id
from utils import safe_int

_WINNING_LINES = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
)


def _pair_key(a, b):
    return (a, b) if int(a) < int(b) else (b, a)


def _pick_starter(a, b):
    key = _pair_key(a, b)
    next_starter = runtime["dooz_pair_next_starter"].get(key)
    if next_starter not in (a, b):
        next_starter = key[0]
    runtime["dooz_pair_next_starter"][key] = b if next_starter == a else a
    return next_starter


def session_of(uid):
    sid = runtime["dooz_user_session"].get(str(uid))
    return runtime["dooz_sessions"].get(sid) if sid is not None else None


def _clear_queue(uid):
    uid = str(uid)
    while uid in runtime["dooz_waiting_random"]:
        runtime["dooz_waiting_random"].remove(uid)


def _clear_binding(session):
    for uid in session["players"]:
        if runtime["dooz_user_session"].get(uid) == session["id"]:
            runtime["dooz_user_session"].pop(uid, None)


def _board_text_for(session, viewer_id):
    my_mark = session["marks"][viewer_id]
    other_id = session["players"][0] if session["players"][1] == viewer_id else session["players"][1]
    other_mark = session["marks"][other_id]
    turn_text = "نوبت شماست." if session["turn"] == viewer_id else "نوبت طرف مقابله."
    return (
        "🎮 بازی دوز\n"
        f"علامت شما: {kb.dooz_symbol(my_mark)}\n"
        f"علامت حریف: {kb.dooz_symbol(other_mark)}\n"
        f"{turn_text}"
    )


async def _cleanup_board_messages(client, session):
    for uid, message_id in dict(session.get("board_message_ids") or {}).items():
        if not message_id:
            continue
        try:
            await client.delete_message(int(uid), int(message_id))
        except Exception:
            pass
    session["board_message_ids"] = {}


async def _send_board(client, session):
    for uid in session["players"]:
        try:
            old_mid = session.get("board_message_ids", {}).get(uid)
            if old_mid:
                try:
                    await client.delete_message(int(uid), int(old_mid))
                except Exception:
                    pass
            sent = await client.send_message(
                int(uid), _board_text_for(session, uid), reply_markup=kb.ikb_dooz_board(session["id"], session["board"])
            )
            if sent:
                session.setdefault("board_message_ids", {})[uid] = sent.id
        except Exception:
            pass


def _winner(board):
    for i, j, k in _WINNING_LINES:
        if board[i] and board[i] == board[j] == board[k]:
            return board[i]
    return None


async def _finish_session(client, session, winner_mark):
    session["status"] = "finished"
    await _cleanup_board_messages(client, session)
    if winner_mark is None:
        result_by_user = {uid: "مساوی شدید" for uid in session["players"]}
    else:
        winner_user = session["players"][0] if session["marks"][session["players"][0]] == winner_mark else session["players"][1]
        session["winner_id"] = winner_user
        if session.get("source") == "random" and config.DOOZ_RANDOM_WIN_REWARD_COIN > 0:
            wu = await db.get_user(winner_user, create_if_missing=False)
            if wu:
                wu["coins"] = safe_int(wu.get("coins", 0), 0) + config.DOOZ_RANDOM_WIN_REWARD_COIN
                await db.save_user(winner_user, wu)
        result_by_user = {}
        for uid in session["players"]:
            if uid == winner_user and session.get("source") == "random" and config.DOOZ_RANDOM_WIN_REWARD_COIN > 0:
                result_by_user[uid] = f"بردید\n🏆 جایزه: {config.DOOZ_RANDOM_WIN_REWARD_COIN} سکه"
            else:
                result_by_user[uid] = "بردید" if uid == winner_user else "باختید"

    _clear_binding(session)
    for uid in session["players"]:
        try:
            await client.send_message(int(uid), result_by_user[uid], reply_markup=kb.ikb_dooz_rematch(session["id"]))
        except Exception:
            pass


async def _start_game(client, player_a, player_b, source="random"):
    player_a, player_b = str(player_a), str(player_b)
    if not player_a or not player_b or player_a == player_b:
        return None
    if session_of(player_a) or session_of(player_b):
        return None
    ua = await db.get_user(player_a, create_if_missing=False)
    ub = await db.get_user(player_b, create_if_missing=False)
    if (ua and ua.get("bot_banned") and not is_admin_id(player_a)) or (ub and ub.get("bot_banned") and not is_admin_id(player_b)):
        return None

    _clear_queue(player_a)
    _clear_queue(player_b)

    starter = _pick_starter(player_a, player_b)
    other = player_b if starter == player_a else player_a
    runtime["dooz_session_counter"] += 1
    session_id = runtime["dooz_session_counter"]
    session = {
        "id": session_id, "source": source, "players": [starter, other], "board": [""] * 9,
        "marks": {starter: "X", other: "O"}, "turn": starter, "status": "active", "winner_id": None,
        "rematch_requests": set(), "board_message_ids": {},
    }
    runtime["dooz_sessions"][session_id] = session
    runtime["dooz_user_session"][starter] = session_id
    runtime["dooz_user_session"][other] = session_id

    for uid in session["players"]:
        try:
            await client.send_message(int(uid), "*بازی شروع شد✨*")
        except Exception:
            pass
    await _send_board(client, session)
    return session


async def start_dooz_random(client, chat_id, user):
    uid = str(chat_id)
    entry_coin = max(0, config.DOOZ_RANDOM_ENTRY_COIN)
    win_reward = max(0, config.DOOZ_RANDOM_WIN_REWARD_COIN)
    if session_of(uid):
        await client.send_message(chat_id, "شما الان داخل یک بازی دوز فعال هستی.")
        return
    if uid in runtime["dooz_waiting_random"]:
        await client.send_message(
            chat_id,
            f"🎲 ورودی این بازی: {entry_coin} سکه | 🏆 جایزه برد: {win_reward} سکه\n\n"
            "⏳ برای بازی دوز شانسی در صف هستی. منتظر بازیکن دوم بمان.",
            reply_markup=kb.ikb_dooz_queue_cancel(uid),
        )
        return
    if entry_coin > 0:
        if safe_int(user.get("coins", 0), 0) < entry_coin:
            await client.send_message(chat_id, f"❌ برای دوز شانسی {entry_coin} سکه ورودی لازم است.\nموجودی شما کافی نیست.")
            return
        user["coins"] = safe_int(user.get("coins", 0), 0) - entry_coin
        await db.save_user(chat_id, user)

    opponent_id = None
    while runtime["dooz_waiting_random"]:
        candidate = runtime["dooz_waiting_random"].pop(0)
        if candidate != uid and not session_of(candidate):
            opponent_id = candidate
            break

    if opponent_id is None:
        runtime["dooz_waiting_random"].append(uid)
        await client.send_message(
            chat_id,
            f"🎲 ورودی این بازی: {entry_coin} سکه | 🏆 جایزه برد: {win_reward} سکه\n\n"
            "⏳ برای دوز شانسی در صف قرار گرفتی. به محض ورود نفر دوم بازی شروع می‌شود.",
            reply_markup=kb.ikb_dooz_queue_cancel(uid),
        )
        return

    session = await _start_game(client, opponent_id, uid, source="random")
    if session is None:
        await client.send_message(chat_id, "اتصال برای دوز شانسی انجام نشد. دوباره تلاش کن.")


async def send_dooz_link(client, chat_id, user):
    if str(chat_id) in runtime["dooz_waiting_random"]:
        await client.send_message(
            chat_id, "شما در صف دوز شانسی هستی. اول از صف خارج شو، بعد دوز با لینک را شروع کن.",
            reply_markup=kb.ikb_dooz_queue_cancel(str(chat_id)),
        )
        return
    dooz_link = await build_start_link(client, f"dooz_{chat_id}")
    text = (
        "با استفاده از این لینک می‌توانید بازی را به صورت مستقیم با دوستانتان شروع کنید.🪅\n"
        "کافی است لینک را برای شخص مورد نظر ارسال کنید و بعد از تایید شما بازی آغاز می‌شود.\n\n"
        "*لینک اختصاصی شما👇*\n"
        f"{dooz_link}"
    )
    await client.send_message(chat_id, text)
    caption = (
        "*سلام!*\n"
        "می‌خوای با هم دوز بازی کنیم؟🎲\n"
        "روی لینک زیر بزنی، مستقیم وارد بازی می‌شی و می‌تونیم شروع کنیم👻\n\n"
        f"{dooz_link}"
    )
    img_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "images", "dooz.jpg")
    if os.path.isfile(img_path):
        try:
            await client.send_photo(chat_id, img_path, caption=caption)
            return
        except Exception:
            pass
    await client.send_message(chat_id, caption)


async def start_dooz_from_link(client, joiner_id, host_id) -> bool:
    joiner_id, host_id = str(joiner_id), str(host_id)
    if not joiner_id or not host_id or joiner_id == host_id:
        return False
    host_user = await db.get_user(host_id, create_if_missing=False)
    if not host_user:
        return False
    if joiner_id in runtime["dooz_waiting_random"]:
        await client.send_message(
            int(joiner_id), "شما در صف دوز شانسی هستی. اول از صف خارج شو و بعد با لینک وارد بازی شو.",
            reply_markup=kb.ikb_dooz_queue_cancel(joiner_id),
        )
        return True
    if session_of(joiner_id):
        await client.send_message(int(joiner_id), "شما الان داخل یک بازی دوز فعال هستی.")
        return True
    if session_of(host_id):
        await client.send_message(int(joiner_id), "این کاربر الان داخل بازی دوز است. کمی بعد دوباره تلاش کن.")
        return True

    for rid, payload in list(runtime["dooz_link_requests"].items()):
        if str(payload.get("joiner_id")) == joiner_id:
            runtime["dooz_link_requests"].pop(rid, None)

    runtime["dooz_link_request_counter"] += 1
    request_id = runtime["dooz_link_request_counter"]
    runtime["dooz_link_requests"][request_id] = {"host_id": host_id, "joiner_id": joiner_id, "status": "pending"}

    joiner_user = await db.get_user(joiner_id, create_if_missing=False) or {}
    joiner_pid = joiner_user.get("public_id") or "-"
    sent = None
    try:
        sent = await client.send_message(
            int(host_id),
            f"کاربر `{joiner_id}` /user_{joiner_pid} با لینک دوز شما وارد شد💥\n"
            "برای شروع بازی، درخواست را تایید کن👇",
            reply_markup=kb.ikb_dooz_link_request(request_id),
        )
    except Exception:
        sent = None
    if not sent:
        runtime["dooz_link_requests"].pop(request_id, None)
        await client.send_message(int(joiner_id), "ارسال درخواست به صاحب لینک ناموفق بود.")
        return True
    await client.send_message(int(joiner_id), "درخواست بازی برای طرف مقابل ارسال شد. منتظر تایید بمان.")
    return True


async def send_chat_dooz_invite(client, chat_id, user):
    inviter_id = str(chat_id)
    peer_id = str(user.get("chat_with") or "")
    if not peer_id:
        await client.send_message(chat_id, "💬 هنوز به مخاطبی وصل نیستی. اول وارد چت ناشناس شو، بعد بازی دوز رو شروع کن.", reply_markup=kb.kb_chat_menu())
        return
    if session_of(inviter_id) or session_of(peer_id):
        await client.send_message(chat_id, "🎮 یک بازی دوز بین شما فعاله. اول همون رو تموم کن، بعد بازی تازه بساز.", reply_markup=kb.kb_chat_menu())
        return
    runtime["pending_chat_dooz_invites"][inviter_id] = peer_id
    inviter_name = (user.get("display_name") or "هم‌صحبت ناشناس").strip()
    await client.send_message(
        int(peer_id),
        "🎮 *دعوت به دوز داخل چت*\n\n"
        f"{inviter_name} می‌خواد باهات یه دست دوز بازی کنه.\n"
        "قبول می‌کنی؟ 👇",
        reply_markup=kb.ikb_chat_dooz_invite(inviter_id),
    )
    await client.send_message(chat_id, "✅ دعوت دوز ارسال شد.\n\nمنتظر جواب مخاطبت بمون؛ همین‌جا خبرت می‌کنم.", reply_markup=kb.ikb_chat_dooz_cancel(inviter_id))


# ---------------------------------------------------------------------------
# دکمه‌های منو
# ---------------------------------------------------------------------------
@bot.on_message(equals("دوز 🎰") & private)
async def msg_dooz_menu_button(client, message):
    await client.send_message(
        message.chat.id, "*یکی از گزینه های زیر را انتخاب کنید:*\nدوز شانسی🎲\nدوز با لینک🎮",
        reply_markup=kb.kb_dooz_menu(), reply_to_message_id=message.id,
    )


@bot.on_message(equals("دوز شانسی🎲") & private)
async def msg_dooz_random_button(client, message):
    user = await get_event_user(message)
    await start_dooz_random(client, message.chat.id, user)


@bot.on_message(equals("دوز با لینک🎮") & private)
async def msg_dooz_link_button(client, message):
    user = await get_event_user(message)
    await send_dooz_link(client, message.chat.id, user)


# ---------------------------------------------------------------------------
# کال‌بک‌های بازی
# ---------------------------------------------------------------------------
@bot.on_callback_query(regex(r"^dooz:qcancel:") & private)
async def cb_dooz_qcancel(client, callback_query):
    parts = callback_query.data.split(":")
    owner_id = parts[2] if len(parts) == 3 else ""
    uid = str(callback_query.author.id)
    if owner_id != uid:
        await callback_query.answer("این دکمه برای شما نیست.", show_alert=True)
        return
    if owner_id not in runtime["dooz_waiting_random"]:
        await callback_query.answer("شما داخل صف جستجو نیستی.", show_alert=True)
        return
    _clear_queue(owner_id)
    await callback_query.answer("از صف جستجو خارج شدی ✅")
    await client.edit_message_text(callback_query.message.chat.id, callback_query.message.id, "✅ جستجوی دوز شانسی لغو شد.")


@bot.on_callback_query(equals("dooz:noop") & private)
async def cb_dooz_noop(client, callback_query):
    await callback_query.answer("خانه قبلا انتخاب شده است.", show_alert=True)


@bot.on_callback_query(regex(r"^dooz:leaveask:") & private)
async def cb_dooz_leaveask(client, callback_query):
    parts = callback_query.data.split(":")
    session_id = safe_int(parts[2], 0) if len(parts) == 3 else 0
    session = runtime["dooz_sessions"].get(session_id)
    uid = str(callback_query.author.id)
    if not session or session.get("status") != "active":
        await callback_query.answer("این بازی دیگر فعال نیست.", show_alert=True)
        return
    if uid not in session["players"]:
        await callback_query.answer("این بازی برای شما نیست.", show_alert=True)
        return
    await callback_query.answer("تایید خروج از بازی")
    await client.send_message(
        callback_query.message.chat.id, "⚠️ مطمئنی می‌خوای از دوز خارج بشی؟\n\nبا خروج شما، بازی برای هر دو نفر لغو می‌شه.",
        reply_markup=kb.ikb_dooz_leave_confirm(session_id, uid), reply_to_message_id=callback_query.message.id,
    )


@bot.on_callback_query(regex(r"^dooz:leave:") & private)
async def cb_dooz_leave(client, callback_query):
    parts = callback_query.data.split(":")
    if len(parts) != 5 or parts[2] not in ("yes", "no"):
        await callback_query.answer("داده نامعتبر است.", show_alert=True)
        return
    action, session_id, owner_id = parts[2], safe_int(parts[3], 0), parts[4]
    uid = str(callback_query.author.id)
    if owner_id != uid:
        await callback_query.answer("این دکمه برای شما نیست.", show_alert=True)
        return
    session = runtime["dooz_sessions"].get(session_id)
    if not session or session.get("status") != "active":
        await callback_query.answer("این بازی دیگر فعال نیست.", show_alert=True)
        return
    if owner_id not in session["players"]:
        await callback_query.answer("این بازی برای شما نیست.", show_alert=True)
        return
    if action == "no":
        await callback_query.answer("ادامه می‌دیم 🎮")
        await client.edit_message_text(callback_query.message.chat.id, callback_query.message.id, "✅ خروج لغو شد؛ بازی ادامه داره.")
        return
    other_id = session["players"][0] if session["players"][1] == owner_id else session["players"][1]
    session["status"] = "cancelled"
    await _cleanup_board_messages(client, session)
    _clear_binding(session)
    runtime["dooz_sessions"].pop(session_id, None)
    await callback_query.answer("از بازی خارج شدی ✅")
    await client.edit_message_text(callback_query.message.chat.id, callback_query.message.id, "✅ از دوز خارج شدی. بازی لغو شد.")
    await client.send_message(int(other_id), "🚪 مخاطبت از دوز خارج شد؛ بازی لغو شد.", reply_markup=kb.kb_chat_menu() if session.get("source") == "chat" else kb.kb_main_menu())


@bot.on_callback_query(regex(r"^dooz:linkreq:") & private)
async def cb_dooz_linkreq(client, callback_query):
    parts = callback_query.data.split(":")
    if len(parts) != 4 or parts[2] not in ("yes", "no"):
        await callback_query.answer("داده نامعتبر است.", show_alert=True)
        return
    action, request_id = parts[2], safe_int(parts[3], 0)
    payload = runtime["dooz_link_requests"].get(request_id)
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
        runtime["dooz_link_requests"].pop(request_id, None)
        await callback_query.answer("درخواست رد شد.")
        await client.edit_message_text(callback_query.message.chat.id, callback_query.message.id, "❌ دعوت دوز رد شد.")
        await client.send_message(int(joiner_id), "درخواست بازی شما توسط طرف مقابل رد شد.")
        return
    if session_of(host_id) or session_of(joiner_id):
        payload["status"] = "expired"
        runtime["dooz_link_requests"].pop(request_id, None)
        await callback_query.answer("یکی از بازیکن‌ها الان داخل بازی است.", show_alert=True)
        await client.edit_message_text(
            callback_query.message.chat.id, callback_query.message.id,
            "⛔ شروع بازی ممکن نیست (یکی از بازیکن‌ها داخل بازی است).",
        )
        await client.send_message(int(joiner_id), "شروع بازی ممکن نشد؛ یکی از بازیکن‌ها داخل بازی است.")
        return
    payload["status"] = "approved"
    runtime["dooz_link_requests"].pop(request_id, None)
    await callback_query.answer("درخواست تایید شد ✅")
    await client.edit_message_text(callback_query.message.chat.id, callback_query.message.id, "✅ درخواست تایید شد. بازی شروع می‌شود...")
    session = await _start_game(client, host_id, joiner_id, source="link")
    if session is None:
        await client.send_message(int(host_id), "شروع بازی ممکن نشد. دوباره تلاش کن.")
        await client.send_message(int(joiner_id), "شروع بازی ممکن نشد. دوباره تلاش کن.")


@bot.on_callback_query(regex(r"^dooz:mv:") & private)
async def cb_dooz_move(client, callback_query):
    parts = callback_query.data.split(":")
    if len(parts) != 4:
        await callback_query.answer("داده نامعتبر است.", show_alert=True)
        return
    session_id, cell = safe_int(parts[2], 0), safe_int(parts[3], -1)
    session = runtime["dooz_sessions"].get(session_id)
    uid = str(callback_query.author.id)
    if not session:
        await callback_query.answer("این بازی دیگر فعال نیست.", show_alert=True)
        return
    if session.get("status") != "active":
        await callback_query.answer("بازی تمام شده است.", show_alert=True)
        return
    if uid not in session["players"]:
        await callback_query.answer("این بازی برای شما نیست.", show_alert=True)
        return
    if session["turn"] != uid:
        await callback_query.answer("الان نوبت شما نیست.", show_alert=True)
        return
    if cell < 0 or cell > 8:
        await callback_query.answer("حرکت نامعتبر است.", show_alert=True)
        return
    if session["board"][cell]:
        await callback_query.answer("این خانه قبلا انتخاب شده.", show_alert=True)
        return

    session["board"][cell] = session["marks"][uid]
    winner = _winner(session["board"])
    if winner:
        await callback_query.answer("حرکت ثبت شد ✅")
        await _finish_session(client, session, winner)
        return
    if all(session["board"]):
        await callback_query.answer("حرکت ثبت شد ✅")
        await _finish_session(client, session, None)
        return
    current_idx = session["players"].index(uid)
    session["turn"] = session["players"][1 - current_idx]
    await callback_query.answer("حرکت ثبت شد ✅")
    await _send_board(client, session)


@bot.on_callback_query(regex(r"^dooz:rm:req:") & private)
async def cb_dooz_rematch_req(client, callback_query):
    parts = callback_query.data.split(":")
    session_id = safe_int(parts[3], 0) if len(parts) == 4 else 0
    session = runtime["dooz_sessions"].get(session_id)
    uid = str(callback_query.author.id)
    if not session or session.get("status") != "finished":
        await callback_query.answer("این بازی قابل تکرار نیست.", show_alert=True)
        return
    if uid not in session["players"]:
        await callback_query.answer("این بازی برای شما نیست.", show_alert=True)
        return
    if uid in session["rematch_requests"]:
        await callback_query.answer("درخواست شما قبلا ثبت شده.", show_alert=True)
        return
    session["rematch_requests"].add(uid)
    if len(session["rematch_requests"]) == 2:
        await callback_query.answer("هر دو بازیکن آماده‌اند ✅")
        new_session = await _start_game(client, session["players"][0], session["players"][1], source=session["source"])
        if new_session is not None:
            runtime["dooz_sessions"].pop(session_id, None)
        return
    other_id = session["players"][0] if session["players"][1] == uid else session["players"][1]
    await callback_query.answer("درخواست بازی مجدد ثبت شد.")
    await client.send_message(
        int(other_id), "طرف مقابل درخواست بازی مجدد داره", reply_markup=kb.ikb_dooz_rematch_confirm(session_id, uid)
    )


@bot.on_callback_query(regex(r"^dooz:rm:(yes|no):") & private)
async def cb_dooz_rematch_confirm(client, callback_query):
    parts = callback_query.data.split(":")
    if len(parts) != 5:
        await callback_query.answer("داده نامعتبر است.", show_alert=True)
        return
    action, session_id, requester_id = parts[2], safe_int(parts[3], 0), parts[4]
    uid = str(callback_query.author.id)
    session = runtime["dooz_sessions"].get(session_id)
    if not session or session.get("status") != "finished":
        await callback_query.answer("این درخواست منقضی شده.", show_alert=True)
        return
    if uid not in session["players"] or requester_id not in session["players"]:
        await callback_query.answer("داده نامعتبر است.", show_alert=True)
        return
    if uid == requester_id:
        await callback_query.answer("این دکمه برای شما نیست.", show_alert=True)
        return
    if action == "no":
        session["rematch_requests"].clear()
        await callback_query.answer("درخواست رد شد.")
        await client.send_message(int(requester_id), "درخواست بازی مجدد توسط طرف مقابل لغو شد.")
        return
    session["rematch_requests"].add(requester_id)
    session["rematch_requests"].add(uid)
    await callback_query.answer("بازی مجدد تایید شد ✅")
    new_session = await _start_game(client, session["players"][0], session["players"][1], source=session["source"])
    if new_session is not None:
        runtime["dooz_sessions"].pop(session_id, None)


@bot.on_callback_query(regex(r"^chat_dooz:") & private)
async def cb_chat_dooz(client, callback_query):
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
        target_peer = runtime["pending_chat_dooz_invites"].pop(inviter_id, None)
        await callback_query.answer("دعوت لغو شد ✅")
        await client.edit_message_text(callback_query.message.chat.id, callback_query.message.id, "❎ دعوت دوز لغو شد.")
        if target_peer:
            await client.send_message(int(target_peer), "❎ مخاطبت دعوت دوز رو لغو کرد.", reply_markup=kb.kb_chat_menu())
        return

    if runtime["pending_chat_dooz_invites"].get(inviter_id) != receiver_id:
        await callback_query.answer("این درخواست منقضی شده.", show_alert=True)
        return

    if action == "reject":
        runtime["pending_chat_dooz_invites"].pop(inviter_id, None)
        await callback_query.answer("دعوت رد شد")
        await client.send_message(int(inviter_id), "❌ مخاطبت دعوت دوز رو رد کرد.", reply_markup=kb.kb_chat_menu())
        await client.edit_message_text(callback_query.message.chat.id, callback_query.message.id, "❌ دعوت دوز رد شد.")
        return

    if session_of(inviter_id) or session_of(receiver_id):
        await callback_query.answer("یکی از بازیکن‌ها داخل بازی است.", show_alert=True)
        return

    runtime["pending_chat_dooz_invites"].pop(inviter_id, None)
    session = await _start_game(client, inviter_id, receiver_id, source="chat")
    if session is None:
        await callback_query.answer("شروع بازی ناموفق بود.", show_alert=True)
        return
    await callback_query.answer("دوز شروع شد ✅")
    await client.edit_message_text(callback_query.message.chat.id, callback_query.message.id, "✅ دوز شروع شد؛ صفحه بازی برای هر دو نفر ارسال شد.")


