"""پنل مدیریت ربات (فقط برای ADMIN_ID)."""
import asyncio

from balethon.conditions import equals, regex, private

import config
import database as db
import force_join as fj
import keyboards as kb
from bot_instance import bot
from filters import get_event_user, admin_only, admin_state_is, is_admin_id
from utils import safe_int, normalize_gender_text, last_seen_text


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
            await client.send_message(int(uid), text)
            return True
        except Exception:
            if attempt >= retries:
                return False
            await asyncio.sleep(0.4 * (attempt + 1))
    return False


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
@bot.on_message(admin_state_is("panel_broadcast_waiting_text") & private)
async def msg_admin_broadcast_text(client, message):
    user = await get_event_user(message)
    if not (message.text or "").strip():
        await client.send_message(message.chat.id, "⚠️ متن نامعتبره. دوباره بفرست.", reply_to_message_id=message.id)
        return
    broadcast_text = message.text
    sent, failed = 0, 0
    for uid, banned in await db.iter_all_user_ids():
        if banned:
            continue
        if await _send_bulk_message(client, uid, broadcast_text):
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)
    user["admin_state"] = None
    await db.save_user(message.chat.id, user)
    await client.send_message(
        message.chat.id, f"✅ ارسال همگانی انجام شد.\n\n📨 ارسال موفق: {sent}\n❌ ناموفق: {failed}",
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
    credited = await db.add_coins_to_all_users(amount, include_banned=False)
    sent, failed = 0, 0
    for uid, banned in await db.iter_all_user_ids():
        if banned:
            continue
        tu = await db.get_user(uid, create_if_missing=False)
        if not tu:
            continue
        text = f"🎁 *سکه همگانی!*\n\n✅ به شما *{amount}* 🪙 سکه هدیه داده شد.\n💰 موجودی جدید شما: *{tu['coins']}* 🪙"
        if await _send_bulk_message(client, uid, text):
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)
    fresh_user = await db.get_user(message.chat.id)
    fresh_user["admin_state"] = None
    await db.save_user(message.chat.id, fresh_user)
    await client.send_message(
        message.chat.id,
        f"✅ سکه همگانی انجام شد.\n\n🪙 مقدار: {amount}\n👥 افزایش موجودی موفق: {credited}\n📨 ارسال پیام تبریک موفق: {sent}\n❌ ناموفق: {failed}",
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
