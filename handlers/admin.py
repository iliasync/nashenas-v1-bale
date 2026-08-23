"""پنل مدیریت ربات (فقط برای ADMIN_ID)."""
import asyncio
import re

from balethon.conditions import equals, regex, private

import config
import database as db
import force_join as fj
import keyboards as kb
from bot_instance import bot
from filters import get_event_user, admin_only, admin_state_is, is_admin_id
from utils import safe_int, normalize_gender_text, last_seen_text

_broadcast_task = None
_broadcast_lock = asyncio.Lock()


@bot.on_callback_query(regex(r"^log_ban:"))
async def cb_log_ban_user(client, callback_query):
    """بن فوری از دکمه‌ی گروه لاگ؛ فقط ادمین اصلی اجازه دارد."""
    if not is_admin_id(callback_query.author.id):
        await callback_query.answer("فقط ادمین اصلی اجازه انجام این کار را دارد.", show_alert=True)
        return
    target_uid = str(safe_int((callback_query.data or "").split(":", 1)[1], 0))
    if target_uid == "0":
        await callback_query.answer("آیدی کاربر نامعتبر است.", show_alert=True)
        return
    target = await db.get_user(target_uid, create_if_missing=False)
    if not target:
        await callback_query.answer("کاربر در دیتابیس پیدا نشد.", show_alert=True)
        return
    if target.get("bot_banned"):
        await callback_query.answer("این کاربر قبلاً بن شده است.", show_alert=True)
        return
    target["bot_banned"] = True
    await db.save_user(target_uid, target)
    await callback_query.answer("کاربر از ربات بن شد ✅", show_alert=True)
    await client.send_message(
        callback_query.message.chat.id,
        f"✅ کاربر `{target_uid}` توسط ادمین `{callback_query.author.id}` از ربات بن شد.",
        reply_to_message_id=callback_query.message.id,
    )
    try:
        await client.send_message(int(target_uid), "⛔ دسترسی شما به ربات مسدود شد.")
    except Exception:
        pass


async def _send_bulk_message(client, uid, text, retries=2):
    for attempt in range(retries + 1):
        try:
            await asyncio.wait_for(client.send_message(int(uid), text), timeout=20)
            return True
        except Exception:
            if attempt >= retries:
                return False
            await asyncio.sleep(0.4 * (attempt + 1))
    return False


async def _broadcast_worker(client):
    """ارسال قابل‌بازیابی؛ هر گیرنده قبل از ارسال در SQLite checkpoint می‌شود."""
    global _broadcast_task
    async with _broadcast_lock:
        while True:
            job = await db.get_broadcast_job()
            if not job or job.get("status") in ("paused", "completed"): return
            recipients = job.get("recipients") or []
            i = safe_int(job.get("next_index"), 0)
            if i >= len(recipients):
                await db.update_broadcast_job(status="completed")
                return
            uid = recipients[i]
            payload = job.get("payload") or {}
            if job.get("kind") == "coin":
                tu = await db.get_user(uid, create_if_missing=False)
                amount = safe_int(payload.get("amount"), 0)
                text = f"🎁 *سکه همگانی!*\n\n✅ به شما *{amount}* 🪙 سکه هدیه داده شد.\n💰 موجودی جدید شما: *{safe_int((tu or {}).get('coins'), 0)}* 🪙"
            else:
                text = payload.get("text", "")
            ok = await _send_bulk_message(client, uid, text, retries=3)
            await db.update_broadcast_job(next_index=i + 1, sent=job.get("sent", 0) + int(ok), failed=job.get("failed", 0) + int(not ok))
            await asyncio.sleep(config.BROADCAST_DELAY_SECONDS if ok else config.BROADCAST_RETRY_DELAY_SECONDS)


def start_broadcast_worker(client):
    global _broadcast_task
    if _broadcast_task is None or _broadcast_task.done():
        _broadcast_task = asyncio.create_task(_broadcast_worker(client))
    return _broadcast_task


