"""
تسک‌های دوره‌ای پس‌زمینه.

در نسخه‌ی اصلی این کارها داخل همان حلقه‌ی polling سینک، قبل از هر بار
`getUpdates`، صدا زده می‌شدند (`mm_cleanup_expired()` و
`cleanup_expired_rps_sessions()`). چون بله‌تون خودش polling را مدیریت
می‌کند، این‌ها را به‌صورت یک تسکِ async مستقل (با asyncio.sleep) اجرا
می‌کنیم که توسط `@bot.on_initialize()` در main.py استارت می‌شود.
"""
import asyncio

from handlers.matchmaking import mm_cleanup_expired
from handlers.rps import cleanup_expired_rps_sessions

CLEANUP_INTERVAL_SECONDS = 5


async def attempt_bridge_matchmaking_v2(client):
    import urllib.request
    import json
    from bot_instance import runtime
    import keyboards as kb
    import database as db
    from utils import now_ts, safe_int

    secret = "Hamraz_Bridge_Sec_7f4d92a18b5c3e0964fa1d8e2b7c4a9382f6e501d4cb98e7235a6104bc8f9a2e"
    now = now_ts()

    candidate_uid = None
    for it in list(runtime.get("mm_queue", [])):
        uid = str(it.get("uid") or "")
        st = safe_int(it.get("started_at") or 0, 0)
        if not uid or not st:
            continue
        waiting_time = now - st
        if 45 <= waiting_time <= 110:
            candidate_uid = uid
            break

    if not candidate_uid:
        return

    # Call Hamraz bridge API to pop candidate
    url = f"https://bale.hamrazma.ir/bridge_api.php?action=pop_candidate&caller_uid={candidate_uid}"
    try:
        def _fetch():
            req = urllib.request.Request(url, headers={"X-Bridge-Token": secret})
            with urllib.request.urlopen(req, timeout=4) as resp:
                return json.loads(resp.read().decode("utf-8"))

        data = await asyncio.to_thread(_fetch)
        partner_uid = data.get("partner_uid") or data.get("hamraz_uid")
        if data.get("ok") and partner_uid:
            # Remove from queue
            runtime["mm_queue"] = [x for x in runtime["mm_queue"] if str(x.get("uid")) != str(candidate_uid)]
            u = await db.get_user(candidate_uid, create_if_missing=False)
            if u:
                u["chat_with"] = f"bridge_hamraz_{partner_uid}"
                u["chat_started_at"] = now
                u["mm"] = {"searching": False, "mode": None, "started_at": None, "msg_id": None, "near": False}
                await db.save_user(candidate_uid, u)

                await client.send_message(
                    int(candidate_uid),
                    "✅ مخاطب پیدا شد.\n💬 شما به چت متصل شدید.\n\nبرای مدیریت چت از منوی پایین استفاده کن.",
                    reply_markup=kb.kb_chat_menu()
                )
    except Exception as e:
        pass


async def periodic_cleanup_loop(client):
    while True:
        try:
            await mm_cleanup_expired(client)
        except Exception as e:
            print(f"[background] mm_cleanup_expired error: {e}")
        try:
            await cleanup_expired_rps_sessions(client)
        except Exception as e:
            print(f"[background] cleanup_expired_rps_sessions error: {e}")
        try:
            await attempt_bridge_matchmaking_v2(client)
        except Exception as e:
            print(f"[background] attempt_bridge_matchmaking_v2 error: {e}")
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
