"""
memory_checkpoint.py — per-write memory-pressure nudge for hermes-agent.
=========================================================================

PURPOSE
-------
The proactive-storage doctrine (memory-discipline skill) relies on the agent
noticing stores are full and acting in the same turn.  In practice this fails
silently: the agent adds an entry, the store crosses 90%, and the doctrine
fires only on explicit audit — not at the moment of the write that caused the
pressure.

This module injects an in-band nudge into the tool result IMMEDIATELY after
every `memory` tool write (add/replace) that leaves a store above the warn
threshold — at the exact moment the agent still has full conversational
context to act.

THRESHOLDS
----------
  WARN  >= 88%  — "compact this turn, ≤80% target"
  CRIT  >= 95%  — same message, worded as hard directive

The live cap is read from config.yaml on every call (never the stale injected
header, which lags by 1–2 turns and caused incorrect judgment in prior
sessions).

ARCHITECTURE (mirrors delegation_checkpoint.py — Option A)
----------------------------------------------------------
Standalone module in ~/.hermes/patches/. Two load paths:
  1. sitecustomize.py at Python startup (provider-independent)
  2. anthropic_billing_bypass.apply_patches() for the Anthropic path

Both idempotent: module-level _INSTALL_STARTED + class _MARKER.

FIRES
-----
On every memory tool add/replace that pushes a store above WARN_PCT.
Re-fires on subsequent writes while the store stays above WARN_PCT — unlike
the skill/delegation guards, the memory nudge is NOT latch-once, because the
whole point is to keep reminding until the agent actually compacts.

DISABLE
-------
  export HERMES_MEMORY_CHECKPOINT=off

ROLLBACK
--------
Delete this file + remove chain line from anthropic_billing_bypass.py +
remove block from sitecustomize.py + restart gateway.
"""

from __future__ import annotations

import os
import sys

# ── Tunables ─────────────────────────────────────────────────────────────────

WARN_PCT  = int(os.environ.get("HERMES_MEMCKPT_WARN_PCT",  "88"))
CRIT_PCT  = int(os.environ.get("HERMES_MEMCKPT_CRIT_PCT",  "95"))
TARGET_PCT = int(os.environ.get("HERMES_MEMCKPT_TARGET_PCT", "80"))
ENABLED = os.environ.get(
    "HERMES_MEMORY_CHECKPOINT", "on"
).strip().lower() not in {"off", "0", "false", "no", "disabled"}

_MARKER        = "_memory_checkpoint_patched"
_INSTALL_STARTED = False
_STARTUP_CHECKED = False  # fire once at session start regardless of writes

_HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
_CONFIG_PATH  = os.path.join(_HERMES_HOME, "config.yaml")
_MEM_PATH     = os.path.join(_HERMES_HOME, "memories", "MEMORY.md")
_USER_PATH    = os.path.join(_HERMES_HOME, "memories", "USER.md")


def _active_hermes_home() -> str:
    """Return the live HERMES_HOME — re-read each call so profile workers
    (swarm-worker-a/b/c, verifier, ha-bot) monitor THEIR OWN memory stores,
    not the root profile's. Falls back to the import-time value."""
    return os.environ.get("HERMES_HOME", _HERMES_HOME)


def _active_paths() -> tuple[str, str, str]:
    """Return (config_path, mem_path, user_path) for the current HERMES_HOME."""
    home = _active_hermes_home()
    return (
        os.path.join(home, "config.yaml"),
        os.path.join(home, "memories", "MEMORY.md"),
        os.path.join(home, "memories", "USER.md"),
    )

_NUDGE_WARN = (
    "\n\n[Memory checkpoint: {store} now at {pct}% ({sz}/{cap}) after this "
    "write — above the 90% line where the autonomous-add path dies. Compact "
    "THIS turn to ≤{target}% per doctrine (verify-cold → .bak → trim-with-"
    "pointer → log). The hourly cron won't catch up in time. Fires on every "
    "write while above {warn}%.]"
)
_NUDGE_CRIT = (
    "\n\n[Memory checkpoint CRITICAL: {store} at {pct}% ({sz}/{cap}) — near "
    "reject threshold. Compact THIS turn to ≤{target}% immediately: "
    "verify-cold-copy → .bak → trim-with-pointer → log. Do not defer.]"
)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _read_caps() -> dict:
    """Read memory caps from live config.yaml. Returns {memory: int, user: int}."""
    try:
        import yaml  # type: ignore
        config_path, _, _ = _active_paths()
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        mc = cfg.get("memory") or {}
        return {
            "memory": int(mc.get("memory_char_limit", 3000)),
            "user":   int(mc.get("user_char_limit",   2250)),
        }
    except Exception:
        return {"memory": 3000, "user": 2250}


def _store_pct(path: str, cap: int) -> tuple[int, int]:
    """Return (chars, pct) for a store file."""
    try:
        with open(path, encoding="utf-8") as f:
            sz = len(f.read())
        return sz, round(sz / cap * 100)
    except FileNotFoundError:
        return 0, 0
    except Exception:
        return 0, 0


def _build_nudge(store_label: str, sz: int, cap: int, pct: int) -> str:
    kw = dict(store=store_label, pct=pct, sz=sz, cap=cap,
               target=TARGET_PCT, warn=WARN_PCT)
    if pct >= CRIT_PCT:
        return _NUDGE_CRIT.format(**kw)
    return _NUDGE_WARN.format(**kw)