async def stop_broadcast_worker():
    global _broadcast_task
    if _broadcast_task and not _broadcast_task.done():
        _broadcast_task.cancel()
        try:
            await _broadcast_task
        except asyncio.CancelledError:
            pass
    _broadcast_task = None


async def resume_pending_broadcasts(client):
    job = await db.get_broadcast_job()
    if job and job.get("status") == "running": start_broadcast_worker(client)


@bot.on_command(name="panel", min_arguments=0, max_arguments=0,condition=private)
async def cmd_panel(client, message):
    if not is_admin_id(message.author.id):
        return
    user = await get_event_user(message)
    user["admin_state"] = None
    await db.save_user(message.chat.id, user)
    await client.send_message(
        message.chat.id,
        "🛠 *پنل مدیریت*\nیکی از گزینه‌ها را انتخاب کنید 👇\n\n"
        f"🧩 نسخه: `{config.BUILD_MARKER}`\n"
        f"🆔 آیدی ادمین تشخیص‌داده‌شده: `{message.author.id}`",
        reply_markup=kb.kb_admin_panel(), reply_to_message_id=message.id,
    )


@bot.on_command(name="testlog", min_arguments=0, max_arguments=0, condition=private)
async def cmd_test_log_group(client, message):
    """تست مستقیم مقصد لاگ و نمایش خطای واقعی فقط به ادمین."""
    if not is_admin_id(message.author.id):
        return
    target = str(config.LOG_CHAT_ID or "").strip()
    if not target:
        await client.send_message(message.chat.id, "❌ `LOG_CHAT_ID` تنظیم نشده است.", reply_to_message_id=message.id)
        return
    try:
        sent = await asyncio.wait_for(
            client.send_message(int(target), "✅ تست گروه لاگ بات با موفقیت انجام شد."), timeout=20
        )
        destination = "پیوی ادمین" if target == str(config.ADMIN_ID) else "گروه لاگ"
        await client.send_message(
            message.chat.id,
            f"✅ ارسال تست موفق بود.\nمقصد فعلی: *{destination}* (`{target}`)\nmessage_id: `{getattr(sent, 'id', '—')}`",
            reply_to_message_id=message.id,
        )
    except Exception as exc:
        await client.send_message(
            message.chat.id,
            f"❌ ارسال به مقصد لاگ ناموفق بود.\nمقصد: `{target}`\nخطا: `{type(exc).__name__}: {str(exc)[:300]}`\n\n"
            "ربات باید داخل گروه باشد و اجازه ارسال پیام داشته باشد.",
            reply_to_message_id=message.id,
        )


@bot.on_message(equals("🔙 خروج از پنل") & admin_only & private)
async def msg_admin_exit(client, message):
    user = await get_event_user(message)
    user["admin_state"] = None
    await db.save_user(message.chat.id, user)
    await client.send_message(message.chat.id, "✅ از پنل خارج شدی.", reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id)


@bot.on_message(equals("📣 ارسال همگانی") & admin_only & private)
async def msg_admin_broadcast_btn(client, message):
    user = await get_event_user(message)
    user["admin_state"] = "panel_broadcast_waiting_text"
    await db.save_user(message.chat.id, user)
    await client.send_message(message.chat.id, "✉️ متن همگانی را ارسال کنید:", reply_to_message_id=message.id)


@bot.on_message(equals("📊 وضعیت همگانی") & admin_only & private)
async def msg_broadcast_status(client, message):
    job = await db.get_broadcast_job()
    if not job:
        text = "ℹ️ همگانی فعالی وجود ندارد."
    else:
        total = len(job.get("recipients") or [])
        text = (f"📊 وضعیت همگانی: *{job.get('status')}*\n"
                f"پیشرفت: {job.get('next_index', 0)}/{total}\n"
                f"✅ موفق: {job.get('sent', 0)} | ❌ ناموفق: {job.get('failed', 0)}")
    await client.send_message(message.chat.id, text, reply_markup=kb.kb_admin_panel(), reply_to_message_id=message.id)


