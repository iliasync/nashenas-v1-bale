"""
کاندیشن‌های (فیلترهای) سفارشی بله‌تون.

این فیلترها روی دیتابیس کار می‌کنند (چون state و profile_completed و ... در
SQLite ذخیره شده‌اند، نه در یک دیکشنری ساده‌ی in-memory).
برای جلوگیری از کوئری تکراری روی هر آپدیت، نتیجه‌ی fetch روی خودِ آبجکت
event کش می‌شود (طول عمرش فقط برای همان یک آپدیت است).
"""
from balethon.conditions import create, author
from balethon.objects import Message, CallbackQuery

import config
import database as db

ADMIN_ID_INT = int(config.ADMIN_ID) if str(config.ADMIN_ID).isdigit() else None


async def get_event_user(event, create_if_missing: bool = True):
    """دیکشنریِ کاربر را برای این event برمی‌گرداند (با کش روی خودِ event)."""
    if not getattr(event, "author", None):
        return None
    cached = getattr(event, "_cached_user", None)
    if cached is not None:
        return cached
    user = await db.get_user(event.author.id, create_if_missing=create_if_missing)
    try:
        event._cached_user = user
    except Exception:
        pass
    return user


def set_event_user(event, user: dict):
    try:
        event._cached_user = user
    except Exception:
        pass


def is_admin_id(uid) -> bool:
    return str(uid) == str(config.ADMIN_ID)


# دکمه‌ی همیشه true برای فیلتر مدیر (آیدی عددی ادمین)
admin_only = author(ADMIN_ID_INT) if ADMIN_ID_INT is not None else create()(lambda: False)


def state_is(*states):
    """شرط: کاربرِ فرستنده‌ی event دقیقاً در یکی از این state هاست."""
    @create(can_process=(Message, CallbackQuery))
    async def _cond(event):
        user = await get_event_user(event, create_if_missing=False)
        return user is not None and user.get("state") in states
    return _cond


def admin_state_is(*states):
    @create(can_process=(Message, CallbackQuery))
    async def _cond(event):
        user = await get_event_user(event, create_if_missing=False)
        return user is not None and user.get("admin_state") in states
    return _cond


@create(can_process=(Message, CallbackQuery))
async def profile_completed(event) -> bool:
    user = await get_event_user(event, create_if_missing=False)
    return bool(user and user.get("profile_completed"))


@create(can_process=(Message, CallbackQuery))
async def profile_not_completed(event) -> bool:
    user = await get_event_user(event, create_if_missing=False)
    return bool(user and not user.get("profile_completed"))


@create(can_process=(Message, CallbackQuery))
async def in_active_chat(event) -> bool:
    user = await get_event_user(event, create_if_missing=False)
    return bool(user and user.get("chat_with"))


@create(can_process=(Message, CallbackQuery))
async def not_in_active_chat(event) -> bool:
    user = await get_event_user(event, create_if_missing=False)
    return not bool(user and user.get("chat_with"))


@create(can_process=Message)
async def is_admin_author(event) -> bool:
    if not event.author:
        return False
    return is_admin_id(event.author.id)
