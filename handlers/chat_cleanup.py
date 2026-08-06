"""Runtime cleanup hooks for active-chat game sessions.

This module is imported after the chat/game handlers are registered. It patches
chat.py helpers so every chat-ending path also clears in-chat game state.
"""
import database as db
import keyboards as kb
from bot_instance import runtime
from profile_common import is_blocked_between
from . import chat as chat_handler

CHAT_GAME_CANCELLED_TEXT = (
    "⛔ چت ناشناس بسته شد\n\n"
    "بازی داخل چت هم خودکار لغو شد و دکمه‌های قبلی دیگر فعال نیستند."
)


def _clear_pending_chat_invites(uid, other_uid=None):
    ids = {str(uid)}
    if other_uid:
        ids.add(str(other_uid))
    for user_id in ids:
        runtime["pending_chat_dooz_invites"].pop(user_id, None)
        runtime["pending_chat_rps_invites"].pop(user_id, None)


async def _edit_old_game_messages(client, message_ids):
    if not client:
        return
    for player_id, message_id in dict(message_ids or {}).items():
        if not message_id:
            continue
        try:
            await client.edit_message_text(int(player_id), int(message_id), CHAT_GAME_CANCELLED_TEXT)
        except Exception:
            pass


async def clear_active_chat_games(client, uid):
    uid = str(uid)
    try:
        from handlers import dooz
        session = dooz.session_of(uid)
        if session and session.get("source") == "chat":
            session["status"] = "cancelled"
            await _edit_old_game_messages(client, session.get("board_message_ids"))
            dooz._clear_binding(session)
            runtime["dooz_sessions"].pop(session["id"], None)
    except Exception:
        pass

    try:
        from handlers import rps
        session = rps.rps_session_of(uid)
        if session and session.get("source") == "chat":
            session["status"] = "cancelled"
            await _edit_old_game_messages(client, session.get("message_ids"))
            rps.clear_rps_active_binding(session)
            runtime["rps_sessions"].pop(session["id"], None)
    except Exception:
        pass


async def end_chat_for(uid, client=None):
    uid = str(uid)
    user = await db.get_user(uid, create_if_missing=False)
    if not user:
        return None
    other_uid = user.get("chat_with")
    _clear_pending_chat_invites(uid, other_uid)
    await clear_active_chat_games(client, uid)
    user["chat_with"] = None
    user["chat_started_at"] = None
    await db.save_user(uid, user)
    return other_uid


_original_relay_message_to_partner = chat_handler.relay_message_to_partner


async def relay_message_to_partner(client, from_uid_str, message):
    from_user = await db.get_user(from_uid_str, create_if_missing=False)
    if not from_user:
        return
    other_uid = from_user.get("chat_with")
    if not other_uid:
        return
    other_user = await db.get_user(other_uid, create_if_missing=False)
    if not other_user:
        return

    if is_blocked_between(from_user, other_user):
        await end_chat_for(from_uid_str, client=client)
        await end_chat_for(other_uid, client=client)
        try:
            await client.send_message(
                int(from_uid_str),
                "⛔ چت به خاطر بلاک بسته شد.\n\nبازی‌های داخل چت هم لغو شدند و شما به منوی اصلی برگشتید.",
                reply_markup=kb.kb_main_menu(),
            )
        except Exception:
            pass
        try:
            await client.send_message(
                int(other_uid),
                "⛔ چت به خاطر بلاک بسته شد.\n\nبازی‌های داخل چت هم لغو شدند و شما به منوی اصلی برگشتید.",
                reply_markup=kb.kb_main_menu(),
            )
        except Exception:
            pass
        return

    await _original_relay_message_to_partner(client, from_uid_str, message)


chat_handler.CHAT_GAME_CANCELLED_TEXT = CHAT_GAME_CANCELLED_TEXT
chat_handler._clear_active_chat_games = clear_active_chat_games
chat_handler.end_chat_for = end_chat_for
chat_handler.relay_message_to_partner = relay_message_to_partner
