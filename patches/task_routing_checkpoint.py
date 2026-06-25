"""
task_routing_checkpoint.py — worker availability nudge for hermes-agent.
=========================================================================

PURPOSE
-------
Fires on the first tool result each turn when kanban_create is called
WITHOUT a prior kanban_list(status='running') call in the same turn.
Reminds the orchestrator to check who's running before assigning, so
work is distributed across the coder fleet rather than stacked on one.

Also fires when kanban_create is called with assignee='coder' and the
task domain looks like it may belong to a specialist (ha-bot for home
automation, etc.).

Does NOT fire:
  - Inside spawned workers (HERMES_KANBAN_TASK set)
  - When kanban_list was already called this turn
  - On non-kanban_create tool calls

DISABLE
-------
  export HERMES_TASK_ROUTING_CHECKPOINT=off

ROLLBACK
--------
Delete this file + remove the block from sitecustomize.py + restart gateway.
"""

from __future__ import annotations

import json
import os
import re
import sys

# ── Tunables ──────────────────────────────────────────────────────────────────

ENABLED = (
    os.environ.get("HERMES_TASK_ROUTING_CHECKPOINT", "on").strip().lower()
    not in {"off", "0", "false", "no", "disabled"}
)

_MARKER = "_task_routing_checkpoint_patched"
_INSTALL_STARTED = False

_AVAILABILITY_NUDGE = (
    "\n\n[Task routing checkpoint: kanban_create called without a prior "
    "kanban_list(status='running') this turn. Check who's running first — "
    "never stack on one worker when others are free. "
    "Fleet: coder / coder-b / coder-c / coder-d (source code), "
    "ha-bot (home automation), default (orchestration). "
    "Fires once per turn. Suppressed when kanban_list ran first.]\n"
)

_DOMAIN_NUDGE = (
    "\n\n[Task routing checkpoint: assignee='coder' but task domain may "
    "belong to a specialist. Home automation / Home Assistant → ha-bot. "
    "Confirm the right worker for this domain before dispatching.]\n"
)

# Keywords that suggest home-automation domain
_HA_KEYWORDS = re.compile(
    r"\b(home.?assistant|homeassistant|lovelace|automation|hass|ha-bot"
    r"|smart.?home|govee|shield.?tv|wall.?dash)\b",
    re.IGNORECASE,
)

# ── Runtime helpers ────────────────────────────────────────────────────────────

def _is_worker() -> bool:
    return bool(os.environ.get("HERMES_KANBAN_TASK", "").strip())


def _tool_names(assistant_message: object) -> list[str]:
    try:
        tcs = getattr(assistant_message, "tool_calls", None) or []
        return [
            getattr(getattr(tc, "function", None), "name", None) or ""
            for tc in tcs
        ]
    except Exception:
        return []


def _tool_args(assistant_message: object, tool_name: str) -> dict:
    """Return parsed args for the FIRST call to tool_name."""
    try:
        tcs = getattr(assistant_message, "tool_calls", None) or []
        for tc in tcs:
            fn = getattr(tc, "function", None)
            if (getattr(fn, "name", None) or "") == tool_name:
                raw = getattr(fn, "arguments", None) or "{}"
                return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        pass
    return {}


def _append_nudge(messages: list, nudge: str) -> bool:
    try:
        for i in range(len(messages) - 1, -1, -1):
            m = messages[i]
            if isinstance(m, dict) and m.get("role") == "tool":
                base = m.get("content", "") or ""
                m["content"] = (base if isinstance(base, str) else str(base)) + nudge
                return True
    except Exception:
        pass
    return False


# ── Wrapper factory ────────────────────────────────────────────────────────────

def _make_wrapper(original: object):
    def _wrapped(self, assistant_message, messages, effective_task_id, api_call_count=0):
        try:
            if ENABLED and not _is_worker():
                names = _tool_names(assistant_message)

                if "kanban_create" in names:
                    list_ran = "kanban_list" in names

                    if not list_ran:
                        _append_nudge(messages, _AVAILABILITY_NUDGE)
                    else:
                        # List ran — still check for domain mismatch
                        args = _tool_args(assistant_message, "kanban_create")
                        assignee = str(args.get("assignee", "")).strip().lower()
                        body = str(args.get("body", "")) + str(args.get("title", ""))
                        if assignee in {"coder", "coder-b", "coder-c", "coder-d"}:
                            if _HA_KEYWORDS.search(body):
                                _append_nudge(messages, _DOMAIN_NUDGE)
        except Exception:
            pass

        return original(self, assistant_message, messages, effective_task_id, api_call_count)
    return _wrapped


# ── Class patcher ──────────────────────────────────────────────────────────────

def _patch_class(run_agent_module: object) -> bool:
    agent_cls = (
        getattr(run_agent_module, "AIAgent", None)
        or getattr(run_agent_module, "RunAgent", None)
    )
    if agent_cls is None:
        return False
    if getattr(agent_cls, _MARKER, False):
        return True
    original = getattr(agent_cls, "_execute_tool_calls", None)
    if not callable(original):
        return False
    agent_cls._execute_tool_calls = _make_wrapper(original)
    setattr(agent_cls, _MARKER, True)
    sys.stderr.write(f"[task-routing-checkpoint] installed (enabled={ENABLED})\n")
    return True


# ── Public entry point ─────────────────────────────────────────────────────────

def apply_patches(run_agent_module: object = None) -> bool:
    """Install the task-routing-checkpoint wrapper. Idempotent."""
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
        return False

    class _TaskRoutingFinder(MetaPathFinder):
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
                        f"[task-routing-checkpoint] deferred patch error: "
                        f"{type(exc).__name__}: {exc}\n"
                    )

            spec.loader.exec_module = patched_exec  # type: ignore[attr-defined]
            return spec

    sys.meta_path.insert(0, _TaskRoutingFinder())
    sys.stderr.write("[task-routing-checkpoint] deferred finder armed\n")
    return True
