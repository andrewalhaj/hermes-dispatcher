"""
domain_ownership_checkpoint.py — peer-domain write nudge for hermes-agent.
===========================================================================

PURPOSE
-------
Proven failure (2026-06-10): the orchestrator SSH'd state-changing edits onto
a peer agent's host (wall-dash on ash-1, owned by ha-bot/HAJarvis) despite the
kanban-swarm-dispatch skill, a prior dispatch precedent, and TWO fired
checkpoints — because every existing guard checks something else (danger,
cost, knowledge). Nothing checked OWNERSHIP. This module does.

It injects an in-band nudge into the tool result the FIRST time a session
issues a state-changing ssh/scp command against a host/path owned by another
profile — before momentum exists, at the exact moment of the routing decision.

DOMAIN MAP
----------
Read from ~/.hermes/references/domain-ownership.json when present:
  {"hosts": {"<host-or-ip-substring>": "<owner-profile>"},
   "paths": {"<remote-path-substring>": "<owner-profile>"}}
Falls back to the built-in map below. Extend the JSON as domains get
delegated — no code change needed.

FIRES
-----
First state-changing ssh/scp to an owned host per session, then re-fires
every RE_FIRE_EVERY further owned writes while no kanban dispatch to that
owner has been seen. Read-only ssh (grep/cat/ls/docker inspect/curl) does
not fire.

DISABLE
-------
  export HERMES_DOMAIN_CHECKPOINT=off

ROLLBACK
--------
Delete this file + remove chain line from anthropic_billing_bypass.py +
remove block from sitecustomize.py + restart gateway.
"""

from __future__ import annotations

import json
import os
import sys

# ── Tunables ─────────────────────────────────────────────────────────────────

ENABLED = os.environ.get(
    "HERMES_DOMAIN_CHECKPOINT", "on"
).strip().lower() not in {"off", "0", "false", "no", "disabled"}

RE_FIRE_EVERY = int(os.environ.get("HERMES_DOMAIN_CKPT_REFIRE", "5"))

_MARKER = "_domain_ownership_patched"
_INSTALL_STARTED = False

_HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
_MAP_PATH = os.path.join(_HERMES_HOME, "references", "domain-ownership.json")

# Built-in fallback map (substring match, case-insensitive)
_BUILTIN_MAP = {
    "hosts": {
        "178.156.246.115": "ha-bot",
        "ubuntu-2gb-ash-1": "ha-bot",
        "ash-1": "ha-bot",
    },
    "paths": {
        "/root/wall-dash": "ha-bot",
    },
}

# Tokens that make a remote command state-changing. Read-only ssh
# (grep/cat/ls/docker inspect/curl/find) contains none of these.
# Matched as regex with word boundaries where applicable — naive substring
# missed `"cp ...` after a quote (proven in pre-deploy tests).
_WRITE_TOKEN_PATTERNS = (
    r"sed\s+-i", r"\btee\b", r">\s*/", r">>\s*/", r"\bcp\b", r"\bmv\b",
    r"\brm\b", r"\bmkdir\b", r"\bchmod\b", r"\bchown\b",
    r"docker\s+(restart|stop|start|rm|compose|exec)", r"\bsystemctl\b",
    r"open\(", r"\.write\(", r"write_text", r"\btruncate\b",
    r"ln\s+-s", r"\btouch\b",
)

