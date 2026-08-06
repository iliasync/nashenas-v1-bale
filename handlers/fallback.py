"""فال‌بک نهایی. این ماژول باید آخرین importِ handlers/__init__.py باشد."""
from balethon.conditions import equals,private

import keyboards as kb
from bot_instance import bot


@bot.on_message(equals("بازگشت 🔙") & private)
async def msg_generic_back(client, message):
    await client.send_message(
        message.chat.id, "بازگشت به منوی اصلی.", reply_markup=kb.kb_main_menu(), reply_to_message_id=message.id
    )
