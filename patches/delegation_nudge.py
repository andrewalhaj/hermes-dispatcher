"""
delegation_nudge.py — autonomous parallel-execution nudge for hermes-agent.
===========================================================================

PURPOSE
-------
Fires on the first tool result of each new user message. When 2+ independent
subtasks are detected, injects a strong nudge to call delegate_task immediately
— no proposal, no greenlight needed. WRITE GATE still governs what subagents
execute.

Distinct from kanban_checkpoint.py:
  kanban_checkpoint → ROUTING shape (sequential → kanban, multi-part → propose)
  delegation_nudge  → EXECUTION mode (parallel + independent → delegate NOW)

Unlike kanban_checkpoint, this also fires INSIDE kanban workers: workers with
max_spawn_depth=2 can delegate their own independent subtasks.

SIGNALS (any 1 = fire)
-----------------------
  "plan to"       — explicit trigger phrase ("plan to X and Y")
  2+ URLs         — multiple links to fetch/review in parallel
  X vs Y / X and Y after compare/review/check/analyze
  2+ bullet or numbered list items
  2+ imperative sentences targeting different subjects

DISABLE
-------
  export HERMES_DELEGATION_NUDGE=off

ROLLBACK
--------
Delete this file + remove the block from sitecustomize.py + restart gateway.
"""

from __future__ import annotations

import os
import re
import sys

# ── Tunables ──────────────────────────────────────────────────────────────────

ENABLED = (
    os.environ.get("HERMES_DELEGATION_NUDGE", "on").strip().lower()
    not in {"off", "0", "false", "no", "disabled"}
)

_MARKER = "_delegation_nudge_patched"
_INSTALL_STARTED = False

_NUDGE = (
    "\n\n[Delegation nudge: 2+ independent subtasks detected ({signal}). "
    "Call delegate_task immediately — no proposal, no greenlight. "
    "Fan out in parallel; synthesize results yourself. "
    "WRITE GATE still governs what subagents execute. "
    "Suppressed once delegate_task is called this turn.]"
)

# ── Signal detection ──────────────────────────────────────────────────────────

_URL_RE = re.compile(r"https?://\S+")
_PLAN_TO_RE = re.compile(r"\bplan to\b", re.I)
_COMPARE_RE = re.compile(
    r"\b(compare|review|check|analyze|look at|examine|evaluate|assess)\b"
    r".{0,80}\band\b",
    re.I | re.S,
)
_VS_RE = re.compile(r"\bvs\.?\b|\bversus\b", re.I)


def _detect_signal(text: str) -> str | None:
    """Return signal description if 2+ independent subtasks detected, else None."""
    if not text or len(text.strip()) < 20:
        return None

    # "plan to" — the explicit trigger phrase
    if _PLAN_TO_RE.search(text):
        return '"plan to" trigger'

    # 2+ URLs — always parallel fetch candidates
    urls = _URL_RE.findall(text)
    if len(urls) >= 2:
        return f"{len(urls)} URLs"

    # Comparison / review patterns: "compare X and Y", "X vs Y"
    if _VS_RE.search(text) or _COMPARE_RE.search(text):
        return "comparison/review pattern"

    # 2+ numbered list items
    numbered = re.findall(r"(?:^|\n)\s*\d+[.)]\s+\S", text)
    if len(numbered) >= 2:
        return f"{len(numbered)}-item numbered list"

    # 2+ bullet items
    bullets = re.findall(r"(?:^|\n)\s*[-*\u2022]\s+\S", text)
    if len(bullets) >= 2:
        return f"{len(bullets)}-item bullet list"

    return None


# ── Runtime helpers ───────────────────────────────────────────────────────────

def _delegate_used(assistant_message: object) -> bool:
    """True if delegate_task was already called in this tool batch."""
    try:
        tcs = getattr(assistant_message, "tool_calls", None) or []
        for tc in tcs:
            fn = getattr(tc, "function", None)
            name = getattr(fn, "name", None) or ""
            if name == "delegate_task":
                return True
    except Exception:
        pass
    return False


def _user_turn_index(messages: list) -> int:
    try:
        return sum(
            1 for m in messages
            if isinstance(m, dict) and m.get("role") == "user"
        )
    except Exception:
        return 0


