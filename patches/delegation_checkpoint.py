"""
delegation_checkpoint.py — per-session delegation nudge for hermes-agent.
==========================================================================

PURPOSE
-------
The Daily Delegation Audit has reported 5+ consecutive days of zero effective
delegation in sessions with large token spend. This module injects a ONE-TIME,
per-session system-reminder into the live tool loop when a session crosses
delegation-worthy thresholds with zero delegate_task calls.

ARCHITECTURE (Option A)
-----------------------
Standalone module in ~/.hermes/patches/. Two load paths:
  1. sitecustomize.py calls apply_patches() at Python startup — provider-
     independent, fires before any agent/provider code loads.
  2. anthropic_billing_bypass.apply_patches() chains into this — belt-and-
     suspenders for the Anthropic path.

Both paths are idempotent: module-level _INSTALL_STARTED prevents double-
arming; AIAgent._MARKER prevents double-wrapping the class method.

THRESHOLDS (tunable via env vars)
---------
Fires once when ALL hold within a session:
  - cumulative `terminal` tool calls     >= HERMES_DELEG_TERMINAL_MIN (50)
  - current context size (prompt tokens) >= HERMES_DELEG_TOKEN_MIN   (80000)
  - cumulative `delegate_task` calls     == 0

DISABLE
-------
  export HERMES_DELEG_CHECKPOINT=off

ROLLBACK
--------
Delete this file + remove chain line from anthropic_billing_bypass.py +
remove block from sitecustomize.py + restart gateway.
"""

from __future__ import annotations

import os
import sys


# ── Tunables ─────────────────────────────────────────────────────────────────

def _int_env(name: str, default: int) -> int:
    try:
        v = int(os.environ.get(name, "").strip())
        return v if v >= 0 else default
    except (TypeError, ValueError):
        return default


TERMINAL_MIN = _int_env("HERMES_DELEG_TERMINAL_MIN", 30)
TOKEN_MIN = _int_env("HERMES_DELEG_TOKEN_MIN", 80_000)
WRITE_MIN = _int_env("HERMES_DELEG_WRITE_MIN", 6)
ENABLED = os.environ.get(
    "HERMES_DELEG_CHECKPOINT", "on"
).strip().lower() not in {"off", "0", "false", "no", "disabled"}

_MARKER = "_deleg_checkpoint_patched"
_INSTALL_STARTED = False  # prevents arming two deferred finders

_NUDGE = (
    "\n\n[Delegation checkpoint: this session has run {terminal} terminal "
    "call(s) and {writes} file write/patch call(s) across a {tokens:,}-token "
    "context with zero delegate_task calls. "
    "Per the delegation protocol, before continuing, evaluate whether any "
    "remaining INDEPENDENT workstreams (multi-system probing, repeated "
    "diagnostic loops, parallel setup tasks) or large file authoring should "
    "be carved into a delegate_task — the orchestrator reviews diffs, it does "
    "not author them inline. If the remaining work is genuinely sequential "
    "and un-delegatable, state that briefly and proceed. This reminder fires "
    "once per session.]"
)


# ── Runtime helpers ──────────────────────────────────────────────────────────

def _count(assistant_message: object, name: str) -> int:
    try:
        tcs = getattr(assistant_message, "tool_calls", None) or []
        return sum(
            1 for tc in tcs
            if getattr(getattr(tc, "function", None), "name", None) == name
        )
    except Exception:
        return 0


def _context_tokens(agent: object) -> int:
    try:
        comp = getattr(agent, "context_compressor", None)
        val = getattr(comp, "last_prompt_tokens", 0) or 0
        return int(val) if val and val > 0 else 0
    except Exception:
        return 0


def _append_nudge(messages: list, terminal: int, writes: int, tokens: int) -> bool:
    try:
        for i in range(len(messages) - 1, -1, -1):
            m = messages[i]
            if isinstance(m, dict) and m.get("role") == "tool":
                base = m.get("content")
                base = base if isinstance(base, str) else (
                    "" if base is None else str(base)
                )
                m["content"] = base + _NUDGE.format(
                    terminal=terminal, writes=writes, tokens=tokens
                )
                return True
    except Exception:
        pass
    return False


