"""پروفایل من / ویرایش پروفایل / لایک‌ها / بلاک‌ها / مخاطبین / گزارش کاربر."""
from balethon.conditions import equals, regex,private

import config
import database as db
import keyboards as kb
import moderation_log as modlog
import lists
from bot_instance import bot
from filters import get_event_user, state_is
from profile_common import (
    show_my_profile,
    show_user_profile_by_pid,
    is_blocked_between,
    maybe_reward_profile_completion,
)
from utils import safe_int, now_ts, silent_status_text

ADMIN_ID_INT = int(config.ADMIN_ID) if str(config.ADMIN_ID).isdigit() else None


# ---------------------------------------------------------------------------
# نمایش پروفایل من / دیگران
# ---------------------------------------------------------------------------
@bot.on_message(equals("👤پروفایل") & private)
async def msg_my_profile(client, message):
    user = await get_event_user(message)
    await show_my_profile(client, message.chat.id, user, reply_to_message_id=message.id)


@bot.on_message(regex(r"^/user_.+") & private)
async def msg_open_user_profile(client, message):
    user = await get_event_user(message)
    pid = (message.text or "").strip()[len("/user_"):].strip()
    await show_user_profile_by_pid(client, message.chat.id, user, pid, reply_to_message_id=message.id)


@bot.on_callback_query(equals("back_to_my_profile") & private)
async def cb_back_to_my_profile(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    await show_my_profile(client, callback_query.message.chat.id, user)


@bot.on_callback_query(equals("back_to_main_from_user") & private)
async def cb_back_to_main_from_user(client, callback_query):
    await callback_query.answer(None)
    await client.send_message(callback_query.message.chat.id, "بازگشت به منوی اصلی.", reply_markup=kb.kb_main_menu())


@bot.on_callback_query(regex(r"^back_user_profile:") & private)
async def cb_back_user_profile(client, callback_query):
    await callback_query.answer(None)
    pid = callback_query.data.split(":", 1)[1]
    user = await get_event_user(callback_query)
    await show_user_profile_by_pid(client, callback_query.message.chat.id, user, pid)


# ---------------------------------------------------------------------------
# لیست‌های مخاطبین/لایک/بلاک
# ---------------------------------------------------------------------------
@bot.on_callback_query(equals("profile_contacts") & private)
async def cb_profile_contacts(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    await lists.send_contacts_list(client, callback_query.message.chat.id, user)


@bot.on_callback_query(equals("profile_my_likes") & private)
async def cb_profile_my_likes(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    await lists.send_my_likes_list(client, callback_query.message.chat.id, user)


@bot.on_callback_query(equals("profile_blocked") & private)
async def cb_profile_blocked(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    await lists.send_blocked_list(client, callback_query.message.chat.id, user)


@bot.on_command(name="deleteAllContacts", min_arguments=0, max_arguments=0,condition=private)
async def cmd_delete_all_contacts(client, message):
    user = await get_event_user(message)
    user["contacts"] = []
    await db.save_user(message.chat.id, user)
    await client.send_message(message.chat.id, "✅ همه مخاطبین حذف شدند.", reply_to_message_id=message.id)


@bot.on_command(name="deleteAllLikes", min_arguments=0, max_arguments=0,condition=private)
async def cmd_delete_all_likes(client, message):
    user = await get_event_user(message)
    user["my_likes"] = []
    await db.save_user(message.chat.id, user)
    await client.send_message(message.chat.id, "✅ همه لایک ها حذف شدند.", reply_to_message_id=message.id)


@bot.on_command(name="unblockAll", min_arguments=0, max_arguments=0,condition=private)
async def cmd_unblock_all(client, message):
    user = await get_event_user(message)
    user["blocked_users"] = []
    await db.save_user(message.chat.id, user)
    await client.send_message(message.chat.id, "✅ رفع بلاک همه انجام شد.", reply_to_message_id=message.id)


@bot.on_command(name="deleteAllBlocked", min_arguments=0, max_arguments=0,condition=private)
async def cmd_delete_all_blocked(client, message):
    user = await get_event_user(message)
    user["blocked_users"] = []
    await db.save_user(message.chat.id, user)
    await client.send_message(message.chat.id, "✅ همه بلاک ها حذف شدند.", reply_to_message_id=message.id)


# ---------------------------------------------------------------------------
# لایک / بلاک کاربر دیگر
# ---------------------------------------------------------------------------
@bot.on_callback_query(regex(r"^like_toggle:") & private)
async def cb_like_toggle(client, callback_query):
    pid = callback_query.data.split(":", 1)[1].strip()
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id

    target_uid, target_user = await db.get_user_by_public_id(pid)
    if not target_user:
        await callback_query.answer("کاربر یافت نشد")
        return
    if is_blocked_between(user, target_user):
        await callback_query.answer("امکان لایک نیست (بلاک)")
        return

    lists.normalize_simple_list(user, "my_likes")
    my_likes = user.get("my_likes") or []
    liked = pid in my_likes
    if liked:
        user["my_likes"] = [x for x in my_likes if x != pid]
        target_user["likes"] = max(0, safe_int(target_user.get("likes", 0), 0) - 1)
        await db.save_user(chat_id, user)
        await db.save_user(target_uid, target_user)
    else:
        user["my_likes"].append(pid)
        target_user["likes"] = safe_int(target_user.get("likes", 0), 0) + 1
        await db.save_user(chat_id, user)
        await db.save_user(target_uid, target_user)
        try:
            await client.send_message(int(target_uid), f"❤️ یک لایک جدید گرفتی!\n🆔 از طرف: /user_{user.get('public_id')}")
        except Exception:
            pass

    await show_user_profile_by_pid(client, chat_id, user, pid)


@bot.on_callback_query(regex(r"^block_toggle:") & private)
async def cb_block_toggle(client, callback_query):
    pid = callback_query.data.split(":", 1)[1].strip()
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id

    lists.normalize_simple_list(user, "blocked_users")
    bl = set(user.get("blocked_users") or [])
    if pid in bl:
        user["blocked_users"] = [x for x in user["blocked_users"] if x != pid]
        await db.save_user(chat_id, user)
        await callback_query.answer("✅ آنبلاک شد", show_alert=True)
    else:
        user["blocked_users"].append(pid)
        await db.save_user(chat_id, user)
        await callback_query.answer("✅ کاربر بلاک شد", show_alert=True)

        target_uid, _ = await db.get_user_by_public_id(pid)
        if target_uid and user.get("chat_with") == str(target_uid):
            from handlers.chat import end_chat_for, notify_watchers_chat_end
            other_uid = user.get("chat_with")
            await end_chat_for(chat_id, client=client)
            if other_uid:
                await end_chat_for(other_uid, client=client)
            try:
                await client.send_message(chat_id, "⛔ کاربر بلاک شد و چت قطع شد.\n\nاگر داخل بازی بودید، بازی هم خودکار لغو شد.", reply_markup=kb.kb_main_menu())
            except Exception:
                pass
            if other_uid:
                try:
                    await client.send_message(int(other_uid), "⛔ شما توسط مخاطب بلاک شدید و چت قطع شد.\n\nاگر داخل بازی بودید، بازی هم خودکار لغو شد.", reply_markup=kb.kb_main_menu())
                except Exception:
                    pass
            await notify_watchers_chat_end(client, other_uid)
            await notify_watchers_chat_end(client, chat_id)

    user = await db.get_user(chat_id)
    await show_user_profile_by_pid(client, chat_id, user, pid)


# ---------------------------------------------------------------------------
# افزودن به مخاطبین
# ---------------------------------------------------------------------------
@bot.on_callback_query(regex(r"^add_contact:") & private)
async def cb_add_contact(client, callback_query):
    pid = callback_query.data.split(":", 1)[1].strip()
    await callback_query.answer(None)
    if not pid:
        return
    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id
    user["state"] = "contact_wait_label"
    user["tmp_contact_pid"] = pid
    await db.save_user(chat_id, user)
    await client.send_message(
        chat_id,
        "👤شما در حال ذخیره کردن کاربر  در لیست مخاطبین خود هستید.\n\n"
        "در صورت تمایل برای اینکار عنوانی که بعدا بتوانید این کاربر را بیاد آورید ارسال کنید "
        "یا در صورت عدم تمایل از منوی پایین روی گزینه 《 بازگشت 🔙 》 کلیک کنید.",
        reply_markup=kb.kb_back_only(),
    )


@bot.on_message(state_is("contact_wait_label") & private)
async def msg_contact_wait_label(client, message):
    user = await get_event_user(message)
    chat_id = message.chat.id
    txt = (message.text or "").strip()
    if txt == "بازگشت 🔙":
        user["state"] = None
        user["tmp_contact_pid"] = None
        await db.save_user(chat_id, user)
        await client.send_message(chat_id, "✅ بازگشت انجام شد.", reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id)
        return

    pid = str(user.get("tmp_contact_pid") or "").strip()
    if not pid:
        user["state"] = None
        await db.save_user(chat_id, user)
        await client.send_message(chat_id, "⚠️ خطا.", reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id)
        return

    lists.normalize_contacts(user)
    found = False
    for it in user["contacts"]:
        if it.get("pid") == pid:
            it["label"] = txt[:40]
            found = True
            break
    if not found:
        user["contacts"].append({"pid": pid, "label": txt[:40]})
    user["state"] = None
    user["tmp_contact_pid"] = None
    await db.save_user(chat_id, user)
    await client.send_message(chat_id, "✅ در مخاطبین ذخیره شد.", reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id)


# ---------------------------------------------------------------------------
# سایلنت
# ---------------------------------------------------------------------------
@bot.on_callback_query(equals("profile_silent") & private)
async def cb_profile_silent(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    await _show_silent_menu(client, callback_query.message.chat.id, user)


async def _show_silent_menu(client, chat_id, user, edit_message_id=None):
    text = (
        f"🔻 حالت سایلنت : {silent_status_text(user)}\n\n"
        "_____________________\n"
        " 💡با فعال شدن حالت سایلنت ، درخواست چت دریافت نخواهید کرد."
    )
    if edit_message_id:
        try:
            await client.edit_message_text(chat_id, edit_message_id, text, reply_markup=kb.ikb_silent_buttons())
            return
        except Exception:
            pass
    await client.send_message(chat_id, text, reply_markup=kb.ikb_silent_buttons())


@bot.on_callback_query(equals("silent_1h", "silent_20m", "silent_forever", "silent_off") & private)
async def cb_silent_options(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id
    data = callback_query.data
    if data == "silent_1h":
        user["silent_forever"] = False
        user["silent_until"] = now_ts() + 3600
    elif data == "silent_20m":
        user["silent_forever"] = False
        user["silent_until"] = now_ts() + 20 * 60
    elif data == "silent_forever":
        user["silent_forever"] = True
        user["silent_until"] = None
    elif data == "silent_off":
        user["silent_forever"] = False
        user["silent_until"] = None
    await db.save_user(chat_id, user)
    await _show_silent_menu(client, chat_id, user, edit_message_id=callback_query.message.id)


# ---------------------------------------------------------------------------
# ویرایش پروفایل (متنی)
# ---------------------------------------------------------------------------
@bot.on_callback_query(equals("profile_edit_text") & private)
async def cb_profile_edit_text(client, callback_query):
    await callback_query.answer(None)
    await client.send_message(
        callback_query.message.chat.id,
        "✏️ *ویرایش پروفایل*\n\n"
        "از منوی پایین انتخاب کن.\n"
        "هرجا خواستی برگردی: «بازگشت 🔙»",
        reply_markup=kb.kb_edit_profile_text_menu(),
    )


@bot.on_message(equals("✏️ تغییر نام") & private)
async def msg_edit_name_btn(client, message):
    user = await get_event_user(message)
    user["state"] = "edit_wait_name"
    await db.save_user(message.chat.id, user)
    await client.send_message(message.chat.id, "✏️ نام جدید را ارسال کنید.\n(بازگشت: «بازگشت 🔙»)", reply_markup=kb.kb_back_only(), reply_to_message_id=message.id)


@bot.on_message(equals("✏️ تغییر جنسیت") & private)
async def msg_edit_gender_btn(client, message):
    user = await get_event_user(message)
    user["state"] = "edit_wait_gender"
    await db.save_user(message.chat.id, user)
    await client.send_message(message.chat.id, "✏️ جنسیت را انتخاب کن 👇", reply_markup=kb.kb_gender_text(), reply_to_message_id=message.id)


@bot.on_message(equals("✏️ تغییر سن") & private)
async def msg_edit_age_btn(client, message):
    user = await get_event_user(message)
    user["state"] = "edit_wait_age"
    await db.save_user(message.chat.id, user)
    await client.send_message(message.chat.id, "✏️ سن را بفرست/انتخاب کن 👇", reply_markup=kb.kb_age_1_99(), reply_to_message_id=message.id)


@bot.on_message(equals("✏️ تغییر استان") & private)
async def msg_edit_province_btn(client, message):
    user = await get_event_user(message)
    user["state"] = "edit_wait_province"
    await db.save_user(message.chat.id, user)
    await client.send_message(message.chat.id, "✏️ استان را انتخاب کن 👇", reply_markup=kb.kb_provinces(), reply_to_message_id=message.id)


@bot.on_message(equals("✏️ تغییر شهر") & private)
async def msg_edit_city_btn(client, message):
    user = await get_event_user(message)
    user["state"] = "edit_wait_city"
    await db.save_user(message.chat.id, user)
    await client.send_message(message.chat.id, "✏️ شهر را انتخاب کن 👇", reply_markup=kb.kb_cities(), reply_to_message_id=message.id)


@bot.on_message(equals("✏️ تغییر عکس") & private)
async def msg_edit_photo_btn(client, message):
    user = await get_event_user(message)
    user["state"] = "edit_wait_photo"
    await db.save_user(message.chat.id, user)
    await client.send_message(message.chat.id, "✏️ عکس جدید پروفایل را ارسال کنید.\n(بازگشت: «بازگشت 🔙»)", reply_markup=kb.kb_back_only(), reply_to_message_id=message.id)


@bot.on_message(state_is("edit_wait_name") & private)
async def msg_edit_wait_name(client, message):
    user = await get_event_user(message)
    chat_id = message.chat.id
    txt = (message.text or "").strip()
    if txt == "بازگشت 🔙":
        user["state"] = None
        await db.save_user(chat_id, user)
        await show_my_profile(client, chat_id, user)
        return
    if len(txt) < 2 or len(txt) > 30:
        await client.send_message(chat_id, "⚠️ نام نامعتبر است. (۲ تا ۳۰ کاراکتر)", reply_markup=kb.kb_back_only(), reply_to_message_id=message.id)
        return
    user["display_name"] = txt
    user["state"] = None
    await db.save_user(chat_id, user)
    await maybe_reward_profile_completion(client, chat_id, user)
    await show_my_profile(client, chat_id, user)


@bot.on_message(state_is("edit_wait_gender") & private)
async def msg_edit_wait_gender(client, message):
    user = await get_event_user(message)
    chat_id = message.chat.id
    txt = (message.text or "").strip()
    if txt == "بازگشت 🔙":
        user["state"] = None
        await db.save_user(chat_id, user)
        await show_my_profile(client, chat_id, user)
        return
    if txt == "🙎‍♂️ پسر":
        user["gender"] = "male"
    elif txt == "🙍‍♀️ دختر":
        user["gender"] = "female"
    else:
        await client.send_message(chat_id, "⚠️ فقط از گزینه‌ها انتخاب کن.", reply_markup=kb.kb_gender_text(), reply_to_message_id=message.id)
        return
    user["state"] = None
    await db.save_user(chat_id, user)
    await maybe_reward_profile_completion(client, chat_id, user)
    await show_my_profile(client, chat_id, user)


@bot.on_message(state_is("edit_wait_age") & private)
async def msg_edit_wait_age(client, message):
    user = await get_event_user(message)
    chat_id = message.chat.id
    txt = (message.text or "").strip()
    if txt == "بازگشت 🔙":
        user["state"] = None
        await db.save_user(chat_id, user)
        await show_my_profile(client, chat_id, user)
        return
    age = safe_int(txt, 0)
    if age < 1 or age > 99:
        await client.send_message(chat_id, "⚠️ سن نامعتبره. 1 تا 99", reply_markup=kb.kb_age_1_99(), reply_to_message_id=message.id)
        return
    user["age"] = age
    user["state"] = None
    await db.save_user(chat_id, user)
    await maybe_reward_profile_completion(client, chat_id, user)
    await show_my_profile(client, chat_id, user)


@bot.on_message(state_is("edit_wait_province") & private)
async def msg_edit_wait_province(client, message):
    user = await get_event_user(message)
    chat_id = message.chat.id
    txt = (message.text or "").strip()
    if txt == "بازگشت 🔙":
        user["state"] = None
        await db.save_user(chat_id, user)
        await show_my_profile(client, chat_id, user)
        return
    if txt not in config.PROVINCES:
        await client.send_message(chat_id, "⚠️ استان را فقط از لیست انتخاب کن.", reply_markup=kb.kb_provinces(), reply_to_message_id=message.id)
        return
    user["province"] = txt
    user["state"] = None
    await db.save_user(chat_id, user)
    await maybe_reward_profile_completion(client, chat_id, user)
    await show_my_profile(client, chat_id, user)


@bot.on_message(state_is("edit_wait_city") & private)
async def msg_edit_wait_city(client, message):
    user = await get_event_user(message)
    chat_id = message.chat.id
    txt = (message.text or "").strip()
    if txt == "بازگشت 🔙":
        user["state"] = None
        await db.save_user(chat_id, user)
        await show_my_profile(client, chat_id, user)
        return
    if txt not in config.IRAN_CITIES:
        await client.send_message(chat_id, "⚠️ شهر را فقط از لیست انتخاب کن.", reply_markup=kb.kb_cities(), reply_to_message_id=message.id)
        return
    user["city"] = txt
    user["state"] = None
    await db.save_user(chat_id, user)
    await maybe_reward_profile_completion(client, chat_id, user)
    await show_my_profile(client, chat_id, user)


@bot.on_message(state_is("edit_wait_photo") & private)
async def msg_edit_wait_photo(client, message):
    user = await get_event_user(message)
    chat_id = message.chat.id
    txt = (message.text or "").strip()
    if txt == "بازگشت 🔙":
        user["state"] = None
        await db.save_user(chat_id, user)
        await show_my_profile(client, chat_id, user)
        return
    if message.photo:
        file_id = message.photo[-1].id
        if not file_id:
            await client.send_message(chat_id, "⚠️ عکس نامعتبر است. دوباره ارسال کن.", reply_markup=kb.kb_back_only(), reply_to_message_id=message.id)
            return
        user["profile_photo_file_id"] = file_id
        user["state"] = None
        await db.save_user(chat_id, user)
        await maybe_reward_profile_completion(client, chat_id, user)
        await show_my_profile(client, chat_id, user)
        return
    await client.send_message(chat_id, "❓ لطفاً یک عکس ارسال کن.", reply_markup=kb.kb_back_only(), reply_to_message_id=message.id)


# ---------------------------------------------------------------------------
# گزارش کاربر
# ---------------------------------------------------------------------------
@bot.on_callback_query(regex(r"^report:") & private)
async def cb_report(client, callback_query):
    pid = callback_query.data.split(":", 1)[1].strip()
    await callback_query.answer(None)
    await client.send_message(
        callback_query.message.chat.id,
        "⚠️ فرم ارسال گزارش عدم رعایت قوانین\n\n"
        f"چرا میخوای /user_{pid} رو گزارش کنی؟\n\n"
        "- توجه : تمامی گزارشات بررسی خواهند شد و 🔴 ارسال گزارشات اشتباه موجب مسدود شدن شما خواهد شد.\n\n"
        "انتخاب کنید 👇",
        reply_markup=kb.ikb_report_reasons(pid),
    )


@bot.on_callback_query(regex(r"^report_reason:") & private)
async def cb_report_reason(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    _, pid, code = callback_query.data.split(":", 2)
    _, target_user = await db.get_user_by_public_id(pid)
    if not target_user:
        await callback_query.answer("کاربر یافت نشد")
        return
    user["state"] = "report_wait_screenshot"
    user["tmp_report_pid"] = pid
    user["tmp_report_reason"] = code
    await db.save_user(callback_query.message.chat.id, user)
    try:
        await client.edit_message_text(
            callback_query.message.chat.id,
            callback_query.message.id,
            "📸 *ارسال اسکرین‌شات الزامی است*\n\n"
            "برای تکمیل گزارش، یک عکس یا اسکرین‌شات واضح از تخلف ارسال کنید.\n"
            "گزارش بدون عکس ثبت و برای ادمین ارسال نمی‌شود.\n\n"
            "برای انصراف، «لغو» را بفرستید.",
        )
    except Exception:
        pass
    await client.send_message(
        callback_query.message.chat.id,
        "👇 حالا اسکرین‌شات تخلف را ارسال کنید.",
        reply_markup=kb.kb_cancel_only(),
    )


@bot.on_message(state_is("report_wait_screenshot") & private)
async def msg_report_screenshot(client, message):
    user = await get_event_user(message)
    chat_id = message.chat.id
    text = (message.text or "").strip()

    if text in ("لغو", "بازگشت 🔙"):
        user["state"] = None
        user["tmp_report_pid"] = None
        user["tmp_report_reason"] = None
        await db.save_user(chat_id, user)
        await client.send_message(
            chat_id, "✅ ارسال گزارش لغو شد.", reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id
        )
        return

    if not message.photo:
        await client.send_message(
            chat_id,
            "⚠️ گزارش فقط با ارسال *عکس یا اسکرین‌شات* ثبت می‌شود. لطفاً تصویر را ارسال کنید.",
            reply_markup=kb.kb_cancel_only(),
            reply_to_message_id=message.id,
        )
        return

    pid = str(user.get("tmp_report_pid") or "").strip()
    reason_code = str(user.get("tmp_report_reason") or "").strip()
    target_uid, target_user = await db.get_user_by_public_id(pid)
    if not target_user or not reason_code:
        user["state"] = None
        user["tmp_report_pid"] = None
        user["tmp_report_reason"] = None
        await db.save_user(chat_id, user)
        await client.send_message(
            chat_id, "⚠️ اطلاعات گزارش منقضی شده؛ دوباره از پروفایل کاربر گزارش را شروع کنید.",
            reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id,
        )
        return

    try:
        await modlog.log_report(
            client, str(message.author.id), user, target_uid, target_user, reason_code, message
        )
    except Exception as exc:
        print(f"report moderation log failed: {exc}")
        await client.send_message(
            chat_id,
            "❌ ارسال گزارش به گروه مدیریت ناموفق بود. دوباره همین اسکرین‌شات را ارسال کنید.",
            reply_markup=kb.kb_cancel_only(), reply_to_message_id=message.id,
        )
        return

    user["state"] = None
    user["tmp_report_pid"] = None
    user["tmp_report_reason"] = None
    await db.save_user(chat_id, user)
    await client.send_message(
        chat_id,
        "✅ گزارش همراه اسکرین‌شات ثبت شد و برای بررسی ادمین ارسال گردید.",
        reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id,
    )


# ---------------------------------------------------------------------------
# اطلاع‌رسانیِ اتمام چت مخاطب
# ---------------------------------------------------------------------------
@bot.on_callback_query(regex(r"^notify_end:") & private)
async def cb_notify_end(client, callback_query):
    pid = callback_query.data.split(":", 1)[1].strip()
    await callback_query.answer(None)
    target_uid, target_user = await db.get_user_by_public_id(pid)
    if not target_user:
        await callback_query.answer("کاربر یافت نشد")
        return
    if not target_user.get("chat_with"):
        await callback_query.answer("کاربر درحال چت نیست")
        return

    await client.send_message(
        callback_query.message.chat.id,
        f"🔔 به محض اتمام چت کاربر /user_{pid} به شما اطلاع داده خواهد شد.\n"
        "(راهنما : /help_onw)\n\n"
        f"⚠️ توجه : فعال کردن این قابلیت {config.NOTIFY_END_COST} 💰 سکه از شما کم خواهد کرد.\n\n"
        "فعال سازی 👇",
        reply_markup=kb.ikb(
            [(f"کسر {config.NOTIFY_END_COST}💰سکه و فعالسازی", f"notify_end_confirm:{pid}")],
            [("بازگشت", f"back_user_profile:{pid}")],
        ),
    )


@bot.on_callback_query(regex(r"^notify_end_confirm:") & private)
async def cb_notify_end_confirm(client, callback_query):
    pid = callback_query.data.split(":", 1)[1].strip()
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id

    target_uid, target_user = await db.get_user_by_public_id(pid)
    if not target_user:
        await callback_query.answer("کاربر یافت نشد")
        return
    if safe_int(user.get("coins", 0), 0) < config.NOTIFY_END_COST:
        await callback_query.answer("موجودی سکه کافی نیست", show_alert=True)
        await client.send_message(
            chat_id,
            "🪙 *موجودی سکه کافی نیست*\n\n"
            f"برای فعال‌سازی این اطلاع‌رسانی به *{config.NOTIFY_END_COST}* سکه نیاز دارید.\n"
            f"موجودی فعلی شما: *{safe_int(user.get('coins', 0), 0)}* سکه\n\n"
            "از گزینه‌های زیر می‌توانید سکه تهیه کنید یا با معرفی دوستان سکه رایگان بگیرید 👇",
            reply_markup=kb.ikb_coin_buy_menu(),
        )
        return

    user["coins"] = safe_int(user.get("coins", 0), 0) - config.NOTIFY_END_COST
    await db.save_user(chat_id, user)

    exp = now_ts() + 10 * 24 * 3600
    watchers = target_user.get("notify_chat_end") or []
    watchers = [w for w in watchers if not (isinstance(w, dict) and str(w.get("watcher_uid")) == str(chat_id))]
    watchers.append({"watcher_uid": str(chat_id), "expire_ts": exp})
    target_user["notify_chat_end"] = watchers
    await db.save_user(target_uid, target_user)

    await client.send_message(
        chat_id,
        "✅ با موفقیت ثبت شد. (راهنما : /help_onw)\n\n"
        f"🔔 به محض اتمام چت کاربر /user_{pid} به شما اطلاع داده خواهد شد.",
    )

