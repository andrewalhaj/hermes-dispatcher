"""
Webhook notification endpoint — sends messages to Telegram.
Auth-exempt (localhost/internal only via firewall).
"""

import os
import logging
import aiohttp
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/hooks")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API = "https://api.telegram.org"


class NotifyPayload(BaseModel):
    chat_id: str
    text: str
    parse_mode: str = "Markdown"


@router.post("/notify")
async def notify(payload: NotifyPayload):
    """Send a message to a Telegram chat. Internal use by webhook handlers."""
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Telegram bot token not configured")

    if not payload.chat_id or not payload.text:
        raise HTTPException(status_code=400, detail="chat_id and text are required")

    url = f"{TELEGRAM_API}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": payload.chat_id,
        "text": payload.text,
        "parse_mode": payload.parse_mode,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                body = await resp.text()
                if resp.status != 200:
                    logger.warning("telegram notify failed: %s %s", resp.status, body[:200])
                    raise HTTPException(status_code=502, detail=f"Telegram API error: {resp.status}")
                return {"status": "sent", "chat_id": payload.chat_id}
    except aiohttp.ClientError as e:
        logger.warning("telegram notify network error: %s", e)
        raise HTTPException(status_code=502, detail="Telegram API unreachable")