@bot.on_message(equals("⏸ توقف همگانی") & admin_only & private)
async def msg_broadcast_pause(client, message):
    job = await db.get_broadcast_job()
    if not job or job.get("status") != "running":
        await client.send_message(message.chat.id, "ℹ️ همگانی در حال اجرا نیست.", reply_to_message_id=message.id); return
    await db.update_broadcast_job(status="paused")
    await client.send_message(message.chat.id, "⏸ همگانی متوقف شد؛ از همان نقطه قابل ادامه است.", reply_markup=kb.kb_admin_panel(), reply_to_message_id=message.id)


@bot.on_message(equals("▶️ ادامه همگانی") & admin_only & private)
async def msg_broadcast_resume(client, message):
    job = await db.get_broadcast_job()
    if not job:
        await client.send_message(message.chat.id, "ℹ️ همگانی ذخیره‌شده‌ای وجود ندارد.", reply_to_message_id=message.id); return
    await db.update_broadcast_job(status="running")
    start_broadcast_worker(client)
    await client.send_message(message.chat.id, "▶️ ادامه‌ی همگانی شروع شد.", reply_markup=kb.kb_admin_panel(), reply_to_message_id=message.id)


@bot.on_message(equals("🪙 انتقال سکه") & admin_only & private)
async def msg_admin_transfer_btn(client, message):
    user = await get_event_user(message)
    user["admin_state"] = "panel_transfer_waiting_user_id"
    await db.save_user(message.chat.id, user)
    await client.send_message(message.chat.id, "👤 آیدی عددی کاربر را بفرست:", reply_to_message_id=message.id)


@bot.on_message(equals("🎁 سکه همگانی") & admin_only & private)
async def msg_admin_global_coin_btn(client, message):
    user = await get_event_user(message)
    user["admin_state"] = "panel_global_coin_waiting_amount"
    await db.save_user(message.chat.id, user)
    await client.send_message(message.chat.id, "🪙 تعداد سکه همگانی را بفرست:", reply_to_message_id=message.id)


@bot.on_message(equals("⚙️ تنظیم سکه روزانه") & admin_only & private)
async def msg_admin_daily_coin_btn(client, message):
    user = await get_event_user(message)
    minimum, maximum = await db.get_daily_coin_settings()
    stats = await db.get_daily_coin_stats()
    user["admin_state"] = "panel_daily_coin_waiting_range"
    await db.save_user(message.chat.id, user)
    await client.send_message(
        message.chat.id,
        "🎁 *تنظیم سکه روزانه*\n\n"
        f"بازه فعلی: از *{minimum}* تا *{maximum}* سکه\n"
        f"دریافت امروز: *{stats['claim_count']}* نفر | مجموع *{stats['reward_sum']}* سکه\n\n"
        "کمینه و بیشینه را در یک پیام بفرست؛ مثال: `5 25`",
        reply_to_message_id=message.id,
    )


@bot.on_message(equals("📌 جوین اجباری") & admin_only & private)
async def msg_admin_force_join_btn(client, message):
    user = await get_event_user(message)
    user["admin_state"] = "panel_force_join_waiting_channel"
    await db.save_user(message.chat.id, user)
    channels = await db.get_force_join_channels()
    await client.send_message(
        message.chat.id,
        "📌 آیدی عددی کانال را بفرست (مثلاً `-1001234567890`).\n\n" + fj.get_force_join_text(channels),
        reply_to_message_id=message.id,
    )
    # اگر کانالی هست، دکمه‌های حذف جداگانه هم نشون بده
    if channels:
        del_kb = fj.build_admin_channel_list_keyboard(channels)
        if del_kb:
            await client.send_message(
                message.chat.id, "🗑 برای حذف هر کانال روی دکمه زیر بزنید:",
                reply_markup=del_kb, reply_to_message_id=message.id,
            )


