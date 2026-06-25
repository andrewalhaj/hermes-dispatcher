"""
kanban_phase_checkpoint.py — multi-phase task routing nudge for hermes-agent.
==============================================================================

PURPOSE
-------
Scores each incoming user message for multi-phase / multi-system complexity.
When the score crosses PHASE_SCORE_MIN, injects a one-time routing reminder
into the live tool-result stream BEFORE the agent continues, so it sees the
gate at the start of its next reasoning step rather than after it's already
executed.

SCORING HEURISTICS (no LLM, pure regex/heuristic, ~0ms)
---------------------------------------------------------
Signal                                      Points
------                                      ------
3+ numbered/bulleted steps                  +3
2 numbered steps                            +1
Sequential conjunctions (then/next/etc.)    +1 each (cap +2)
Phase vocabulary (phase/stage/step/etc.)    +1 each (cap +2)
3+ distinct systems/paths/services          +2
2  distinct systems/paths/services          +1
Message > 300 words                         +1

Fires when score >= PHASE_SCORE_MIN (default 3) on a NEW user turn.
Does NOT re-fire on the same user message (tracked by first-100-char hash).

OVERRIDE (inline bypass)
------------------------
If the user's message contains any of: "inline", "do it now", "just go",
"just do it", "quick" — the nudge is suppressed for that turn.

DISABLE
-------
  export HERMES_KANBAN_PHASE=off

ROLLBACK
--------
Delete this file + remove the chain block from anthropic_billing_bypass.py
+ remove block from sitecustomize.py + restart gateway.
"""

from __future__ import annotations

import os
import re
import sys


# ── Tunables ─────────────────────────────────────────────────────────────────

PHASE_SCORE_MIN = int(os.environ.get("HERMES_KANBAN_PHASE_MIN", "3").strip() or "3")

ENABLED = os.environ.get(
    "HERMES_KANBAN_PHASE", "on"
).strip().lower() not in {"off", "0", "false", "no", "disabled"}

_MARKER = "_kanban_phase_patched"
_INSTALL_STARTED = False

_BYPASS_PHRASES = ["inline", "do it now", "just go", "just do it", "quick fix", "quickly"]

_NUDGE = (
    "\n\n[KANBAN ROUTING GATE — multi-phase task detected (complexity score: {score}/10,"
    " signals: {signals}).\n"
    "Before executing inline, apply the 3-question check:\n"
    "  1. 3+ sequential phases where each depends on the previous?\n"
    "  2. Touches 3+ distinct systems / files / services?\n"
    "  3. Estimated >10 minutes end-to-end?\n"
    "ALL YES → call kanban_create() with a full spec + phase breakdown, tell the user"
    " the card ID, then STOP. The worker picks it up.\n"
    "ANY NO, or this is a tight interactive follow-up → state why inline in one line,"
    " then proceed.\n"
    "Add 'inline' anywhere in your reply to suppress this gate on quick follow-ups.]"
)


# ── Scoring ───────────────────────────────────────────────────────────────────

_SEQ_WORDS = [
    "then ", "after that", "next ", "finally ", "also need", "and then",
    "followed by", "once that", "subsequently", "afterward",
]

_PHASE_WORDS = [
    r"\bphase\b", r"\bstages?\b", r"\bsteps?\b", r"\bparts?\b",
    r"\bfirst\b.{1,40}\bthen\b", r"\bmultiple\b", r"\bseveral\b",
]

_SYSTEM_PATTERNS = [
    r"/[\w.\-]+/[\w.\-/]+\.(?:py|yaml|yml|json|sh|md|conf|toml|env|cfg)",  # file paths
    r"\b(?:systemctl|docker|nginx|postgres|redis|sqlite|kanban|gateway|"
    r"hermes|uvicorn|gunicorn|caddy|cloudflare|tailscale)\b",               # services
    r"https?://\S{6,}",                                                      # URLs
    r"\b(?:deploy|migrate|restart|rebuild|provision|install|configure)\b",  # ops verbs
]


def _score_multiphase(text: str) -> tuple[int, list[str]]:
    """Return (score, [signal descriptions]) for a user message."""
    score = 0
    signals: list[str] = []
    t = text.lower()

    # Numbered / bulleted steps
    numbered = len(re.findall(r"(?:^|\n)\s*(?:\d+[\.\)]|[-*•])\s+\w", text, re.MULTILINE))
    if numbered >= 3:
        score += 3; signals.append(f"{numbered} list items")
    elif numbered == 2:
        score += 1; signals.append("2 list items")

    # Sequential conjunctions
    seq_count = sum(1 for w in _SEQ_WORDS if w in t)
    added = min(seq_count, 2)
    if added:
        score += added; signals.append(f"{seq_count} sequential connectors")

    # Phase vocabulary
    phase_hits = [p for p in _PHASE_WORDS if re.search(p, t)]
    added = min(len(phase_hits), 2)
    if added:
        score += added; signals.append("phase vocabulary")

    # System breadth
    systems: set[str] = set()
    for pat in _SYSTEM_PATTERNS:
        for m in re.finditer(pat, t):
            systems.add(m.group(0)[:30])
    if len(systems) >= 3:
        score += 2; signals.append(f"{len(systems)} systems/services")
    elif len(systems) == 2:
        score += 1; signals.append("2 systems/services")

    # Message length
    word_count = len(text.split())
    if word_count > 300:
        score += 1; signals.append(f"{word_count} words")

    # Comma-chained action verbs (e.g. "refactor X, update Y, restart Z, test…")
    action_clauses = re.findall(
        r"\b(?:refactor|update|restart|rebuild|migrate|deploy|configure|"
        r"install|patch|test|verify|write|create|add|remove|fix|setup|"
        r"wire|connect|integrate)\b",
        t,
    )
    if len(action_clauses) >= 4:
        score += 2; signals.append(f"{len(action_clauses)} chained actions")
    elif len(action_clauses) == 3:
        score += 1; signals.append(f"3 chained actions")

    return score, signals


