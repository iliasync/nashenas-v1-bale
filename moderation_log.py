"""ارسال لاگ رسانه و گزارش به گروه مدیریت."""
import config
import keyboards as kb
from utils import normalize_gender_text, safe_int


def _reason_title(code):
    return next((title for title, value in config.REPORT_REASONS if value == code), code or "نامشخص")


def _user_lines(title, uid, user):
    user = user or {}
    return [
        f"{title}",
        f"• آیدی عددی: `{uid}`",
        f"• شناسه عمومی: /user_{user.get('public_id') or '—'}",
        f"• نام: {user.get('display_name') or 'ثبت نشده'}",
        f"• جنسیت: {normalize_gender_text(user)}",
        f"• سن: {safe_int(user.get('age'), 0) or 'ثبت نشده'}",
        f"• شهر: {user.get('city') or 'ثبت نشده'}",
        f"• وضعیت بن: {'بله ⛔' if user.get('bot_banned') else 'خیر ✅'}",
    ]


def _media_type(message):
    names = (
        ("photo", "عکس"), ("video", "ویدئو"), ("animation", "گیف"),
        ("voice", "پیام صوتی"), ("audio", "فایل صوتی"),
        ("document", "فایل"), ("sticker", "استیکر"), ("contact", "مخاطب"),
    )
    return next((label for attr, label in names if getattr(message, attr, None)), "رسانه")


def is_loggable_media(message):
    return any(getattr(message, attr, None) for attr in (
        "photo", "video", "animation", "voice", "audio", "document", "sticker", "contact"
    ))


async def log_media(client, message, sender_uid, sender, receiver_uid, receiver):
    """ابتدا خود رسانه و سپس کارت اطلاعات و دکمه‌های مدیریت را می‌فرستد."""
    try:
        copied = await client.copy_message(int(config.LOG_CHAT_ID), message.chat.id, message.id)
        lines = [f"🖼 *لاگ رسانه جدید — {_media_type(message)}*", ""]
        lines += _user_lines("👤 *ارسال‌کننده*", sender_uid, sender)
        lines += [""] + _user_lines("🎯 *دریافت‌کننده*", receiver_uid, receiver)
        lines += ["", f"📝 کپشن: {(message.caption or 'بدون کپشن')}"]
        await client.send_message(
            int(config.LOG_CHAT_ID), "\n".join(lines),
            reply_markup=kb.ikb_log_moderation(
                sender_uid, receiver_uid, "⛔ بن ارسال‌کننده", "⛔ بن دریافت‌کننده"
            ),
            reply_to_message_id=getattr(copied, "id", None),
        )
        return True
    except Exception as exc:
        print(f"media moderation log failed: {exc}")
        return False


async def log_report(client, reporter_uid, reporter, target_uid, target, reason_code, screenshot_message):
    if not getattr(screenshot_message, "photo", None):
        raise ValueError("A screenshot photo is required for reports")
    copied = await client.copy_message(
        int(config.LOG_CHAT_ID), screenshot_message.chat.id, screenshot_message.id
    )
    lines = ["🚫 *گزارش جدید*", ""]
    lines += _user_lines("👤 *گزارش‌دهنده*", reporter_uid, reporter)
    lines += [""] + _user_lines("🎯 *کاربر گزارش‌شده*", target_uid, target)
    lines += [
        "", f"🧾 دلیل گزارش: *{_reason_title(reason_code)}*", f"🔖 کد دلیل: `{reason_code}`",
        f"📝 توضیح همراه اسکرین‌شات: {screenshot_message.caption or 'بدون توضیح'}",
    ]
    report_message = await client.send_message(
        int(config.LOG_CHAT_ID), "\n".join(lines),
        reply_markup=kb.ikb_log_moderation(
            target_uid, reporter_uid, "⛔ بن کاربر گزارش‌شده", "⛔ بن گزارش‌دهنده"
        ),
        reply_to_message_id=getattr(copied, "id", None),
    )
    try:
        # کارت اطلاعات پین می‌شود تا علت، آیدی‌ها و دکمه‌های مدیریت یکجا در دسترس باشند.
        await client.pin_chat_message(int(config.LOG_CHAT_ID), report_message.id)
    except Exception as exc:
        # نداشتن دسترسی Pin نباید اصل ثبت و ارسال گزارش را ناموفق کند.
        print(f"pin report failed: {exc}")
    return True
