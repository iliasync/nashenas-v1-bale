"""معرفی به دوستان (لینک دعوت) و لینک پیام ناشناس."""
import os

from balethon.conditions import equals,private

import config
import database as db
from bot_links import build_start_link
from bot_instance import bot
from filters import get_event_user
from utils import safe_int

IMG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "IMG.jpg")


async def invite_caption_for_pid(client, inviter_pid: str) -> str:
    inviter_pid = (inviter_pid or "").strip()
    invite_link = await build_start_link(client, f"z_{inviter_pid}")
    return (
        "《 چت ناشناس↑cₕₐₜ    🤖》 هستم،بامن میتونی\n\n"
        "📡 افراد #نزدیک ، #هم‌سنی ، #هم‌استانی خودتو پیداکنی و باهاشون #ناشناس چت کنی و آشنا شی😍\n\n"
        "پس منتظر چی هستی؟🤔 بدووو بیا که منتظرتم!🏃‍♂️\n\n"
        "همین الان روی لینک بزن  👇\n"
        f"{invite_link}\n\n"
        "✅ #رایگان و #واقعی 😎"
    )


async def send_invite_banner(client, chat_id, user: dict, reply_to_message_id=None):
    inviter_pid = await db.ensure_unique_public_id(chat_id)
    cap = await invite_caption_for_pid(client, inviter_pid)

    mid = None
    if os.path.isfile(IMG_PATH):
        try:
            res = await client.send_photo(chat_id, IMG_PATH, caption=cap, reply_to_message_id=reply_to_message_id)
            mid = res.id if res else None
        except Exception as e:
            print(f"send_invite_banner (photo) failed: {e}")
    if mid is None:
        try:
            m1 = await client.send_message(chat_id, "⚠️ فایل IMG.jpg پیدا نشد.\n\n" + cap, reply_to_message_id=reply_to_message_id)
            mid = m1.id if m1 else None
        except Exception:
            mid = None

    inv_count = safe_int(user.get("invite_count", 0), 0)
    msg2 = (
        "لینک⚡️ دعوت شما با موفقیت ساخته شد 👆\n\n"
        "شما میتوانید بنر حاوی لینک⚡️ خود را به گـــروه ها و دوستان خود ارسال کنید\n\n"
        f"با معرفی هر نفر {config.INVITE_JOIN_REWARD_OWNER} سکه بگیرید! برای اطلاعات بیشتر راهنمای سکه رو بخون (/help_credit)\n\n"
        f"👈 شما تاکنون \" {inv_count} \" نفر را به این ربات دعوت کرده اید."
    )
    try:
        if mid:
            await client.send_message(chat_id, msg2, reply_to_message_id=mid)
        else:
            await client.send_message(chat_id, msg2)
    except Exception as e:
        print(f"send_invite_banner (text) failed: {e}")


async def send_anonymous_link(client, chat_id, user: dict, reply_to_message_id=None, first_name=""):
    code = await db.ensure_unique_anon_code(chat_id)
    name = (user.get("display_name") or first_name or "دوست").strip()
    link = await build_start_link(client, f"anon_{code}")

    try:
        m1 = await client.send_message(
            chat_id,
            f"سلام  {name}  هستم ✋\n\n"
            "لینک زیر رو لمس کن و هر حرفی که تو دلت هست یا هر انتقادی که نسبت به من داری رو با خیال راحت بنویس و بفرست. "
            "بدون اینکه از اسمت باخبر بشم پیامت به من میرسه. خودتم میتونی امتحان کنی و از بقیه بخوای راحت و ناشناس بهت پیام بفرستن، "
            "حرفای خیلی جالبی میشنوی! 😉\n\n\n"
            "👇👇\n"
            f"{link}",
            reply_to_message_id=reply_to_message_id,
        )
    except Exception:
        m1 = None
    if m1:
        try:
            await client.send_message(
                chat_id,
                "☝️ پیام بالا رو به دوستات و گروه هایی که میشناسی فـوروارد کن یا لـینک داخلش رو تو شبکه های اجتماعی بذار و توئیت کن، "
                "تا بقیه بتونن بهت پیام ناشناس بفرستن. پیام ها از طریق همین برنامه بهت میرسه.",
                reply_to_message_id=m1.id,
            )
        except Exception:
            pass


@bot.on_message(equals("🚸 معرفی به دوستان (سکه رایگان)") & private)
async def msg_invite_button(client, message):
    user = await get_event_user(message)
    await send_invite_banner(client, message.chat.id, user, reply_to_message_id=message.id)


@bot.on_callback_query(equals("buy_invite") & private)
async def cb_buy_invite(client, callback_query):
    await callback_query.answer(None)
    user = await get_event_user(callback_query)
    await send_invite_banner(client, callback_query.message.chat.id, user, reply_to_message_id=callback_query.message.id)


@bot.on_message(equals("لینک ناشناس من 📬") & private)
async def msg_anon_link_button(client, message):
    user = await get_event_user(message)
    first_name = message.author.first_name or "" if message.author else ""
    await send_anonymous_link(client, message.chat.id, user, reply_to_message_id=message.id, first_name=first_name)
