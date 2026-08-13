"""
Webhook notification endpoint — sends messages to Telegram.
Auth-exempt (localhost/internal only via firewall).

Delivery hardening
------------------
Telegram's entity parser rejects unbalanced/unterminated Markdown (a stray
``**``, ``_``, ``[`` or a raw error string like ``RangeError: Invalid time
value``) with HTTP 400 ``can't parse entities``. Because dynamic content
(issue titles, error messages, URLs) is interpolated into ``**``-formatted
messages upstream, that failure mode killed *every* dispatcher notification.

To make delivery impossible to break with formatting, ``notify`` now:

  1. Attempts the send with the requested ``parse_mode`` (best-effort
     formatting).
  2. If Telegram returns a 400 entity-parse error, it retries the *same*
     text with ``parse_mode`` stripped (plain text always parses).

The retry guarantees the message is delivered even when the markup is
malformed; only a genuine transport/API failure now surfaces as an error.
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


def _is_entity_parse_error(status: int, body: str) -> bool:
    """True when Telegram rejected the message because of bad markup.

    These are recoverable by resending as plain text. Matches the family of
    400 responses Telegram emits for unbalanced/unterminated entities, e.g.:
        {"ok":false,"error_code":400,
         "description":"Bad Request: can't parse entities: ..."}
    """
    if status != 400:
        return False
    low = body.lower()
    return "can't parse entities" in low or "cant parse entities" in low or "parse entities" in low


async def _send_telegram(session: aiohttp.ClientSession, chat_id: str, text: str,
                         parse_mode: str | None) -> tuple[int, str]:
    """POST sendMessage. parse_mode=None sends plain text. Returns (status, body)."""
    url = f"{TELEGRAM_API}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    if parse_mode:
        data["parse_mode"] = parse_mode
    async with session.post(url, json=data,
                            timeout=aiohttp.ClientTimeout(total=10)) as resp:
        return resp.status, await resp.text()


@router.post("/notify")
async def notify(payload: NotifyPayload):
    """Send a message to a Telegram chat. Internal use by webhook handlers.

    Best-effort formatting with a guaranteed plain-text fallback: a message
    whose markup Telegram can't parse is retried without ``parse_mode`` so a
    formatting bug can never again drop a notification.
    """
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Telegram bot token not configured")

    if not payload.chat_id or not payload.text:
        raise HTTPException(status_code=400, detail="chat_id and text are required")

    try:
        async with aiohttp.ClientSession() as session:
            # 1) Best-effort: honor the requested formatting.
            status, body = await _send_telegram(
                session, payload.chat_id, payload.text, payload.parse_mode or None
            )
            if status == 200:
                logger.info("telegram notify ok (parse_mode=%s): %s",
                            payload.parse_mode or "none", body[:200])
                return {"status": "sent", "chat_id": payload.chat_id}

            # 2) Recoverable formatting failure → retry as plain text.
            if payload.parse_mode and _is_entity_parse_error(status, body):
                logger.warning(
                    "telegram notify 400 entity-parse (parse_mode=%s); retrying plain text: %s",
                    payload.parse_mode, body[:200],
                )
                status2, body2 = await _send_telegram(
                    session, payload.chat_id, payload.text, None
                )
                if status2 == 200:
                    logger.info("telegram notify ok (plain-text retry): %s", body2[:200])
                    return {"status": "sent", "chat_id": payload.chat_id,
                            "fallback": "plain_text"}
                logger.warning("telegram notify plain-text retry failed: %s %s",
                               status2, body2[:200])
                raise HTTPException(status_code=502,
                                    detail=f"Telegram API error: {status2}")

            # 3) Non-recoverable error.
            logger.warning("telegram notify failed: %s %s", status, body[:200])
            raise HTTPException(status_code=502, detail=f"Telegram API error: {status}")
    except aiohttp.ClientError as e:
        logger.warning("telegram notify network error: %s", e)
        raise HTTPException(status_code=502, detail="Telegram API unreachable")
