"""دریافت فایل خروجیِ پروفایل (JSON / TEXT / HTML)."""
import json as json_lib
import os
import tempfile
from datetime import datetime

from balethon.conditions import regex,private

import database as db
import keyboards as kb
from bot_instance import bot
from filters import get_event_user
from utils import normalize_gender_text, last_seen_text, distance_text, safe_int


def clean_user_for_export(uid_str, u: dict) -> dict:
    gps = u.get("gps") or {}
    return {
        "uid": str(uid_str),
        "public_id": u.get("public_id"),
        "display_name": u.get("display_name"),
        "gender": u.get("gender"),
        "age": u.get("age"),
        "province": u.get("province"),
        "city": u.get("city"),
        "likes": safe_int(u.get("likes", 0), 0),
        "last_seen": u.get("last_seen"),
        "created_at": u.get("created_at"),
        "gps": {"lat": gps.get("lat"), "lon": gps.get("lon"), "set_at": gps.get("set_at")},
    }


def export_text_block(target_uid_str, target_user: dict) -> str:
    e = clean_user_for_export(target_uid_str, target_user)
    lines = [
        "📄 پروفایل کاربر (TEXT)", "",
        f"public_id: {e.get('public_id')}",
        f"name: {e.get('display_name')}",
        f"gender: {e.get('gender')}",
        f"age: {e.get('age')}",
        f"province: {e.get('province')}",
        f"city: {e.get('city')}",
        f"likes: {e.get('likes')}",
        f"last_seen: {e.get('last_seen')}",
        f"created_at: {e.get('created_at')}",
        f"gps.lat: {e.get('gps', {}).get('lat')}",
        f"gps.lon: {e.get('gps', {}).get('lon')}",
    ]
    return "\n".join(lines)


def export_html_content(viewer_user: dict, target_user: dict) -> str:
    vname = (viewer_user.get("display_name") or "—")
    tname = (target_user.get("display_name") or "—")
    tpid = (target_user.get("public_id") or "—")
    vpid = (viewer_user.get("public_id") or "—")
    tprov = (target_user.get("province") or "—")
    tcity = (target_user.get("city") or "—")
    tage = (target_user.get("age") or "—")
    tgender = normalize_gender_text(target_user)
    tlikes = safe_int(target_user.get("likes", 0), 0)
    tlast = last_seen_text(target_user).replace("*", "")
    dist = distance_text(viewer_user, target_user)

    html = f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>zone - Profile</title>