def _last_user_text(messages: list) -> str:
    try:
        for m in reversed(messages):
            if not isinstance(m, dict) or m.get("role") != "user":
                continue
            content = m.get("content", "")
            if isinstance(content, list):
                parts = [
                    p.get("text", "") for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                return " ".join(parts)
            return str(content or "")
    except Exception:
        pass
    return ""


def _append_nudge(messages: list, signal: str) -> bool:
    try:
        for i in range(len(messages) - 1, -1, -1):
            m = messages[i]
            if isinstance(m, dict) and m.get("role") == "tool":
                base = m.get("content")
                base = base if isinstance(base, str) else ("" if base is None else str(base))
                m["content"] = base + _NUDGE.format(signal=signal)
                return True
    except Exception:
        pass
    return False


# ── Wrapper factory ───────────────────────────────────────────────────────────

def _make_wrapper(original: object):
    def _wrapped(self, assistant_message, messages, effective_task_id, api_call_count=0):
        result = original(self, assistant_message, messages, effective_task_id, api_call_count)
        try:
            if not ENABLED:
                return result

            # Suppress if delegate_task already called this batch
            if _delegate_used(assistant_message):
                return result

            # Per-turn guard: fire at most once per user turn
            current_turn = _user_turn_index(messages)
            last_turn = getattr(self, "_deleg_nudge_last_turn", -1)
            if current_turn <= last_turn:
                return result

            # Detect signal
            user_text = _last_user_text(messages)
            signal = _detect_signal(user_text)
            if signal is None:
                return result

            # Fire
            if _append_nudge(messages, signal):
                self._deleg_nudge_last_turn = current_turn
                try:
                    sys.stderr.write(
                        f"[delegation-nudge] fired: signal={signal!r} "
                        f"turn={current_turn} "
                        f"session={getattr(self, 'session_id', '?')}\n"
                    )
                except Exception:
                    pass

        except Exception as exc:
            try:
                sys.stderr.write(
                    f"[delegation-nudge] guard error (no-op): "
                    f"{type(exc).__name__}: {exc}\n"
                )
            except Exception:
                pass
        return result
    return _wrapped


# ── Class patcher ─────────────────────────────────────────────────────────────

def _patch_class(run_agent_module: object) -> bool:
    """Wrap AIAgent._execute_tool_calls. Idempotent."""
    agent_cls = (
        getattr(run_agent_module, "AIAgent", None)
        or getattr(run_agent_module, "RunAgent", None)
    )
    if agent_cls is None:
        sys.stderr.write("[delegation-nudge] agent class not found; skipping\n")
        return False
    if getattr(agent_cls, _MARKER, False):
        return True
    original = getattr(agent_cls, "_execute_tool_calls", None)
    if not callable(original):
        sys.stderr.write("[delegation-nudge] _execute_tool_calls not found; skipping\n")
        return False
    agent_cls._execute_tool_calls = _make_wrapper(original)
    setattr(agent_cls, _MARKER, True)
    sys.stderr.write(f"[delegation-nudge] installed (enabled={ENABLED})\n")
    return True


# ── Public entry point ────────────────────────────────────────────────────────

def apply_patches(run_agent_module: object = None) -> bool:
    """Install the delegation-nudge wrapper. Idempotent."""
    global _INSTALL_STARTED

    if not ENABLED:
        return False

    if run_agent_module is not None:
        return _patch_class(run_agent_module)

    existing = sys.modules.get("run_agent")
    if existing is not None:
        return _patch_class(existing)

    if _INSTALL_STARTED:
        return True
    _INSTALL_STARTED = True

    try:
        from importlib.abc import MetaPathFinder
        from importlib.util import find_spec as _find_spec
    except ImportError:
        sys.stderr.write("[delegation-nudge] importlib unavailable; skipping\n")
        return False

    class _DelegNudgeFinder(MetaPathFinder):
        _done = False

        def find_spec(self, fullname, path=None, target=None):  # type: ignore[override]
            if fullname != "run_agent" or self._done:
                return None
            if self in sys.meta_path:
                sys.meta_path.remove(self)
            try:
                spec = _find_spec(fullname)
            finally:
                if self not in sys.meta_path:
                    sys.meta_path.insert(0, self)
            if spec is None or spec.loader is None:
                return None
            original_exec = getattr(spec.loader, "exec_module", None)
            if not callable(original_exec):
                return None
            finder = self

            def patched_exec(module):  # type: ignore[no-untyped-def]
                original_exec(module)
                finder._done = True
                try:
                    _patch_class(module)
                except Exception as exc:
                    sys.stderr.write(
                        f"[delegation-nudge] deferred patch error (no-op): "
                        f"{type(exc).__name__}: {exc}\n"
                    )

            spec.loader.exec_module = patched_exec  # type: ignore[attr-defined]
            return spec

    sys.meta_path.insert(0, _DelegNudgeFinder())
    return True