@bot.on_message(equals("📊 آمار ربات") & admin_only & private)
async def msg_admin_stats_btn(client, message):
    await client.send_message(message.chat.id, await db.render_stats_text(), reply_to_message_id=message.id)


@bot.on_message(equals("⛔ بلاک کاربر") & admin_only & private)
async def msg_admin_block_btn(client, message):
    user = await get_event_user(message)
    user["admin_state"] = "panel_block_waiting_user_id"
    await db.save_user(message.chat.id, user)
    await client.send_message(message.chat.id, "⛔ آیدی عددی کاربر را بفرست:", reply_to_message_id=message.id)


@bot.on_message(equals("✅ آنبلاک کاربر") & admin_only & private)
async def msg_admin_unblock_btn(client, message):
    user = await get_event_user(message)
    user["admin_state"] = "panel_unblock_waiting_user_id"
    await db.save_user(message.chat.id, user)
    await client.send_message(message.chat.id, "✅ آیدی عددی کاربر را بفرست:", reply_to_message_id=message.id)


@bot.on_message(equals("👤 اطلاعات کاربر") & admin_only & private)
async def msg_admin_userinfo_btn(client, message):
    user = await get_event_user(message)
    user["admin_state"] = "panel_userinfo_waiting_user_id"
    await db.save_user(message.chat.id, user)
    await client.send_message(message.chat.id, "👤 آیدی عددی کاربر را بفرست:", reply_to_message_id=message.id)


@bot.on_message(equals("🧾 پرداخت‌ها (لیست)") & admin_only & private)
async def msg_admin_payments_btn(client, message):
    pays = await db.list_recent_payments(15)
    lines = ["🧾 *لیست پرداخت‌ها (۱۵ مورد آخر)*", ""]
    if not pays:
        lines.append("— خالی")
    else:
        for p in pays:
            lines.append(
                f"• tx: `{p.get('tx_id')}` | `{p.get('buyer_uid')}` | 🪙{p.get('coins')} | "
                f"💵{safe_int(p.get('price'), 0):,} | وضعیت: *{p.get('status')}*"
            )
    await client.send_message(message.chat.id, "\n".join(lines), reply_to_message_id=message.id)


# ---------------------------------------------------------------------------
# جریان‌های متنیِ پنل (admin_state)
# ---------------------------------------------------------------------------
@bot.on_message(admin_state_is("panel_daily_coin_waiting_range") & private)
async def msg_admin_daily_coin_range(client, message):
    user = await get_event_user(message)
    parts = [part for part in re.split(r"[\s,،\-]+", (message.text or "").strip()) if part]
    if len(parts) != 2:
        await client.send_message(message.chat.id, "⚠️ دقیقاً دو عدد بفرست؛ مثال: `5 25`", reply_to_message_id=message.id)
        return
    minimum, maximum = safe_int(parts[0], -1), safe_int(parts[1], -1)
    if minimum <= 0 or maximum < minimum:
        await client.send_message(
            message.chat.id,
            "⚠️ کمینه باید مثبت و بیشینه باید بزرگ‌تر یا مساوی کمینه باشد.",
            reply_to_message_id=message.id,
        )
        return
    if maximum > 1_000_000:
        await client.send_message(message.chat.id, "⚠️ بیشینه نمی‌تواند بیشتر از ۱٬۰۰۰٬۰۰۰ باشد.", reply_to_message_id=message.id)
        return
    await db.set_daily_coin_settings(minimum, maximum)
    user["admin_state"] = None
    await db.save_user(message.chat.id, user)
    await client.send_message(
        message.chat.id,
        f"✅ بازه سکه روزانه روی *{minimum}* تا *{maximum}* تنظیم شد.",
        reply_markup=kb.kb_admin_panel(), reply_to_message_id=message.id,
    )