_NUDGE = (
    "\n\n[Domain-ownership checkpoint: this command WRITES to a host/path "
    "owned by profile '{owner}' ({matched}). Per the ownership protocol, "
    "state-changing work on a peer-owned domain routes to the owner as a "
    "cross-profile kanban card — the owner's brain executes on its own turf, "
    "you verify the result:\n"
    "  hermes kanban create \"<title>\" --assignee {owner} --created-by "
    "default --priority 5 --max-runtime 20m --idempotency-key <task-date> "
    "--body \"<self-contained spec>\" --json\n"
    "If inline execution is genuinely justified (emergency, owner-profile "
    "down, explicit user directive), state the justification in ONE line in "
    "your reply AND create a tracking card on the board so the shared record "
    "never diverges from reality. Re-fires every {refire} owned writes.]"
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_map() -> dict:
    try:
        with open(_MAP_PATH, encoding="utf-8") as f:
            m = json.load(f)
        if isinstance(m, dict) and ("hosts" in m or "paths" in m):
            return {
                "hosts": dict(m.get("hosts") or {}),
                "paths": dict(m.get("paths") or {}),
            }
    except Exception:
        pass
    return _BUILTIN_MAP


def _tool_call_name(tc: object) -> str:
    try:
        return getattr(getattr(tc, "function", None), "name", None) or ""
    except Exception:
        return ""


def _tool_call_args(tc: object) -> dict:
    try:
        raw = getattr(getattr(tc, "function", None), "arguments", None) or "{}"
        parsed = json.loads(raw) if isinstance(raw, str) else (raw or {})
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _owned_write(tc: object) -> tuple:
    """Return (owner, matched_token) if this tool call is a state-changing
    remote command against an owned host/path, else (None, None)."""
    name = _tool_call_name(tc).lower()
    if "terminal" not in name and "execute_code" not in name:
        return (None, None)
    args = _tool_call_args(tc)
    cmd = str(args.get("command") or args.get("code") or "")
    if not cmd:
        return (None, None)
    low = cmd.lower()
    if "ssh" not in low and "scp" not in low:
        return (None, None)

    dmap = _load_map()
    matched = None
    owner = None
    for token, own in dmap.get("hosts", {}).items():
        if token.lower() in low:
            matched, owner = token, own
            break
    if owner is None:
        for token, own in dmap.get("paths", {}).items():
            if token.lower() in low:
                matched, owner = token, own
                break
    if owner is None:
        return (None, None)

    # scp is always a push/write; ssh needs a write token
    if "scp" in low:
        return (owner, matched)
    import re as _re
    if any(_re.search(p, low) for p in _WRITE_TOKEN_PATTERNS):
        return (owner, matched)
    return (None, None)


def _saw_dispatch_to(tc: object, owner: str) -> bool:
    """True if this tool call dispatches a kanban card to the owner."""
    name = _tool_call_name(tc).lower()
    if "terminal" not in name:
        return False
    args = _tool_call_args(tc)
    cmd = str(args.get("command") or "").lower()
    return "kanban create" in cmd and f"--assignee {owner}" in cmd


def _append_nudge(messages: list, owner: str, matched: str) -> bool:
    try:
        text = _NUDGE.format(owner=owner, matched=matched, refire=RE_FIRE_EVERY)
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


# ── Wrapper ──────────────────────────────────────────────────────────────────

def _make_wrapper(original: object):
    def _wrapped(self, assistant_message, messages, effective_task_id, api_call_count=0):
        result = original(self, assistant_message, messages, effective_task_id, api_call_count)
        try:
            if not ENABLED:
                return result

            tcs = getattr(assistant_message, "tool_calls", None) or []

            # Track dispatches: a kanban card to an owner suppresses further
            # nudges for that owner this session (the route was taken).
            dispatched = getattr(self, "_domain_ckpt_dispatched", set())
            hit_owner, hit_token = None, None
            for tc in tcs:
                owner, matched = _owned_write(tc)
                if owner and owner not in dispatched:
                    hit_owner, hit_token = owner, matched
                for own in list(dispatched) + ([owner] if owner else []):
                    if own and _saw_dispatch_to(tc, own):
                        dispatched.add(own)
            # Re-scan for dispatch to the hit owner in the same turn
            if hit_owner:
                for tc in tcs:
                    if _saw_dispatch_to(tc, hit_owner):
                        dispatched.add(hit_owner)
                        hit_owner = None
                        break
            self._domain_ckpt_dispatched = dispatched

            if not hit_owner:
                return result

            counts = getattr(self, "_domain_ckpt_counts", {})
            fired_at = getattr(self, "_domain_ckpt_fired_at", {})
            counts[hit_owner] = counts.get(hit_owner, 0) + 1
            self._domain_ckpt_counts = counts

            last = fired_at.get(hit_owner)
            first_fire = last is None
            refire = last is not None and counts[hit_owner] >= last + RE_FIRE_EVERY
            if first_fire or refire:
                if _append_nudge(messages, hit_owner, hit_token):
                    fired_at[hit_owner] = counts[hit_owner]
                    self._domain_ckpt_fired_at = fired_at
                    try:
                        sys.stderr.write(
                            f"[domain-ownership-checkpoint] fired: owner={hit_owner} "
                            f"matched={hit_token} writes={counts[hit_owner]} "
                            f"session={getattr(self, 'session_id', '?')}\n"
                        )
                    except Exception:
                        pass
        except Exception as exc:
            try:
                sys.stderr.write(
                    f"[domain-ownership-checkpoint] guard error (no-op): "
                    f"{type(exc).__name__}: {exc}\n"
                )
            except Exception:
                pass
        return result
    return _wrapped


# ── Install ──────────────────────────────────────────────────────────────────

def _patch_class(run_agent_module: object) -> bool:
    agent_cls = (
        getattr(run_agent_module, "AIAgent", None)
        or getattr(run_agent_module, "RunAgent", None)
    )
    if agent_cls is None:
        sys.stderr.write(
            "[domain-ownership-checkpoint] agent class not found; skipping\n"
        )
        return False
    if getattr(agent_cls, _MARKER, False):
        return True
    original = getattr(agent_cls, "_execute_tool_calls", None)
    if not callable(original):
        sys.stderr.write(
            "[domain-ownership-checkpoint] _execute_tool_calls not found; skipping\n"
        )
        return False
    agent_cls._execute_tool_calls = _make_wrapper(original)
    setattr(agent_cls, _MARKER, True)
    sys.stderr.write(
        f"[domain-ownership-checkpoint] installed "
        f"(refire={RE_FIRE_EVERY}, enabled={ENABLED})\n"
    )
    return True


def apply_patches(run_agent_module: object = None) -> bool:
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
        sys.stderr.write("[domain-ownership-checkpoint] importlib unavailable; skipping\n")
        return False

    class _DomFinder(MetaPathFinder):
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
                        f"[domain-ownership-checkpoint] deferred patch error (no-op): "
                        f"{type(exc).__name__}: {exc}\n"
                    )

            spec.loader.exec_module = patched_exec  # type: ignore[attr-defined]
            return spec

    sys.meta_path.insert(0, _DomFinder())
    return True
