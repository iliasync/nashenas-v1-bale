"""Helpers for building bot deep links from the runtime bot identity."""
import inspect

import config


def _clean_username(username: str) -> str:
    username = (username or "").strip()
    if username.startswith("@"):
        username = username[1:]
    if username.startswith("https://ble.ir/"):
        username = username.removeprefix("https://ble.ir/").split("?", 1)[0].strip("/")
    if username.startswith("ble.ir/"):
        username = username.removeprefix("ble.ir/").split("?", 1)[0].strip("/")
    if username.startswith("@"):
        username = username[1:]
    return username.strip("/")


async def get_bot_username(client) -> str:
    """Prefer get_me/getMe so deep links use the actual running bot username."""
    bot_user = None
    for method_name in ("get_me", "getMe", "get_me_"):
        method = getattr(client, method_name, None)
        if callable(method):
            try:
                result = method()
                bot_user = await result if inspect.isawaitable(result) else result
                break
            except Exception:
                bot_user = None
    if bot_user is None:
        bot_user = getattr(client, "user", None)

    if isinstance(bot_user, dict):
        raw_username = bot_user.get("username") or ""
    else:
        raw_username = getattr(bot_user, "username", "") or ""
    username = _clean_username(raw_username)
    if username:
        return username
    return _clean_username(getattr(config, "BOT_USERNAME_FALLBACK", "") or "")


async def build_start_link(client, payload: str) -> str:
    payload = (payload or "").strip()
    username = await get_bot_username(client)
    if username:
        return f"https://ble.ir/{username}?start={payload}"
    return f"/start {payload}"