@bot.on_message(admin_state_is("panel_broadcast_waiting_text") & private)
async def msg_admin_broadcast_text(client, message):
    user = await get_event_user(message)
    if not (message.text or "").strip():
        await client.send_message(message.chat.id, "⚠️ متن نامعتبره. دوباره بفرست.", reply_to_message_id=message.id)
        return
    recipients = [uid for uid, banned in await db.iter_all_user_ids() if not banned]
    await db.create_broadcast_job({"text": message.text}, recipients, message.chat.id)
    start_broadcast_worker(client)
    user["admin_state"] = None
    await db.save_user(message.chat.id, user)
    await client.send_message(
        message.chat.id, f"✅ همگانی شروع شد.\n\n👥 گیرنده: {len(recipients)}\n📊 از «وضعیت همگانی» پیگیری یا متوقفش کنید.",
        reply_markup=kb.kb_admin_panel(), reply_to_message_id=message.id,
    )


@bot.on_message(admin_state_is("panel_transfer_waiting_user_id") & private)
async def msg_admin_transfer_user_id(client, message):
    user = await get_event_user(message)
    target_id = str(safe_int((message.text or "").strip(), 0))
    if not target_id or target_id == "0":
        await client.send_message(message.chat.id, "⚠️ آیدی عددی معتبر بفرست.", reply_to_message_id=message.id)
        return
    await db.get_user(target_id)  # ensure exists
    user["panel_tmp_target"] = target_id
    user["admin_state"] = "panel_transfer_waiting_amount"
    await db.save_user(message.chat.id, user)
    await client.send_message(message.chat.id, "🪙 تعداد سکه را بفرست:", reply_to_message_id=message.id)


@bot.on_message(admin_state_is("panel_transfer_waiting_amount") & private)
async def msg_admin_transfer_amount(client, message):
    user = await get_event_user(message)
    amount = safe_int((message.text or "").strip(), -1)
    if amount <= 0:
        await client.send_message(message.chat.id, "⚠️ تعداد سکه باید عدد صحیح مثبت باشد.", reply_to_message_id=message.id)
        return
    target_id = str(user.get("panel_tmp_target") or "")
    if not target_id:
        user["admin_state"] = None
        await db.save_user(message.chat.id, user)
        await client.send_message(
            message.chat.id, "⚠️ خطا. دوباره از پنل شروع کن.", reply_markup=kb.kb_admin_panel(), reply_to_message_id=message.id
        )
        return
    tu = await db.get_user(target_id)
    tu["coins"] = safe_int(tu.get("coins", 0), 0) + amount
    await db.save_user(target_id, tu)
    user["admin_state"] = None
    user["panel_tmp_target"] = None
    await db.save_user(message.chat.id, user)
    await client.send_message(
        message.chat.id, f"✅ انتقال انجام شد.\n\n👤 کاربر: `{target_id}`\n🪙 مقدار: *{amount}*",
        reply_markup=kb.kb_admin_panel(), reply_to_message_id=message.id,
    )
    try:
        await client.send_message(
            int(target_id), f"🎉 *تبریک!*\n\n✅ *{amount}* 🪙 سکه به حساب شما اضافه شد.\n💰 موجودی جدید شما: *{tu['coins']}* 🪙"
        )
    except Exception:
        pass


@bot.on_message(admin_state_is("panel_global_coin_waiting_amount") & private)
async def msg_admin_global_coin_amount(client, message):
    user = await get_event_user(message)
    amount = safe_int((message.text or "").strip(), -1)
    if amount <= 0:
        await client.send_message(message.chat.id, "⚠️ تعداد سکه باید عدد صحیح مثبت باشد.", reply_to_message_id=message.id)
        return
    recipients = [uid for uid, banned in await db.iter_all_user_ids() if not banned]
    credited = await db.create_coin_broadcast_job(amount, recipients, message.chat.id)
    start_broadcast_worker(client)
    fresh_user = await db.get_user(message.chat.id)
    fresh_user["admin_state"] = None
    await db.save_user(message.chat.id, fresh_user)
    await client.send_message(
        message.chat.id,
        f"✅ سکه همگانی شروع شد.\n\n🪙 مقدار: {amount}\n👥 افزایش موجودی: {credited}\n📊 ارسال پیام از وضعیت همگانی قابل پیگیری است.",
        reply_markup=kb.kb_admin_panel(), reply_to_message_id=message.id,
    )