<style>
  body {{
    margin:0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Tahoma, Arial, sans-serif;
    background: radial-gradient(1200px 600px at 10% 10%, #0b2a5b 0%, rgba(11,42,91,0) 55%),
                radial-gradient(900px 500px at 90% 20%, #4b1a8a 0%, rgba(75,26,138,0) 55%),
                linear-gradient(180deg, #070a12 0%, #0b1020 100%);
    color:#eaf1ff;
  }}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 28px 16px 60px; }}
  .brand {{
    display:flex; align-items:center; justify-content:space-between;
    gap:12px; margin-bottom:18px;
  }}
  .logo {{
    font-weight: 800; letter-spacing: .2px;
    font-size: 22px; color: #fff;
  }}
  .tag {{ font-size: 12px; opacity:.8; }}
  .grid {{ display:grid; grid-template-columns: 1.1fr .9fr; gap:16px; }}
  @media (max-width: 820px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  .card {{
    background: rgba(255,255,255,.06);
    border: 1px solid rgba(255,255,255,.10);
    border-radius: 18px;
    backdrop-filter: blur(10px);
    overflow:hidden;
  }}
  .head {{
    padding:16px 18px;
    background: linear-gradient(90deg, rgba(95,180,255,.18), rgba(210,118,255,.14));
    border-bottom: 1px solid rgba(255,255,255,.10);
  }}
  .head h2 {{ margin:0; font-size: 18px; }}
  .head .sub {{ margin-top:6px; font-size: 12px; opacity:.85; }}
  .body {{ padding: 16px 18px 18px; }}
  .kv {{ display:grid; grid-template-columns: 160px 1fr; gap:10px; }}
  .k {{ opacity:.8; }}
  .v {{ font-weight: 700; }}
  .pill {{
    display:inline-block; padding:6px 10px; border-radius:999px;
    background: rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.12);
    font-size:12px; margin-inline-end: 6px;
  }}
  .footer {{
    margin-top: 18px; font-size: 12px; opacity:.8;
  }}
  .glow {{
    position:fixed; inset:-200px;
    background: radial-gradient(650px 350px at 50% 0%, rgba(120,240,255,.10), rgba(0,0,0,0) 60%);
    pointer-events:none;
  }}
</style>
</head>
<body>
<div class="glow"></div>
<div class="wrap">
  <div class="brand">
    <div>
      <div class="logo"> زون  • zone</div>
      <div class="tag">نمایش وب پروفایل (Export HTML)</div>
    </div>
    <div class="tag">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="head">
        <h2>پروفایل کاربر</h2>
        <div class="sub">🆔 /user_{tpid}</div>
      </div>
      <div class="body">
        <div class="kv">
          <div class="k">نام</div><div class="v">{tname}</div>
          <div class="k">جنسیت</div><div class="v">{tgender}</div>
          <div class="k">سن</div><div class="v">{tage}</div>
          <div class="k">استان</div><div class="v">{tprov}</div>
          <div class="k">شهر</div><div class="v">{tcity}</div>
          <div class="k">لایک‌ها</div><div class="v">❤️ {tlikes}</div>
          <div class="k">آخرین بازدید</div><div class="v">{tlast}</div>
          <div class="k">فاصله از شما</div><div class="v">🏁 {dist}</div>
        </div>
        <div class="footer">
          <span class="pill">Export: HTML</span>
          <span class="pill">App:  زون </span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="head">
        <h2>نمایشگر (شما)</h2>
        <div class="sub">🆔 /user_{vpid}</div>
      </div>
      <div class="body">
        <div class="kv">
          <div class="k">نام شما</div><div class="v">{vname}</div>
          <div class="k">GPS شما</div><div class="v">{'✅ ثبت شده' if (viewer_user.get('gps') or {}).get('lat') is not None else '❌ ثبت نشده'}</div>
        </div>
        <div class="footer">
          این فایل برای نمایش زیبا ساخته شده است.
        </div>
      </div>
    </div>
  </div>
</div>
</body>
</html>"""
    return html


def write_temp_file(s: str, suffix: str) -> str:
    fd, path = tempfile.mkstemp(prefix="zsone_", suffix=suffix)
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write(s)
    return path


@bot.on_callback_query(regex(r"^export_menu:") & private)
async def cb_export_menu(client, callback_query):
    pid = callback_query.data.split(":", 1)[1].strip()
    await callback_query.answer(None)
    await client.send_message(
        callback_query.message.chat.id,
        "🪗 *دریافت فایل پروفایل*\n\nفرمت خروجی را انتخاب کن 👇",
        reply_markup=kb.ikb_export_menu(pid),
        reply_to_message_id=callback_query.message.id,
    )


@bot.on_callback_query(regex(r"^export_json:") & private)
async def cb_export_json(client, callback_query):
    pid = callback_query.data.split(":", 1)[1].strip()
    await callback_query.answer(None)
    chat_id = callback_query.message.chat.id
    target_uid, target_user = await db.get_user_by_public_id(pid)
    if not target_user:
        await client.send_message(chat_id, "⚠️ کاربر پیدا نشد.")
        return
    payload = clean_user_for_export(target_uid, target_user)
    path = write_temp_file(json_lib.dumps(payload, ensure_ascii=False, indent=2), ".json")
    try:
        await client.send_document(chat_id, path, caption=f"📦 خروجی JSON پروفایل /user_{pid}")
    except Exception as e:
        print(f"export_json failed: {e}")
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


@bot.on_callback_query(regex(r"^export_text:") & private)
async def cb_export_text(client, callback_query):
    pid = callback_query.data.split(":", 1)[1].strip()
    await callback_query.answer(None)
    chat_id = callback_query.message.chat.id
    target_uid, target_user = await db.get_user_by_public_id(pid)
    if not target_user:
        await client.send_message(chat_id, "⚠️ کاربر پیدا نشد.")
        return
    content = export_text_block(target_uid, target_user)
    path = write_temp_file(content, ".txt")
    try:
        await client.send_document(chat_id, path, caption=f"📄 خروجی TEXT پروفایل /user_{pid}")
    except Exception as e:
        print(f"export_text failed: {e}")
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


@bot.on_callback_query(regex(r"^export_html:") & private)
async def cb_export_html(client, callback_query):
    pid = callback_query.data.split(":", 1)[1].strip()
    await callback_query.answer(None)
    chat_id = callback_query.message.chat.id
    viewer = await get_event_user(callback_query)
    target_uid, target_user = await db.get_user_by_public_id(pid)
    if not target_user:
        await client.send_message(chat_id, "⚠️ کاربر پیدا نشد.")
        return
    html = export_html_content(viewer, target_user)
    path = write_temp_file(html, ".html")
    try:
        await client.send_document(chat_id, path, caption=f"🌐 خروجی HTML پروفایل /user_{pid}\n(فایل را باز کن)")
    except Exception as e:
        print(f"export_html failed: {e}")
    finally:
        try:
            os.remove(path)
        except Exception:
            pass