def _get_last_user_message(messages: list) -> str:
    """Extract text content of the most recent user message."""
    try:
        for m in reversed(messages):
            role = m.get("role") if isinstance(m, dict) else getattr(m, "role", None)
            if role != "user":
                continue
            content = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        return block.get("text", "")
    except Exception:
        pass
    return ""


def _has_bypass(text: str) -> bool:
    t = text.lower()
    return any(p in t for p in _BYPASS_PHRASES)


def _append_nudge(messages: list, score: int, signals: list[str]) -> bool:
    """Append nudge to the last tool-result message. Returns True if appended."""
    try:
        for i in range(len(messages) - 1, -1, -1):
            m = messages[i]
            if isinstance(m, dict) and m.get("role") == "tool":
                base = m.get("content", "") or ""
                if not isinstance(base, str):
                    base = str(base)
                m["content"] = base + _NUDGE.format(
                    score=score,
                    signals=", ".join(signals) if signals else "general complexity",
                )
                return True
    except Exception:
        pass
    return False


# ── Wrapper ───────────────────────────────────────────────────────────────────

def _make_wrapper(original: object):
    def _wrapped(self, assistant_message, messages, effective_task_id, api_call_count=0):
        result = original(self, assistant_message, messages, effective_task_id, api_call_count)
        try:
            if not ENABLED:
                return result

            # Extract current user message
            user_msg = _get_last_user_message(messages)
            if not user_msg:
                return result

            # Deduplicate — only fire once per unique user turn
            msg_key = user_msg[:100]
            last_key = getattr(self, "_kanban_phase_last_key", None)
            if msg_key == last_key:
                return result
            self._kanban_phase_last_key = msg_key

            # Bypass check
            if _has_bypass(user_msg):
                return result

            # Score
            score, signals = _score_multiphase(user_msg)
            if score < PHASE_SCORE_MIN:
                return result

            # Fire nudge
            if _append_nudge(messages, score, signals):
                try:
                    sys.stderr.write(
                        f"[kanban-phase-checkpoint] fired: score={score} "
                        f"signals={signals} "
                        f"session={getattr(self, 'session_id', '?')}\n"
                    )
                except Exception:
                    pass

        except Exception as exc:
            try:
                sys.stderr.write(
                    f"[kanban-phase-checkpoint] guard error (no-op): "
                    f"{type(exc).__name__}: {exc}\n"
                )
            except Exception:
                pass
        return result
    return _wrapped


# ── Install ───────────────────────────────────────────────────────────────────

def _patch_class(run_agent_module: object) -> bool:
    agent_cls = (
        getattr(run_agent_module, "AIAgent", None)
        or getattr(run_agent_module, "RunAgent", None)
    )
    if agent_cls is None:
        sys.stderr.write("[kanban-phase-checkpoint] agent class not found; skipping\n")
        return False
    if getattr(agent_cls, _MARKER, False):
        return True  # already wrapped
    original = getattr(agent_cls, "_execute_tool_calls", None)
    if not callable(original):
        sys.stderr.write("[kanban-phase-checkpoint] _execute_tool_calls not found; skipping\n")
        return False
    agent_cls._execute_tool_calls = _make_wrapper(original)
    setattr(agent_cls, _MARKER, True)
    sys.stderr.write(
        f"[kanban-phase-checkpoint] installed "
        f"(score_min={PHASE_SCORE_MIN}, enabled={ENABLED})\n"
    )
    return True


def apply_patches(run_agent_module: object = None) -> bool:
    """Install the kanban-phase-checkpoint wrapper. Idempotent."""
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
        sys.stderr.write("[kanban-phase-checkpoint] importlib unavailable; skipping\n")
        return False

    class _KanbanPhaseFinder(MetaPathFinder):
        _done = False

        def find_spec(self, fullname, path=None, target=None):  # type: ignore[override]
            if fullname != "run_agent" or self._done:
                return None
            if self in sys.meta_path:
                sys.meta_path.remove(self)
            try:
                spec = _find_spec(fullname)
            finally:
                self._done = True
            if spec is None:
                return None
            orig_exec = spec.loader.exec_module

            def _exec_and_patch(module):
                orig_exec(module)
                _patch_class(module)

            spec.loader.exec_module = _exec_and_patch
            return spec

    sys.meta_path.insert(0, _KanbanPhaseFinder())
    return True


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    tests = [
        "Can you update the webui?",
        "Can you 1. patch the server 2. restart the service 3. verify it works and then update the kanban board?",
        "Set up the new docker stack: first migrate the database, then rebuild the image, deploy to prod, configure nginx, and update cloudflare DNS.",
        "Fix that bug inline",
        "Refactor the galaxy component, update the API endpoint, restart hermes-webui, test in browser, and write a skill doc for this pattern.",
    ]
    for t in tests:
        score, sigs = _score_multiphase(t)
        bypass = _has_bypass(t)
        fires = score >= PHASE_SCORE_MIN and not bypass
        print(f"score={score:2d} fires={fires} bypass={bypass} | {t[:70]}")
        if sigs:
            print(f"         signals: {', '.join(sigs)}")