@bot.on_message(admin_state_is("panel_force_join_waiting_channel") & private)
async def msg_admin_force_join_channel(client, message):
    user = await get_event_user(message)
    raw = (message.text or "").strip()

    # بررسی آیدی عددی معتبر
    chat_id = str(safe_int(raw, 0))
    if not chat_id or chat_id == "0":
        await client.send_message(
            message.chat.id, "⚠️ آیدی عددی معتبر بفرست (مثلاً `-1001234567890`).", reply_to_message_id=message.id
        )
        return

    # چک تعداد حداکثر
    current = await db.get_force_join_channels()
    if len(current) >= 10:
        await client.send_message(message.chat.id, "⚠️ حداکثر ۱۰ کانال مجاز است. اول با `0` پاک کن.", reply_to_message_id=message.id)
        return

    # گرفتن اطلاعات کانال
    info = await fj.fetch_channel_info(client, chat_id)
    title = info["title"]
    is_admin = info["is_admin"]
    can_invite = info["can_invite"]
    invite_link = info["invite_link"]

    if not title:
        await client.send_message(
            message.chat.id,
            "⚠️ کانال یافت نشد! مطمئن شو:\n"
            "1. آیدی عددی صحیح است\n"
            "2. ربات در کانال عضو است\n"
            "3. کانال یا گروه عمومی است",
            reply_to_message_id=message.id,
        )
        return

    # بررسی تکراری
    existing_ids = [c.get("chat_id") for c in current]
    if chat_id in existing_ids:
        await client.send_message(
            message.chat.id, f"⚠️ کانال `{chat_id}` قبلاً اضافه شده.", reply_to_message_id=message.id
        )
        return

    # ذخیره
    await db.add_force_join_channel(chat_id, title, is_admin, can_invite, invite_link)

    user["admin_state"] = None
    await db.save_user(message.chat.id, user)

    channels = await db.get_force_join_channels()

    # ساخت پیام وضعیت
    status_lines = [f"✅ جوین اجباری اضافه شد:\n📌 {title} (`{chat_id}`)\n"]
    if is_admin:
        status_lines.append("✅ ربات در این کانال ادمین است.")
    else:
        status_lines.append("⚠️ ربات در این کانال ادمین نیست (چک عضویت دقیق انجام نمی‌شود).")
    if can_invite:
        status_lines.append(f"🔗 لینک دعوت: {invite_link or 'دریافت شد'}")
    else:
        status_lines.append("❌ ربات اجازه دعوت کاربران را ندارد.")
    status_lines.append("")
    status_lines.append(fj.get_force_join_text(channels))

    await client.send_message(
        message.chat.id, "\n".join(status_lines), reply_markup=kb.kb_admin_panel(), reply_to_message_id=message.id
    )

    # دکمه‌های حذف جداگانه
    del_kb = fj.build_admin_channel_list_keyboard(channels)
    if del_kb:
        await client.send_message(
            message.chat.id, "🗑 برای حذف هر کانال روی دکمه زیر بزنید:",
            reply_markup=del_kb, reply_to_message_id=message.id,
        )


