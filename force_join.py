"""بررسی و مدیریت «جوین اجباری» کانال‌ها — نسخه‌ی جدید با chat_id عددی."""
from balethon.enums import ChatMemberStatus
from balethon.errors import RPCError

import config
import database as db
import keyboards as kb


def is_admin_id(uid) -> bool:
    return str(uid) == str(config.ADMIN_ID)


async def fetch_channel_info(client, chat_id: str) -> dict:
    """گرفتن اطلاعات کانال با chat_id عددی. برگشت: {title, is_admin, can_invite, invite_link}"""
    result = {"title": None, "is_admin": False, "can_invite": False, "invite_link": None}
    try:
        chat = await client.get_chat(chat_id)
        result["title"] = chat.title or chat.first_name
    except (RPCError, Exception):
        return result

    if not client.user:
        return result

    try:
        member = await client.get_chat_member(chat_id, client.user.id)
    except (RPCError, Exception):
        return result

    result["is_admin"] = member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)

    # اگر ادمین هستیم، باید چک کنیم invite_users داریم یا نه
    if result["is_admin"] and hasattr(member, "can_invite_users"):
        result["can_invite"] = bool(member.can_invite_users)

    # گرفتن invite_link از کانال (فقط اگر bot can_invite)
    if result["can_invite"]:
        try:
            if hasattr(chat, "username") and chat.username:
                result["invite_link"] = "https://ble.ir/" + chat.username
            elif hasattr(chat, "export_invite_link"):
                link = await client.export_invite_link(chat_id)
                result["invite_link"] = link
        except (RPCError, Exception):
            pass

    return result


async def user_membership_check(client, user_id, chat_id: str) -> bool:
    """چک کردن عضویت کاربر در کانال."""
    try:
        member = await client.get_chat_member(chat_id, user_id)
    except (RPCError, Exception):
        return False
    return member.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)


async def user_membership_check_in_channel(client, user_id, channel_slug: str) -> bool:
    """سازگاری با تست/کد قدیمی که slug کانال را بدون @ می‌فرستاد."""
    channel_slug = (channel_slug or "").strip()
    if channel_slug and not channel_slug.startswith(("@", "-")):
        channel_slug = "@" + channel_slug
    return await user_membership_check(client, user_id, channel_slug)


async def force_join_gate_needed_for_user(client, uid) -> bool:
    if is_admin_id(uid):
        return False
    channels = await db.get_force_join_channels()
    if not channels:
        return False
    try:
        int(uid)
    except (TypeError, ValueError):
        return False
    for ch in channels:
        if not ch.get("bot_is_admin"):
            continue
        chat_id = ch["chat_id"]
        if not await user_membership_check(client, uid, chat_id):
            return True
    return False


def build_force_join_keyboard(channels, user_id=None, client=None):
    """ساخت کیبورد جوین اجباری — فقط کانال‌هایی که کاربر عضو نیست."""
    rows = []
    for ch in channels:
        title = (ch.get("title") or "کانال").strip()
        invite_link = ch.get("invite_link")
        if invite_link:
            rows.append([kb.url_btn(f"📌 عضویت در {title}", invite_link)])
    rows.append([("✅ بررسی عضویت", "forcejoin_check")])
    return kb.ikb(*rows)


async def send_force_join_gate(client, chat_id, reply_to_message_id=None):
    channels = await db.get_force_join_channels()
    active = [ch for ch in channels if ch.get("bot_is_admin")]
    text = (
        "⛔ برای استفاده از ربات باید عضو کانال‌های زیر باشید.\n\n"
        "بعد از عضویت، روی «✅ بررسی عضویت» بزنید."
    )
    try:
        await client.send_message(
            chat_id, text, reply_markup=build_force_join_keyboard(active), reply_to_message_id=reply_to_message_id
        )
    except Exception as e:
        print(f"Error sending force-join gate: {e}")


def get_force_join_text(channels):
    lines = ["📌 *جوین اجباری*", "", "کانال‌های فعال:"]
    if not channels:
        lines.append("— (هیچ کانالی ثبت نشده)")
    else:
        for ch in channels:
            status = "✅" if ch.get("bot_is_admin") else "⚠️"
            invite_status = "🔗 لینک دعوت دارد" if ch.get("invite_link") else "❌ بدون لینک دعوت"
            lines.append(f"{status} {ch.get('title', '—')} (`{ch['chat_id']}`)")
            lines.append(f"   ادمین ربات: {'بله' if ch.get('bot_is_admin') else 'خیر'} | {invite_status}")
    lines += [
        "",
        "برای افزودن کانال: داخل پنل روی «جوین اجباری» بزن و آیدی عددی کانال را بفرست.",
    ]
    return "\n".join(lines)


def build_admin_channel_list_keyboard(channels):
    """ساخت کیبورد لیست کانال‌ها با دکمه حذف جداگانه."""
    rows = []
    for ch in channels:
        title = (ch.get("title") or "کانال").strip()
        ch_id = ch["id"]
        rows.append([
            kb.ikb_row_btn(f"🗑 حذف {title}", f"fj_delete:{ch_id}")
        ])
    return kb.ikb(*rows) if rows else None
