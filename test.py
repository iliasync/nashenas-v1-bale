import database as db
from pyrobale import Client
import asyncio

bot = Client("1133133663:4TNzG3aY6tpYg6QbqSrwGjDDyR-hwxjWepg")

async def main():
    global bot
    await db.init_db()
    for uid, banned in await db.iter_all_user_ids():
        try:
            mes = await bot.get_chat(2065995342)
            print(mes.)
        except Exception as e:
            print(e)

asyncio.run(main())