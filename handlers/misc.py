"""دستورهای راهنما / قوانین / میانبرها."""
from balethon.conditions import equals,private

import keyboards as kb
import texts
from bot_instance import bot
from filters import is_admin_id


@bot.on_command(name="myid", min_arguments=0, max_arguments=0, condition=private)
async def cmd_myid(client, message):
    uid = str(message.author.id).strip()
    await client.send_message(
        message.chat.id,
        f"🆔 آیدی عددی شما: `{uid}`\n"
        f"🔐 تشخیص ادمین: {'✅ بله' if is_admin_id(uid) else '❌ خیر'}",
        reply_to_message_id=message.id,
    )


@bot.on_command(name="version", min_arguments=0, max_arguments=0, condition=private)
async def cmd_version(client, message):
    if not is_admin_id(message.author.id):
        return
    version = "manual/zip"
    try:
        with open("/home/jowkdwuy/nashenasV2/.deployed_sha", encoding="utf-8") as file:
            version = file.read().strip() or version
    except OSError:
        pass
    await client.send_message(
        message.chat.id,
        f"🤖 نسخه در حال اجرا: `{version}`\n"
        "قابلیت: `admin-profile-v2`",
        reply_to_message_id=message.id,
    )


@bot.on_callback_query(equals("show_rules") & private)
async def cb_show_rules(client, callback_query):
    await callback_query.answer(None)
    await client.send_message(
        callback_query.message.chat.id, texts.RULES_TEXT, reply_to_message_id=callback_query.message.id
    )


@bot.on_command(name="ghavanin", min_arguments=0, max_arguments=0,condition=private)
async def cmd_ghavanin(client, message):
    await client.send_message(
        message.chat.id, "برای مشاهده قوانین روی دکمه زیر بزن 👇", reply_markup=kb.ikb_rules_button(),
        reply_to_message_id=message.id,
    )


_HELP_COMMANDS = {
    "help": texts.HELP_TEXT,
    "help_chat": texts.HELP_CHAT_TEXT,
    "help_credit": texts.HELP_CREDIT_TEXT,
    "help_gps": texts.HELP_GPS_TEXT,
    "help_profile": texts.HELP_PROFILE_TEXT,
    "help_sendchat": texts.HELP_SENDCHAT_TEXT,
    "help_direct": texts.HELP_DIRECT_TEXT,
    "help_shortcuts": texts.HELP_SHORTCUTS_TEXT,
    "help_onw": texts.HELP_ONW_TEXT,
    "help_chw": texts.HELP_CHW_TEXT,
    "help_contacts": texts.HELP_CONTACTS_TEXT,
    "help_search": texts.HELP_SEARCH_TEXT,
    "help_deleteMessage": texts.HELP_DELETEMSG_TEXT,
}


def _make_help_handler(text_value):
    async def _handler(client, message):
        await client.send_message(message.chat.id, text_value, reply_to_message_id=message.id)
    return _handler


for _cmd_name, _text_value in _HELP_COMMANDS.items():
    bot.on_command(name=_cmd_name, min_arguments=0, max_arguments=0)(_make_help_handler(_text_value))


@bot.on_message(equals("🤔راهنما") & private)
async def msg_help_button(client, message):
    await client.send_message(message.chat.id, texts.HELP_TEXT, reply_to_message_id=message.id)
