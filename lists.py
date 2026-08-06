"""رندر و مدیریت لیست‌های مخاطبین / لایک‌ها / بلاک‌شده‌ها."""
import database as db
from utils import last_seen_text

LIST_PAGE_SIZE = 10


def normalize_contacts(user: dict):
    out, seen = [], set()
    for item in (user.get("contacts") or []):
        if isinstance(item, dict):
            pid = str(item.get("pid") or "").strip()
            label = str(item.get("label") or "").strip()
        else:
            pid = str(item).strip()
            label = ""
        if not pid or pid in seen:
            continue
        seen.add(pid)
        out.append({"pid": pid, "label": label})
    user["contacts"] = out


def normalize_simple_list(user: dict, key: str):
    lst = user.get(key) or []
    seen, out = set(), []
    for x in lst:
        sx = str(x).strip()
        if not sx or sx in seen:
            continue
        seen.add(sx)
        out.append(sx)
    user[key] = out


async def _render_user_list_item(idx, target_pid: str, label=None):
    _, tu = await db.get_user_by_public_id(target_pid)
    title = (label or "").strip()
    title_part = f" | {title}" if title else ""
    if not tu:
        return f"{idx}. (کاربر) /user_{target_pid}{title_part}\nنامشخص\n⏳ نامشخص\n"
    age = tu.get("age") or "تعیین نشده"
    prov = tu.get("province") or "تعیین نشده"
    ls = last_seen_text(tu)
    nm = (tu.get("display_name") or "").strip() or "تعیین نشده"
    return f"{idx}. {nm} /user_{target_pid}{title_part}\n{age} {prov}\n⏳ {ls}\n"


async def send_pinnable_text(client, chat_id, text):
    try:
        m = await client.send_message(chat_id, text)
    except Exception as e:
        print(f"send_pinnable_text failed: {e}")
        return
    if m is not None:
        try:
            await client.pin_chat_message(chat_id, m.id)
        except Exception as e:
            print(f"pin_chat_message failed: {e}")


async def send_contacts_list(client, chat_id, user: dict, page=1):
    normalize_contacts(user)
    uniq = user.get("contacts") or []
    await db.save_user(chat_id, user)
    if not uniq:
        await send_pinnable_text(client, chat_id, "مخاطبین ندارید")
        return
    start = (page - 1) * LIST_PAGE_SIZE
    chunk = uniq[start:start + LIST_PAGE_SIZE]
    lines = ["📌 🙎‍♂️🙎‍♀️ لیست مخاطبین شما", ""]
    for i, it in enumerate(chunk, start=start + 1):
        lines.append(await _render_user_list_item(i, it["pid"], it.get("label")))
        lines.append("〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️")
    lines += ["", "🗑 حذف همه مخاطبین : /deleteAllContacts"]
    await send_pinnable_text(client, chat_id, "\n".join(lines))


async def send_my_likes_list(client, chat_id, user: dict, page=1):
    normalize_simple_list(user, "my_likes")
    uniq = user.get("my_likes") or []
    await db.save_user(chat_id, user)
    if not uniq:
        await send_pinnable_text(client, chat_id, "لایک ندارید")
        return
    start = (page - 1) * LIST_PAGE_SIZE
    chunk = uniq[start:start + LIST_PAGE_SIZE]
    lines = ["📌 ❤️ لیست لایک های شما", ""]
    for i, pid in enumerate(chunk, start=start + 1):
        lines.append(await _render_user_list_item(i, pid))
        lines.append("〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️")
    lines += ["", "🗑 حذف همه لایک ها : /deleteAllLikes"]
    await send_pinnable_text(client, chat_id, "\n".join(lines))


async def send_blocked_list(client, chat_id, user: dict, page=1):
    normalize_simple_list(user, "blocked_users")
    uniq = user.get("blocked_users") or []
    await db.save_user(chat_id, user)
    if not uniq:
        await send_pinnable_text(client, chat_id, "بلاک شده ندارید")
        return
    start = (page - 1) * LIST_PAGE_SIZE
    chunk = uniq[start:start + LIST_PAGE_SIZE]
    lines = ["📌 🚫 لیست بلاک شده های شما", ""]
    for i, pid in enumerate(chunk, start=start + 1):
        lines.append(await _render_user_list_item(i, pid))
        lines.append("〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️")
    lines += ["", "🧹 رفع بلاک همه : /unblockAll", "🗑 حذف همه بلاک ها : /deleteAllBlocked"]
    await send_pinnable_text(client, chat_id, "\n".join(lines))