@bot.on_message(admin_state_is("panel_block_waiting_user_id") & private)
async def msg_admin_block_user_id(client, message):
    user = await get_event_user(message)
    target_id = str(safe_int((message.text or "").strip(), 0))
    if not target_id or target_id == "0":
        await client.send_message(message.chat.id, "⚠️ آیدی عددی معتبر بفرست.", reply_to_message_id=message.id)
        return
    tu = await db.get_user(target_id)
    tu["bot_banned"] = True
    await db.save_user(target_id, tu)
    user["admin_state"] = None
    await db.save_user(message.chat.id, user)
    await client.send_message(
        message.chat.id, f"✅ کاربر `{target_id}` از بات بلاک شد.", reply_markup=kb.kb_admin_panel(), reply_to_message_id=message.id
    )
    try:
        await client.send_message(int(target_id), "⛔ دسترسی شما به ربات مسدود شد.")
    except Exception:
        pass


@bot.on_message(admin_state_is("panel_unblock_waiting_user_id") & private)
async def msg_admin_unblock_user_id(client, message):
    user = await get_event_user(message)
    target_id = str(safe_int((message.text or "").strip(), 0))
    if not target_id or target_id == "0":
        await client.send_message(message.chat.id, "⚠️ آیدی عددی معتبر بفرست.", reply_to_message_id=message.id)
        return
    tu = await db.get_user(target_id)
    tu["bot_banned"] = False
    await db.save_user(target_id, tu)
    user["admin_state"] = None
    await db.save_user(message.chat.id, user)
    await client.send_message(
        message.chat.id, f"✅ کاربر `{target_id}` آنبلاک شد.", reply_markup=kb.kb_admin_panel(), reply_to_message_id=message.id
    )
    try:
        await client.send_message(int(target_id), "✅ دسترسی شما به ربات فعال شد.")
    except Exception:
        pass


@bot.on_message(admin_state_is("panel_userinfo_waiting_user_id") & private)
async def msg_admin_userinfo(client, message):
    user = await get_event_user(message)
    target_id = str(safe_int((message.text or "").strip(), 0))
    if not target_id or target_id == "0":
        await client.send_message(message.chat.id, "⚠️ آیدی عددی معتبر بفرست.", reply_to_message_id=message.id)
        return
    tu = await db.get_user(target_id, create_if_missing=False)
    if not tu:
        await client.send_message(message.chat.id, "⚠️ کاربر یافت نشد.", reply_to_message_id=message.id)
        return
    pid = tu.get("public_id")
    info = (
        "👤 *اطلاعات کاربر*\n\n"
        f"uid: `{target_id}`\n"
        f"public: /user_{pid}\n"
        f"name: {(tu.get('display_name') or '—')}\n"
        f"gender: {normalize_gender_text(tu)}\n"
        f"coins: *{safe_int(tu.get('coins', 0), 0)}*\n"
        f"last_seen: {last_seen_text(tu)}\n"
        f"banned: {'✅' if tu.get('bot_banned') else '❌'}\n"
    )
    user["admin_state"] = None
    await db.save_user(message.chat.id, user)
    await client.send_message(message.chat.id, info, reply_markup=kb.kb_admin_panel(), reply_to_message_id=message.id)


# ---------------------------------------------------------------------------
# حذف جداگانه کانال‌های جوین اجباری
# ---------------------------------------------------------------------------
@bot.on_callback_query(private)
async def admin_force_join_delete(client, callback_query):
    data = callback_query.data or ""
    if not data.startswith("fj_delete:"):
        from balethon.errors import ContinueDispatching
        raise ContinueDispatching()
    await callback_query.answer(None)
    uid = str(callback_query.author.id)
    if not is_admin_id(uid):
        return
    ch_db_id = safe_int(data.split(":")[1], 0)
    if ch_db_id <= 0:
        return
    await db.remove_force_join_channel(ch_db_id)
    channels = await db.get_force_join_channels()
    await client.send_message(
        callback_query.message.chat.id,
        "✅ کانال حذف شد.\n\n" + fj.get_force_join_text(channels),
        reply_markup=kb.kb_admin_panel(),
    )
