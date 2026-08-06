"""توابع مشترک نمایش/ساخت پروفایل (هم برای پروفایل خودم، هم پروفایل دیگران)."""
import os

import config
import database as db
import keyboards as kb
from utils import normalize_gender_text, last_seen_text, distance_text, get_profile_missing_fields, safe_int

DEFAULT_AVATAR_PATH = os.path.join(os.path.dirname(__file__), "Aksss.jpg")


def is_blocked_between(viewer_user: dict, target_user: dict) -> bool:
    target_pid = (target_user.get("public_id") or "").strip()
    viewer_pid = (viewer_user.get("public_id") or "").strip()
    if target_pid and target_pid in (viewer_user.get("blocked_users") or []):
        return True
    if viewer_pid and viewer_pid in (target_user.get("blocked_users") or []):
        return True
    return False


async def _send_profile_card(client, chat_id, file_id, caption, reply_markup, reply_to_message_id=None):
    if file_id:
        try:
            return await client.send_photo(
                chat_id, file_id, caption=caption, reply_markup=reply_markup, reply_to_message_id=reply_to_message_id
            )
        except Exception as e:
            print(f"send_photo (file_id) failed: {e}")
    if os.path.isfile(DEFAULT_AVATAR_PATH):
        try:
            return await client.send_photo(
                chat_id, DEFAULT_AVATAR_PATH, caption=caption, reply_markup=reply_markup,
                reply_to_message_id=reply_to_message_id,
            )
        except Exception as e:
            print(f"send_photo (default avatar) failed: {e}")
    try:
        return await client.send_message(
            chat_id, caption, reply_markup=reply_markup, reply_to_message_id=reply_to_message_id
        )
    except Exception as e:
        print(f"send_message (profile fallback) failed: {e}")
        return None


async def build_my_profile_text(user: dict) -> str:
    name = (user.get("display_name") or "").strip() or "تعیین نشده"
    city = (user.get("city") or "").strip() or "تعیین نشده"

    pid = await db.ensure_unique_public_id(user.get("user_id"))
    return (
        f"• نام: {name}\n"
        f"• جنسیت: {normalize_gender_text(user)}\n"
        f"• استان: {(user.get('province') or 'تعیین نشده')}\n"
        f"• شهر: {city}\n"
        f"• سن: {(user.get('age') or 'تعیین نشده')}\n\n"
        f"♥️ لایک ها : {safe_int(user.get('likes', 0), 0)}\n\n"
        f"هم اکنون 👀 {last_seen_text(user)}\n\n"
        f"🆔 آیدی : /user_{pid}"
    )


def build_user_profile_text(viewer_user: dict, target_user: dict) -> str:
    name = (target_user.get("display_name") or "").strip() or "تعیین نشده"
    city = (target_user.get("city") or "").strip() or "تعیین نشده"
    pid = target_user.get("public_id") or "unknown"
    return (
        f"• نام: {name}\n"
        f"• جنسیت: {normalize_gender_text(target_user)}\n"
        f"• استان: {(target_user.get('province') or 'تعیین نشده')}\n"
        f"• شهر: {city}\n"
        f"• سن: {(target_user.get('age') or 'تعیین نشده')}\n\n"
        f"هم اکنون {last_seen_text(target_user)}\n\n"
        f"🆔 آیدی : /user_{pid}\n\n"
        f"🏁 فاصله از شما: {distance_text(viewer_user, target_user)}"
    )


async def maybe_reward_profile_completion(client, chat_id, user: dict):
    missing = get_profile_missing_fields(user)
    if not missing and not user.get("profile_completion_rewarded", False):
        user["profile_completion_rewarded"] = True
        user["coins"] = safe_int(user.get("coins", 0), 0) + config.PROFILE_COMPLETE_REWARD
        await db.save_user(chat_id, user)
        await client.send_message(
            chat_id,
            f"🎉 تبریک! پروفایل شما کامل شد و *{config.PROFILE_COMPLETE_REWARD}* سکه 💰 هدیه گرفتید.\n"
            f"💰 موجودی جدید: *{user['coins']}*",
        )


async def send_profile_completion_hint(client, chat_id, reply_to_message_id, user: dict):
    missing = get_profile_missing_fields(user)
    if not missing:
        return
    text = (
        f"🔔 فقط *{len(missing)}* قدم تا تکمیل پروفایل !\n\n"
        f"اطلاعات تکمیل نشده:  " + " , ".join(missing) + "\n\n"
        "پروفایل خود را تکمیل کنید👇 و 5 سکه 💰 دریافت کنید."
    )
    try:
        await client.send_message(chat_id, text, reply_to_message_id=reply_to_message_id)
    except Exception as e:
        print(f"send_profile_completion_hint failed: {e}")


async def show_my_profile(client, chat_id, user: dict, reply_to_message_id=None):
    caption = await build_my_profile_text(user)
    file_id = (user.get("profile_photo_file_id") or "").strip() or None
    msg = await _send_profile_card(
        client, chat_id, file_id, caption, kb.ikb_my_profile_buttons(), reply_to_message_id
    )
    if msg is not None:
        await send_profile_completion_hint(client, chat_id, msg.id, user)


async def show_user_profile_by_pid(client, viewer_chat_id, viewer_user: dict, pid: str, reply_to_message_id=None):
    target_uid, target_user = await db.get_user_by_public_id(pid)
    print(target_uid, target_user)
    if not target_user:
        await client.send_message(viewer_chat_id, "⚠️ کاربر پیدا نشد.", reply_to_message_id=reply_to_message_id)
        return

    if str(target_uid) == str(viewer_chat_id):
        await show_my_profile(client, viewer_chat_id, viewer_user, reply_to_message_id=reply_to_message_id)
        return

    caption = build_user_profile_text(viewer_user, target_user)
    blocked = is_blocked_between(viewer_user, target_user)
    actions = kb.ikb_user_profile_actions(viewer_user, target_user, blocked)
    file_id = (target_user.get("profile_photo_file_id") or "").strip() or None
    await _send_profile_card(client, viewer_chat_id, file_id, caption, actions, reply_to_message_id)