def _make_wrapper(original: object):
    def _wrapped(self, assistant_message, messages, effective_task_id, api_call_count=0):
        result = original(self, assistant_message, messages, effective_task_id, api_call_count)
        try:
            if not ENABLED:
                return result

            term = getattr(self, "_deleg_ckpt_terminal", 0) + _count(assistant_message, "terminal")
            self._deleg_ckpt_terminal = term

            writes = (
                getattr(self, "_deleg_ckpt_writes", 0)
                + _count(assistant_message, "write_file")
                + _count(assistant_message, "patch")
            )
            self._deleg_ckpt_writes = writes

            deleg = getattr(self, "_deleg_ckpt_delegate", 0) + _count(assistant_message, "delegate_task")
            self._deleg_ckpt_delegate = deleg

            if deleg > 0:
                return result

            # Re-firing watermark (hardened 2026-06-09): fire at first
            # threshold cross, then RE-FIRE every WRITE_MIN further writes
            # while delegation remains zero. fired_at_writes records the
            # write-count at last fire.
            fired_at = getattr(self, "_deleg_ckpt_fired_at_writes", None)

            tokens = _context_tokens(self)
            # Two independent triggers (fire on EITHER):
            #  A. terminal-grind in a large live context (diagnostic/build loops)
            #  B. inline file authoring volume — the output-token bill that a
            #     small-context session hides (write_file + patch >= WRITE_MIN)
            trigger_a = term >= TERMINAL_MIN and tokens >= TOKEN_MIN
            trigger_b = writes >= WRITE_MIN
            first_fire = fired_at is None and (trigger_a or trigger_b)
            refire = fired_at is not None and writes >= fired_at + WRITE_MIN
            if first_fire or refire:
                if _append_nudge(messages, term, writes, tokens):
                    self._deleg_ckpt_fired = True
                    self._deleg_ckpt_fired_at_writes = writes
                    try:
                        sys.stderr.write(
                            f"[delegation-checkpoint] fired: terminal={term} "
                            f"writes={writes} context_tokens={tokens} "
                            f"trigger={'A' if trigger_a else 'B'} session="
                            f"{getattr(self, 'session_id', '?')}\n"
                        )
                    except Exception:
                        pass
        except Exception as exc:
            try:
                sys.stderr.write(
                    f"[delegation-checkpoint] guard error (no-op): "
                    f"{type(exc).__name__}: {exc}\n"
                )
            except Exception:
                pass
        return result
    return _wrapped


def _patch_class(run_agent_module: object) -> bool:
    """Wrap AIAgent._execute_tool_calls on the given module. Idempotent."""
    agent_cls = (
        getattr(run_agent_module, "AIAgent", None)
        or getattr(run_agent_module, "RunAgent", None)
    )
    if agent_cls is None:
        sys.stderr.write(
            "[delegation-checkpoint] agent class (AIAgent/RunAgent) not found; skipping\n"
        )
        return False
    if getattr(agent_cls, _MARKER, False):
        return True  # already wrapped
    original = getattr(agent_cls, "_execute_tool_calls", None)
    if not callable(original):
        sys.stderr.write(
            "[delegation-checkpoint] _execute_tool_calls not found; skipping\n"
        )
        return False
    agent_cls._execute_tool_calls = _make_wrapper(original)
    setattr(agent_cls, _MARKER, True)
    sys.stderr.write(
        f"[delegation-checkpoint] installed "
        f"(terminal>={TERMINAL_MIN}, tokens>={TOKEN_MIN}, "
        f"writes>={WRITE_MIN}, enabled={ENABLED})\n"
    )
    return True


def apply_patches(run_agent_module: object = None) -> bool:
    """Install the delegation-checkpoint wrapper.

    Safe to call from sitecustomize (at Python startup, before run_agent
    loads) and from anthropic_billing_bypass.apply_patches (Anthropic path).
    Idempotent across both callers.

    If run_agent_module is None and run_agent is not yet in sys.modules,
    a MetaPathFinder is armed to patch the class the moment run_agent loads
    naturally — avoiding a heavy eager import at interpreter startup.
    """
    global _INSTALL_STARTED

    if not ENABLED:
        return False

    # Fast path: caller passes the module directly (e.g. test harness).
    if run_agent_module is not None:
        return _patch_class(run_agent_module)

    # Direct path: run_agent is already loaded.
    existing = sys.modules.get("run_agent")
    if existing is not None:
        return _patch_class(existing)

    # Deferred path: arm a finder — only once across all callers.
    if _INSTALL_STARTED:
        return True  # finder already armed; class will be patched when it loads
    _INSTALL_STARTED = True

    try:
        from importlib.abc import MetaPathFinder
        from importlib.util import find_spec as _find_spec
    except ImportError:
        sys.stderr.write("[delegation-checkpoint] importlib unavailable; skipping\n")
        return False

    class _DelegFinder(MetaPathFinder):
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
                        f"[delegation-checkpoint] deferred patch error (no-op): "
                        f"{type(exc).__name__}: {exc}\n"
                    )

            spec.loader.exec_module = patched_exec  # type: ignore[attr-defined]
            return spec

    sys.meta_path.insert(0, _DelegFinder())
    return True
