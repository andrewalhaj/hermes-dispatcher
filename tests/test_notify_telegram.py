"""Tests for routes/notify.py Telegram delivery hardening.

Proves the entity-parse 400 failure mode (unbalanced **, _, [, raw error
strings like "RangeError: Invalid time value") can no longer drop a
notification: a 400 "can't parse entities" triggers a plain-text retry.

The Telegram network call (routes.notify._send_telegram) is monkeypatched, so
no test touches the real Telegram API or reads TELEGRAM_BOT_TOKEN.

Runner-agnostic: plain unittest.TestCase (runs under pytest and stdlib).
"""
import asyncio
import os
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# A token must be present for notify() to attempt a send (value is never used
# because the network layer is mocked).
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-not-real")

import routes.notify as notify  # noqa: E402

# Telegram's real 400 body when markup is malformed.
_ENTITY_400 = (
    '{"ok":false,"error_code":400,"description":'
    '"Bad Request: can\'t parse entities: '
    'Can\'t find end of the entity starting at byte offset 127"}'
)
_OK_200 = '{"ok":true,"result":{"message_id":42}}'

# A payload full of the exact hazards from the acceptance criteria.
HAZARD_TEXT = (
    "\u274c **Sentry — payments\n"
    "RangeError: Invalid time value in [handler_\n"
    "value = arr[unterminated"
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _FakeSession:
    """Stand-in for aiohttp.ClientSession as an async context manager."""
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class TelegramNotifyHardeningTest(unittest.TestCase):
    def setUp(self):
        self.calls = []  # (parse_mode, text) per _send_telegram invocation
        self._orig_send = notify._send_telegram
        self._orig_sess = notify.aiohttp.ClientSession

        # Replace ClientSession with a no-op async context manager.
        notify.aiohttp.ClientSession = lambda *a, **k: _FakeSession()

    def tearDown(self):
        notify._send_telegram = self._orig_send
        notify.aiohttp.ClientSession = self._orig_sess

    def _install_send(self, script):
        """script: callable(parse_mode) -> (status, body)."""
        async def fake_send(session, chat_id, text, parse_mode):
            self.calls.append((parse_mode, text))
            return script(parse_mode)
        notify._send_telegram = fake_send

    def _notify(self, text, parse_mode="Markdown"):
        payload = notify.NotifyPayload(chat_id="123", text=text, parse_mode=parse_mode)
        return _run(notify.notify(payload))

    # --- Acceptance criterion 1: malformed markup never surfaces a 400 -------

    def test_entity_400_retries_plain_text_and_succeeds(self):
        """Markdown send 400s on bad entities → plain-text retry succeeds."""
        def script(parse_mode):
            if parse_mode == "Markdown":
                return (400, _ENTITY_400)
            return (200, _OK_200)  # plain-text retry
        self._install_send(script)

        result = self._notify(HAZARD_TEXT)

        self.assertEqual(result["status"], "sent")
        self.assertEqual(result.get("fallback"), "plain_text")
        # First attempt with Markdown, second with parse_mode stripped.
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[0][0], "Markdown")
        self.assertIsNone(self.calls[1][0])
        # The full text (including hazards) was preserved on the retry.
        self.assertEqual(self.calls[1][1], HAZARD_TEXT)

    def test_clean_markdown_sends_once_no_retry(self):
        """A well-formed message sends on the first try, no fallback."""
        self._install_send(lambda pm: (200, _OK_200))
        result = self._notify("*bold* done")
        self.assertEqual(result["status"], "sent")
        self.assertNotIn("fallback", result)
        self.assertEqual(len(self.calls), 1)

    def test_non_entity_400_does_not_retry(self):
        """A 400 that is NOT an entity-parse error surfaces as an error."""
        self._install_send(lambda pm: (400, '{"ok":false,"description":"Bad Request: chat not found"}'))
        with self.assertRaises(notify.HTTPException) as ctx:
            self._notify(HAZARD_TEXT)
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertEqual(len(self.calls), 1)  # no retry

    def test_plain_text_request_no_double_send(self):
        """parse_mode='' (plain) that 400s does not loop into a retry."""
        self._install_send(lambda pm: (400, _ENTITY_400))
        with self.assertRaises(notify.HTTPException):
            self._notify(HAZARD_TEXT, parse_mode="")
        self.assertEqual(len(self.calls), 1)

    # --- entity-error classifier ------------------------------------------

    def test_is_entity_parse_error_matches(self):
        self.assertTrue(notify._is_entity_parse_error(400, _ENTITY_400))
        self.assertFalse(notify._is_entity_parse_error(400, '{"description":"chat not found"}'))
        self.assertFalse(notify._is_entity_parse_error(200, _OK_200))
        self.assertFalse(notify._is_entity_parse_error(500, "internal"))


if __name__ == "__main__":
    unittest.main()