def _append_to_last_tool_result(messages: list, text: str) -> bool:
    try:
        for i in range(len(messages) - 1, -1, -1):
            m = messages[i]
            if isinstance(m, dict) and m.get("role") == "tool":
                base = m.get("content")
                base = base if isinstance(base, str) else (
                    "" if base is None else str(base)
                )
                m["content"] = base + text
                return True
    except Exception:
        pass
    return False


def _tool_call_name(tc: object) -> str:
    try:
        return getattr(getattr(tc, "function", None), "name", None) or ""
    except Exception:
        return ""


def _is_memory_write(tc: object) -> bool:
    name = _tool_call_name(tc).lower()
    if "memory" not in name:
        return False
    # memory tool writes: action=add or action=replace
    try:
        import json
        args = getattr(getattr(tc, "function", None), "arguments", None) or "{}"
        parsed = json.loads(args) if isinstance(args, str) else (args or {})
        action = str(parsed.get("action", "")).lower()
        return action in {"add", "replace"}
    except Exception:
        return True  # conservative: treat unknown as a write


# ── Wrapper ───────────────────────────────────────────────────────────────────

def _make_wrapper(original: object):
    def _wrapped(self, assistant_message, messages, effective_task_id, api_call_count=0):
        result = original(self, assistant_message, messages, effective_task_id, api_call_count)
        try:
            if not ENABLED:
                return result

            global _STARTUP_CHECKED
            caps = _read_caps()
            nudges = []
            _, mem_path, user_path = _active_paths()

            # Session-start check: fire once on the first tool execution of
            # this process regardless of whether a memory write occurred.
            # Catches stores that were already over threshold before any writes
            # (e.g. USER.md drifting to 98% between sessions).
            if not _STARTUP_CHECKED:
                _STARTUP_CHECKED = True
                for store_label, path, cap_key in (
                    ("MEMORY.md", mem_path,  "memory"),
                    ("USER.md",   user_path, "user"),
                ):
                    cap = caps[cap_key]
                    sz, pct = _store_pct(path, cap)
                    if pct >= WARN_PCT:
                        nudges.append(_build_nudge(store_label, sz, cap, pct))
                if nudges:
                    combined = "".join(nudges)
                    if _append_to_last_tool_result(messages, combined):
                        try:
                            sys.stderr.write(
                                f"[memory-checkpoint] startup check fired: "
                                f"stores over threshold at session start\n"
                            )
                        except Exception:
                            pass
                    return result

            # Per-write check: fires after every memory add/replace
            tcs = getattr(assistant_message, "tool_calls", None) or []
            has_memory_write = any(_is_memory_write(tc) for tc in tcs)
            if not has_memory_write:
                return result

            for store_label, path, cap_key in (
                ("MEMORY.md", mem_path,  "memory"),
                ("USER.md",   user_path, "user"),
            ):
                cap = caps[cap_key]
                sz, pct = _store_pct(path, cap)
                if pct >= WARN_PCT:
                    nudges.append(_build_nudge(store_label, sz, cap, pct))

            if nudges:
                combined = "".join(nudges)
                if _append_to_last_tool_result(messages, combined):
                    try:
                        sys.stderr.write(
                            f"[memory-checkpoint] fired: "
                            f"{'; '.join(f'{l} {p}%' for l, p in [(s, _store_pct(p, caps[k])[1]) for s,p,k in [('MEMORY.md',mem_path,'memory'),('USER.md',user_path,'user')] if _store_pct(p,caps[k])[1]>=WARN_PCT])} "
                            f"session={getattr(self, 'session_id', '?')}\n"
                        )
                    except Exception:
                        pass

        except Exception as exc:
            try:
                sys.stderr.write(
                    f"[memory-checkpoint] guard error (no-op): "
                    f"{type(exc).__name__}: {exc}\n"
                )
            except Exception:
                pass
        return result
    return _wrapped


# ── Install ───────────────────────────────────────────────────────────────────

def _patch_class(run_agent_module: object) -> bool:
    """Wrap AIAgent._execute_tool_calls. Idempotent."""
    agent_cls = (
        getattr(run_agent_module, "AIAgent", None)
        or getattr(run_agent_module, "RunAgent", None)
    )
    if agent_cls is None:
        sys.stderr.write(
            "[memory-checkpoint] agent class (AIAgent/RunAgent) not found; skipping\n"
        )
        return False
    if getattr(agent_cls, _MARKER, False):
        return True  # already wrapped
    original = getattr(agent_cls, "_execute_tool_calls", None)
    if not callable(original):
        sys.stderr.write(
            "[memory-checkpoint] _execute_tool_calls not found; skipping\n"
        )
        return False
    agent_cls._execute_tool_calls = _make_wrapper(original)
    setattr(agent_cls, _MARKER, True)
    sys.stderr.write(
        f"[memory-checkpoint] installed "
        f"(warn>={WARN_PCT}%, crit>={CRIT_PCT}%, target={TARGET_PCT}%, "
        f"enabled={ENABLED})\n"
    )
    return True


def apply_patches(run_agent_module: object = None) -> bool:
    """Install the memory-checkpoint wrapper.

    Safe to call from sitecustomize (at Python startup) and from
    anthropic_billing_bypass.apply_patches (Anthropic path). Idempotent.
    """
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
        sys.stderr.write("[memory-checkpoint] importlib unavailable; skipping\n")
        return False

    class _MemFinder(MetaPathFinder):
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
                        f"[memory-checkpoint] deferred patch error (no-op): "
                        f"{type(exc).__name__}: {exc}\n"
                    )

            spec.loader.exec_module = patched_exec  # type: ignore[attr-defined]
            return spec

    sys.meta_path.insert(0, _MemFinder())
    return True
