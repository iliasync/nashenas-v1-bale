"""خریدِ سکه (کارت‌به‌کارت + تایید ادمین) با OCR بهترین-تلاش روی رسید."""
import os
import tempfile
from datetime import datetime

from balethon.conditions import create, equals, regex,private
from balethon.objects import Message

import config
import database as db
import keyboards as kb
from bot_instance import bot
from filters import get_event_user, admin_only
from utils import safe_int, gen_req_id, now_ts


def buy_state_is(*states):
    """شرط: user['buy']['state'] (نه state کلی کاربر) برابر یکی از این مقادیر است."""
    @create(can_process=Message)
    async def _cond(event):
        user = await get_event_user(event, create_if_missing=False)
        return user is not None and (user.get("buy") or {}).get("state") in states
    return _cond


async def try_extract_text_from_file_id(client, file_id: str) -> str:
    """تلاش برای OCR روی تصویر رسید؛ اگر PIL/pytesseract نصب نباشد رشته‌ی خالی برمی‌گرداند."""
    if not file_id:
        return ""
    try:
        file_obj = await client.get_file(file_id)
        if not file_obj or not file_obj.path:
            return ""
        content = await client.download(file_obj.path)
    except Exception as e:
        print(f"download receipt failed: {e}")
        return ""

    path = None
    try:
        fd, path = tempfile.mkstemp(prefix="receipt_", suffix=".jpg")
        os.close(fd)
        with open(path, "wb") as f:
            f.write(content)
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore
        img = Image.open(path)
        return (pytesseract.image_to_string(img) or "").strip()
    except Exception:
        return ""
    finally:
        if path:
            try:
                os.remove(path)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# منوی خرید سکه
# ---------------------------------------------------------------------------
@bot.on_message(equals("💰سکه بات") & private)
async def msg_coins_button(client, message):
    user = await get_event_user(message)
    coins_now = safe_int(user.get("coins", 0), 0)
    txt = (
        f'💰 سکه فعلی شما: "{coins_now}"\n'
        "ـــــــــــــــــــــــــــــــ\n"
        "❓ روش های بدست آوردن سکه چیست؟\n\n"
        "برای افزایش سکه به صورت رایگان بنر لینک⚡️ مخصوص خودت (/link) رو برای دوستات بفرست و 7 سکه دریافت کن\n\n"
        "- برای اطلاعات بیشتر راهنمای سکه رو بخون (/help_credit)\n\n"
        "2️⃣ خرید سکه بصورت آنلاین:\n\n"
        "برای خرید سکه یکی از تعرفه های زیر را انتخاب نمایید👇"
    )
    await client.send_message(message.chat.id, txt, reply_markup=kb.ikb_coin_buy_menu(), reply_to_message_id=message.id)


@bot.on_callback_query(regex(r"^buy_pkg:") & private)
async def cb_buy_pkg(client, callback_query):
    await callback_query.answer(None)
    _, coins_s, price_s = callback_query.data.split(":")
    coins, price = safe_int(coins_s, 0), safe_int(price_s, 0)
    if coins <= 0 or price <= 0:
        await client.send_message(callback_query.message.chat.id, "⚠️ خطا در بسته.")
        return

    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id
    tx_id = gen_req_id()
    user["buy"] = {"state": "awaiting_paid_click", "tmp_pkg": {"coins": coins, "price": price, "tx_id": tx_id}, "tmp_msg_id": None}
    await db.save_user(chat_id, user)

    txt = (
        f'🛒 خرید "{coins}" سکه\n'
        f'💵 مبلغ: "{price:,}" تومان\n\n'
        "💳 لطفا مبلغ را به شماره کارت زیر واریز کنید:\n\n"
        f"`{config.PAYMENT_CARD_NUMBER}`\n\n"
        "✅ پس از پرداخت، روی دکمه زیر کلیک کنید:"
    )
    m = await client.send_message(chat_id, txt, reply_markup=kb.ikb_payment_actions(tx_id), reply_to_message_id=callback_query.message.id)
    if m:
        user["buy"]["tmp_msg_id"] = m.id
        await db.save_user(chat_id, user)


@bot.on_callback_query(regex(r"^buy_cancel:") & private)
async def cb_buy_cancel(client, callback_query):
    await callback_query.answer(None)
    chat_id = callback_query.message.chat.id
    try:
        await client.delete_message(chat_id, callback_query.message.id)
    except Exception:
        pass
    user = await get_event_user(callback_query)
    user["buy"] = {"state": None, "tmp_pkg": None, "tmp_msg_id": None}
    await db.save_user(chat_id, user)


@bot.on_callback_query(regex(r"^buy_paid:") & private)
async def cb_buy_paid(client, callback_query):
    await callback_query.answer(None)
    tx_id = callback_query.data.split(":", 1)[1].strip()
    user = await get_event_user(callback_query)
    chat_id = callback_query.message.chat.id
    pkg = (user.get("buy") or {}).get("tmp_pkg") or {}
    if pkg.get("tx_id") != tx_id:
        await client.send_message(chat_id, "⚠️ این پرداخت منقضی شده یا متعلق به شما نیست.")
        return
    user["buy"]["state"] = "awaiting_receipt"
    await db.save_user(chat_id, user)
    await client.send_message(chat_id, "📸 لطفا عکس رسید پرداخت را ارسال کنید.", reply_to_message_id=callback_query.message.id)


