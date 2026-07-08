"""Telegram Bot service — invite links, ban/unban, send document, send messages."""
import os
import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")

API_BASE = "https://api.telegram.org"


def _placeholder() -> bool:
    return (
        not BOT_TOKEN
        or "placeholder" in BOT_TOKEN.lower()
        or not CHANNEL_ID
        or CHANNEL_ID.startswith("-1000000")
    )


async def _post(method: str, payload: dict) -> dict:
    if _placeholder():
        logger.warning(f"[Telegram MOCK] {method}: {payload}")
        return {"ok": True, "mocked": True, "result": {"invite_link": "https://t.me/+MOCK_INVITE_LINK"}}
    url = f"{API_BASE}/bot{BOT_TOKEN}/{method}"
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.post(url, json=payload)
        data = r.json()
        if not data.get("ok"):
            logger.error(f"Telegram error {method}: {data}")
        return data


async def create_invite_link(name_hint: str = "member") -> Optional[str]:
    """Create a single-use expiring invite link for the channel."""
    data = await _post(
        "createChatInviteLink",
        {
            "chat_id": CHANNEL_ID,
            "name": f"FnOTattva-{name_hint}",
            "member_limit": 1,
            "creates_join_request": False,
        },
    )
    if data.get("mocked"):
        return f"https://t.me/+MOCK_{name_hint.replace(' ', '_')}"
    if data.get("ok"):
        return data["result"]["invite_link"]
    return None


async def ban_user(user_id: str) -> bool:
    if not user_id:
        return False
    data = await _post("banChatMember", {"chat_id": CHANNEL_ID, "user_id": int(user_id)})
    return bool(data.get("ok"))


async def unban_user(user_id: str) -> bool:
    if not user_id:
        return False
    data = await _post(
        "unbanChatMember",
        {"chat_id": CHANNEL_ID, "user_id": int(user_id), "only_if_banned": True},
    )
    return bool(data.get("ok"))


async def send_channel_document(file_path: str, caption: str = "") -> dict:
    """Send a PDF document to the channel."""
    if _placeholder():
        logger.warning(f"[Telegram MOCK] sendDocument: {file_path} caption={caption}")
        return {"ok": True, "mocked": True}
    url = f"{API_BASE}/bot{BOT_TOKEN}/sendDocument"
    async with httpx.AsyncClient(timeout=60.0) as c:
        with open(file_path, "rb") as f:
            files = {"document": (os.path.basename(file_path), f, "application/pdf")}
            data = {"chat_id": CHANNEL_ID, "caption": caption[:1024]}
            r = await c.post(url, data=data, files=files)
            return r.json()


async def send_direct_message(user_id: str, text: str) -> bool:
    """Send a DM to a subscriber (only works if they've DM'd the bot before)."""
    if not user_id:
        return False
    data = await _post("sendMessage", {"chat_id": int(user_id), "text": text, "parse_mode": "HTML"})
    return bool(data.get("ok"))


async def set_webhook(url: str, secret_token: str) -> dict:
    """Register the inbound webhook and subscribe to chat_member updates."""
    if _placeholder():
        logger.warning(f"[Telegram MOCK] setWebhook to {url}")
        return {"ok": True, "mocked": True}
    return await _post(
        "setWebhook",
        {
            "url": url,
            "secret_token": secret_token,
            "allowed_updates": ["chat_member", "my_chat_member", "message"],
            "drop_pending_updates": False,
        },
    )