@bot.on_message(buy_state_is("awaiting_receipt") & private)
async def msg_receipt_photo(client, message):
    user = await get_event_user(message)
    chat_id = message.chat.id

    if not message.photo:
        await client.send_message(chat_id, "📸 لطفا *فقط عکس رسید* پرداخت را ارسال کنید.", reply_to_message_id=message.id)
        return

    file_id = message.photo[-1].id
    pkg = (user.get("buy") or {}).get("tmp_pkg") or {}
    coins = safe_int(pkg.get("coins"), 0)
    price = safe_int(pkg.get("price"), 0)
    tx_id = pkg.get("tx_id") or gen_req_id()

    ocr_text = await try_extract_text_from_file_id(client, file_id)

    await db.create_payment({
        "tx_id": tx_id, "buyer_uid": chat_id, "buyer_pid": user.get("public_id"),
        "coins": coins, "price": price, "file_id": file_id, "ocr_text": ocr_text,
        "status": "pending", "created_at": now_ts(),
    })

    cap = (
        "🧾 *رسید پرداخت جدید*\n\n"
        f"👤 خریدار: `{chat_id}`  /user_{user.get('public_id')}\n"
        f"🪙 تعداد سکه: *{coins}*\n"
        f"💵 مبلغ: *{price:,}* تومان\n"
        f"🆔 تراکنش: `{tx_id}`\n"
        f"⏰ زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"📄 متن استخراج‌شده رسید (OCR):\n`{(ocr_text[:900] if ocr_text else '—')}`"
    )
    try:
        await client.send_photo(
            int(config.ADMIN_ID), file_id, caption=cap,
            reply_markup=kb.ikb(
                [("✅ تایید و انتقال سکه", f"pay_approve:{tx_id}")],
                [("❌ رد و فیک رسید", f"pay_reject:{tx_id}")],
            ),
        )
    except Exception as e:
        print(f"notify admin about payment failed: {e}")

    user.setdefault("transactions", [])
    user["transactions"].append({
        "tx_id": tx_id, "type": "buy_coin", "coins": coins, "price": price, "status": "pending",
        "created_at": now_ts(), "note": (ocr_text[:500] if ocr_text else None),
    })
    user["buy"] = {"state": None, "tmp_pkg": None, "tmp_msg_id": None}
    await db.save_user(chat_id, user)

    await client.send_message(
        chat_id, "✅ رسید شما ارسال شد.\nپس از بررسی، نتیجه اعلام می‌شود.", reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id
    )


# ---------------------------------------------------------------------------
# تایید/رد پرداخت توسط ادمین
# ---------------------------------------------------------------------------
@bot.on_callback_query(regex(r"^(pay_approve|pay_reject):") & private & admin_only)
async def cb_pay_review(client, callback_query):
    await callback_query.answer(None)
    chat_id = callback_query.message.chat.id
    action, tx_id = callback_query.data.split(":", 1)

    tx = await db.get_payment(tx_id)
    if not tx or tx.get("status") != "pending":
        await callback_query.answer("تراکنش نامعتبر/قبلا بررسی شده")
        return

    buyer_uid = str(tx.get("buyer_uid") or "")
    coins = safe_int(tx.get("coins"), 0)
    price = safe_int(tx.get("price"), 0)

    bu = await db.get_user(buyer_uid, create_if_missing=False)
    if not bu:
        await db.update_payment_status(tx_id, "failed_user_missing")
        await callback_query.answer("کاربر یافت نشد")
        return

    def _mark_tx(u, status):
        for t in (u.get("transactions") or []):
            if isinstance(t, dict) and t.get("tx_id") == tx_id:
                t["status"] = status

    if action == "pay_reject":
        await db.update_payment_status(tx_id, "rejected")
        _mark_tx(bu, "rejected")
        await db.save_user(buyer_uid, bu)
        try:
            await client.send_message(
                int(buyer_uid), f"❌ پرداخت شما رد شد.\n🆔 تراکنش: `{tx_id}`\nاگر مشکلی هست با پشتیبانی در ارتباط باشید."
            )
        except Exception:
            pass
        try:
            await client.edit_message_caption(chat_id, callback_query.message.id, f"❌ رد شد.\nTX: `{tx_id}`")
        except Exception:
            pass
        return

    bu["coins"] = safe_int(bu.get("coins", 0), 0) + coins
    _mark_tx(bu, "approved")
    await db.save_user(buyer_uid, bu)
    await db.update_payment_status(tx_id, "approved")

    try:
        await client.send_message(
            int(buyer_uid),
            "🎉 *پرداخت تایید شد!*\n\n"
            f"✅ *{coins}* سکه به حساب شما اضافه شد.\n"
            f"💰 موجودی جدید شما: *{safe_int(bu.get('coins', 0), 0)}*\n\n"
            "🙏 ممنون از خرید شما",
        )
    except Exception:
        pass
    try:
        await client.edit_message_caption(
            chat_id, callback_query.message.id, f"✅ تایید شد و انتقال انجام شد.\nTX: `{tx_id}`\n🪙{coins} | 💵{price:,}"
        )
    except Exception:
        pass
