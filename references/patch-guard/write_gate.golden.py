"""
write_gate.py — hard-enforcement write gate for hermes-agent.
=============================================================

PURPOSE
-------
Blocks or warns on gated tool calls (terminal commands, file writes/patches)
that target protected paths or invoke privileged system operations. The gate
is an honesty mechanism, not adversarial security: the agent arms it only
after explicit user greenlight via a time-limited grant token.

FAIL-OPEN GUARANTEE
-------------------
All gate logic is wrapped in try/except. Any bug or unexpected exception in
the gate MUST be a NO-OP that ALLOWS the action and logs to stderr. A buggy
gate must never brick the agent.

INTERCEPTION MECHANISM
----------------------
We wrap AIAgent._execute_tool_calls (same anchor as delegation_checkpoint,
memory_checkpoint, skill_review_checkpoint, domain_ownership_checkpoint).

BEFORE calling the original, we scan assistant_message.tool_calls for gated
actions and NEUTRALIZE them via argument rewriting:

  - terminal: replace ``command`` with ``echo '<BLOCK_MSG>'`` so the shell
    runs a harmless echo instead of the gated command. The echo output
    naturally becomes the tool result visible to the model.

  - write_file / patch: replace ``path`` with ``/dev/null`` so the write
    goes nowhere. The tool still executes (preserving the message protocol
    — every tool_call_id gets a tool_result), but no file is touched.

AFTER the original returns, we scan messages for tool results from the
gated calls and append the block-message warning so the model sees why
its action was blocked.

This two-phase approach guarantees:
  (a) every tool_call has a matching tool_result (provider-agnostic),
  (b) the gated action never executes,
  (c) the model receives an in-band explanation.

ARCHITECTURE (Option A — mirrors delegation_checkpoint.py)
----------------------------------------------------------
Standalone module in ~/.hermes/patches/. Two load paths:
  1. sitecustomize.py at Python startup (provider-independent)
  2. anthropic_billing_bypass.apply_patches() for the Anthropic path

Both idempotent: module-level _INSTALL_STARTED + class _MARKER.

GREENLIGHT TOKEN (the arm mechanism)
------------------------------------
Token file: /root/.hermes/.write_gate_grant — JSON:
  {"armed_at": <epoch>, "expires": <epoch>, "note": "<approval summary>"}

If the file exists, parses, and time.time() < expires → ALLOW the action.
Corrupt/expired file → treat as not armed.

CLI: python3 /root/.hermes/patches/write_gate.py arm "<note>" [--ttl SECONDS]
     python3 /root/.hermes/patches/write_gate.py disarm
     python3 /root/.hermes/patches/write_gate.py status

Default TTL 600s, max 3600s. Refuses empty note.

DISABLE
-------
  export HERMES_WRITE_GATE=off

MODE
----
  export HERMES_WRITE_GATE_MODE=block (default) | warn
  warn = execute but append a loud warning to the tool result

ROLLBACK
--------
Delete this file + remove chain line from anthropic_billing_bypass.py +
remove block from sitecustomize.py + restart gateway.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time


# ── Tunables ─────────────────────────────────────────────────────────────────

ENABLED = os.environ.get(
    "HERMES_WRITE_GATE", "on"
).strip().lower() not in {"off", "0", "false", "no", "disabled"}

MODE = os.environ.get("HERMES_WRITE_GATE_MODE", "block").strip().lower()
if MODE not in {"block", "warn"}:
    MODE = "block"

_MARKER = "_write_gate_patched"
_INSTALL_STARTED = False

_HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
_GRANT_PATH = os.path.join(_HERMES_HOME, ".write_gate_grant")
_AUDIT_LOG  = os.path.join(_HERMES_HOME, "references", "write-gate-audit.log")

# ── Gated paths (after expanduser/realpath-ish normalization) ────────────────

_GATED_PATH_LITERALS = (
    "/etc/",
    os.path.join(_HERMES_HOME, "config.yaml"),
    os.path.join(_HERMES_HOME, ".env"),
    os.path.join(_HERMES_HOME, "AGENTS.md"),
    os.path.join(_HERMES_HOME, "SOUL.md"),
    os.path.join(_HERMES_HOME, "skills/"),
    os.path.join(_HERMES_HOME, "profiles/"),
    os.path.join(_HERMES_HOME, "cron/"),
    os.path.join(_HERMES_HOME, "patches/"),
    os.path.join(_HERMES_HOME, "references/patch-guard/"),
    "/root/.config/systemd/",
    "/usr/local/lib/hermes-agent/",
)

# Explicitly NOT gated:
#   /root/.hermes/memories/  (autonomous by doctrine)
#   /root/.hermes/references/  (except patch-guard subdir)

# ── Gated terminal command patterns ──────────────────────────────────────────

# Regex patterns for gated commands (case-sensitive, word-boundary aware)
_GATED_TERMINAL_PATTERNS = [
    # systemctl with state-changing verbs
    re.compile(r"systemctl\s+(--user\s+)?(restart|stop|start|enable|disable)\b"),
    # docker compose / docker with state-changing verbs
    re.compile(r"docker\s+(compose\s+)?(restart|stop|start|rm|up|down)\b"),
    # apt / apt-get install/remove/purge
    re.compile(r"\bapt(-get)?\s+(install|remove|purge)\b"),
    # pip / pip3 install/uninstall
    re.compile(r"\bpip3?\s+(install|uninstall)\b"),
    # reboot, shutdown, kill -9, chmod 777, chown -R
    re.compile(r"\breboot\b"),
    re.compile(r"\bshutdown\b"),
    re.compile(r"kill\s+-9\b"),
    re.compile(r"chmod\s+777\b"),
    re.compile(r"chown\s+-R\b"),
    # scp (always gated)
    re.compile(r"\bscp\b"),
    # ssh with state-changing token
    re.compile(
        r"\bssh\b.*\b(systemctl|docker\s+(restart|stop|start|rm|compose)"
        r"|rm\s+|tee\s+|sed\s+-i|apt|reboot|shutdown|>>|>)\b"
    ),
]

# Shell-redirect regex: command mentions a gated path literal AND a redirect/overwrite token
_GATED_PATH_LITERALS_FOR_REDIRECT = (
    "config.yaml", "/.env", "AGENTS.md", "SOUL.md", "/etc/", "patch-guard",
)

def _has_write_redirect(cmd: str) -> bool:
    """Return True if cmd contains a genuine shell write, False for read-only uses.

    Distinguishes real file writes (>file, tee, sed -i, cp, mv, rm) from
    harmless fd-redirects that trip on gated path literals (2>&1, 2>/dev/null,
    &>/dev/null).  Word-boundary guards prevent substring false-matches on
    tokens like 'mcp' containing 'cp', 'firm' containing 'rm', etc.
    """
    # Explicit write verbs always gate, regardless of redirect shape.
    if re.search(r"\btee\s+|\bsed\s+-i\b|\bcp\s+|\bmv\s+|\brm\s+", cmd):
        return True
    # Scrub fd-duplications: 2>&1, 1>&2, >&2, >&1
    s = re.sub(r"\d*>>?\s*&\s*\d", " ", cmd)
    # Scrub null-sink redirects: >/dev/null, 2>/dev/null, &>/dev/null
    s = re.sub(r"(\d+|&)?>>?\s*/dev/null", " ", s)
    # Any surviving > or >> is a real file write — gate it.
    return bool(re.search(r">>?", s))

# ── Block message ────────────────────────────────────────────────────────────

def _block_message(tool_name: str, summary: str) -> str:
    return (
        f"[WRITE GATE] Blocked gated action: {tool_name}: {summary}. "
        f"This action requires explicit user greenlight per AGENTS.md. "
        f"Present what/risks/rollback, wait for approval, then arm the gate: "
        f"python3 ~/.hermes/patches/write_gate.py arm "
        f"\"<approval note>\" --ttl 600 and retry."
    )


# ── Greenlight token ─────────────────────────────────────────────────────────

def _read_grant() -> dict | None:
    """Read the grant file. Returns parsed dict or None if missing/corrupt/expired."""
    try:
        if not os.path.exists(_GRANT_PATH):
            return None
        with open(_GRANT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        expires = data.get("expires")
        if not isinstance(expires, (int, float)):
            return None
        if time.time() >= expires:
            return None  # expired
        return data
    except Exception:
        return None


def _is_armed() -> bool:
    """Return True if the gate is currently armed (valid, unexpired grant)."""
    return _read_grant() is not None


# ── Path normalization ───────────────────────────────────────────────────────

def _normalize_path(raw: str) -> str:
    """Expanduser + realpath-like normalization for gate path matching."""
    try:
        p = os.path.expanduser(raw)
        # realpath resolves symlinks and normalizes; fall back to abspath
        p = os.path.realpath(p)
    except Exception:
        try:
            p = os.path.abspath(os.path.expanduser(raw))
        except Exception:
            return raw
    return p


def _is_gated_path(file_path: str) -> bool:
    """Check if a file path falls under any gated path prefix."""
    if not file_path or not isinstance(file_path, str):
        return False
    norm = _normalize_path(file_path)
    # Ensure trailing slash for directory prefixes for prefix matching
    if not norm.endswith("/") and os.path.isdir(norm):
        norm += "/"
    for gate in _GATED_PATH_LITERALS:
        gate_norm = _normalize_path(gate)
        if norm == gate_norm or norm.startswith(gate_norm.rstrip("/") + "/") or norm.startswith(gate_norm):
            return True
    return False


# ── Terminal command matching ────────────────────────────────────────────────

def _is_gated_command(cmd: str) -> tuple[bool, str]:
    """Check if a terminal command matches any gated pattern.
    Returns (is_gated, reason_summary).
    """
    if not cmd or not isinstance(cmd, str):
        return False, ""

    # Check regex patterns
    for pat in _GATED_TERMINAL_PATTERNS:
        m = pat.search(cmd)
        if m:
            return True, m.group(0)[:80]

    # Check shell-redirect to gated paths
    if _has_write_redirect(cmd):
        for lit in _GATED_PATH_LITERALS_FOR_REDIRECT:
            if lit in cmd:
                return True, f"redirect to gated path ({lit})"

    return False, ""


# ── Tool call argument parsing (mirrors memory_checkpoint pattern) ───────────

def _tool_call_name(tc: object) -> str:
    try:
        return getattr(getattr(tc, "function", None), "name", None) or ""
    except Exception:
        return ""


def _tool_call_args(tc: object) -> dict:
    """Parse function.arguments JSON into a dict. Returns empty dict on failure."""
    try:
        raw = getattr(getattr(tc, "function", None), "arguments", None) or "{}"
        if isinstance(raw, dict):
            return raw
        parsed = json.loads(raw) if isinstance(raw, str) else {}
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _set_tool_call_args(tc: object, args: dict) -> bool:
    """Write a dict back into function.arguments as JSON. Returns True on success."""
    try:
        fn = getattr(tc, "function", None)
        if fn is None:
            return False
        fn.arguments = json.dumps(args, ensure_ascii=False)
        return True
    except Exception:
        return False


# ── Neutralization ───────────────────────────────────────────────────────────

def _neutralize_terminal(tc: object, block_msg: str) -> str:
    """Rewrite terminal command to a harmless echo. Returns summary string."""
    args = _tool_call_args(tc)
    cmd = args.get("command", "")
    is_gated, reason = _is_gated_command(cmd)
    if not is_gated:
        return ""

    summary = f"terminal: {reason}"
    args["command"] = f"echo '{block_msg}'"
    _set_tool_call_args(tc, args)
    return summary


def _neutralize_write_file(tc: object, tool_name: str, block_msg: str) -> str:
    """Rewrite write_file/patch path to /dev/null. Returns summary string."""
    args = _tool_call_args(tc)
    path = args.get("path", "")
    if not _is_gated_path(path):
        return ""

    # For write_file, also set content to block message so it's harmless
    if tool_name == "write_file":
        args["content"] = block_msg
    # For patch, clear old_string/new_string so nothing is patched
    if tool_name == "patch":
        args["old_string"] = ""
        args["new_string"] = ""

    summary = f"{tool_name}: {os.path.basename(path)[:60]}"
    args["path"] = "/dev/null"
    _set_tool_call_args(tc, args)
    return summary


# ── Audit logging ────────────────────────────────────────────────────────────

def _audit_log(event: str, detail: str) -> None:
    """Append a line to the audit log."""
    try:
        os.makedirs(os.path.dirname(_AUDIT_LOG), exist_ok=True)
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(_AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(f"{ts} {event} {detail}\n")
    except Exception:
        pass


# ── Result appending (post-execution, like nudge patches) ────────────────────

def _append_to_tool_results(messages: list, gated_results: dict[str, str]) -> bool:
    """Append block messages to the tool result entries for gated tool_call_ids.
    gated_results maps tool_call_id -> block_message_text.
    Returns True if at least one was appended.
    """
    if not gated_results or not messages:
        return False
    appended = False
    try:
        for m in messages:
            if not isinstance(m, dict) or m.get("role") != "tool":
                continue
            tcid = m.get("tool_call_id", "")
            if tcid in gated_results:
                base = m.get("content")
                base = base if isinstance(base, str) else (
                    "" if base is None else str(base)
                )
                m["content"] = base + "\n\n" + gated_results[tcid]
                appended = True
    except Exception:
        pass
    return appended


# ── Wrapper factory ──────────────────────────────────────────────────────────

def _make_wrapper(original: object):
    def _wrapped(self, assistant_message, messages, effective_task_id, api_call_count=0):
        # ── Phase 1: scan + neutralize BEFORE execution ──────────────────
        neutralized: dict[str, str] = {}  # tool_call_id -> block_message
        try:
            if not ENABLED:
                pass
            elif _is_armed():
                try:
                    grant = _read_grant()
                    note = (grant or {}).get("note", "?")
                    sys.stderr.write(
                        f"[write-gate] armed-pass: {note}\n"
                    )
                except Exception:
                    pass
            else:
                tcs = getattr(assistant_message, "tool_calls", None) or []
                for tc in tcs:
                    name = _tool_call_name(tc)
                    tcid = getattr(tc, "id", "") or ""

                    if name == "terminal":
                        args = _tool_call_args(tc)
                        cmd = args.get("command", "")
                        is_gated, reason = _is_gated_command(cmd)
                        if is_gated:
                            if MODE == "block":
                                block_msg = _block_message("terminal", reason)
                                summary = _neutralize_terminal(tc, block_msg)
                                neutralized[tcid] = block_msg
                                sid = getattr(self, "session_id", "?")
                                sys.stderr.write(
                                    f"[write-gate] BLOCKED tool=terminal "
                                    f"detail={summary} session={sid}\n"
                                )
                                _audit_log("BLOCK", f"terminal: {reason}")
                            else:  # warn mode
                                neutralized[tcid] = (
                                    f"[WRITE GATE WARNING] Gated terminal "
                                    f"command: {reason}. Per AGENTS.md this "
                                    f"requires user greenlight. Executed, "
                                    f"but review is needed."
                                )
                                sys.stderr.write(
                                    f"[write-gate] WARN tool=terminal "
                                    f"detail={reason}\n"
                                )

                    elif name in ("write_file", "patch"):
                        args = _tool_call_args(tc)
                        path = args.get("path", "")
                        if _is_gated_path(path):
                            if MODE == "block":
                                block_msg = _block_message(name, os.path.basename(path)[:60])
                                summary = _neutralize_write_file(tc, name, block_msg)
                                neutralized[tcid] = block_msg
                                sid = getattr(self, "session_id", "?")
                                sys.stderr.write(
                                    f"[write-gate] BLOCKED tool={name} "
                                    f"detail={summary} session={sid}\n"
                                )
                                _audit_log("BLOCK", f"{name}: {summary}")
                            else:  # warn mode
                                neutralized[tcid] = (
                                    f"[WRITE GATE WARNING] Gated file write: "
                                    f"{name} targeting {path[:60]}. Per "
                                    f"AGENTS.md this requires user greenlight. "
                                    f"Executed, but review is needed."
                                )
                                sys.stderr.write(
                                    f"[write-gate] WARN tool={name} "
                                    f"detail={path[:60]}\n"
                                )
        except Exception as exc:
            try:
                sys.stderr.write(
                    f"[write-gate] guard error (no-op): "
                    f"{type(exc).__name__}: {exc}\n"
                )
            except Exception:
                pass

        # ── Phase 2: execute (neutralized tools run harmlessly) ──────────
        result = original(self, assistant_message, messages, effective_task_id, api_call_count)

        # ── Phase 3: append block/warn messages to tool results ──────────
        try:
            if neutralized:
                _append_to_tool_results(messages, neutralized)
        except Exception as exc:
            try:
                sys.stderr.write(
                    f"[write-gate] post-exec append error (no-op): "
                    f"{type(exc).__name__}: {exc}\n"
                )
            except Exception:
                pass

        return result
    return _wrapped


# ── Class patching ───────────────────────────────────────────────────────────

def _patch_class(run_agent_module: object) -> bool:
    """Wrap AIAgent._execute_tool_calls on the given module. Idempotent."""
    agent_cls = (
        getattr(run_agent_module, "AIAgent", None)
        or getattr(run_agent_module, "RunAgent", None)
    )
    if agent_cls is None:
        sys.stderr.write(
            "[write-gate] agent class (AIAgent/RunAgent) not found; skipping\n"
        )
        return False
    if getattr(agent_cls, _MARKER, False):
        return True  # already wrapped
    original = getattr(agent_cls, "_execute_tool_calls", None)
    if not callable(original):
        sys.stderr.write(
            "[write-gate] _execute_tool_calls not found; skipping\n"
        )
        return False
    agent_cls._execute_tool_calls = _make_wrapper(original)
    setattr(agent_cls, _MARKER, True)
    sys.stderr.write(
        f"[write-gate] installed (mode={MODE}, enabled={ENABLED})\n"
    )
    return True


# ── Deferred install (MetaPathFinder pattern) ─────────────────────────────────

def apply_patches(run_agent_module: object = None) -> bool:
    """Install the write-gate wrapper.

    Safe to call from sitecustomize (at Python startup) and from
    anthropic_billing_bypass.apply_patches (Anthropic path). Idempotent.
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
        return True
    _INSTALL_STARTED = True

    try:
        from importlib.abc import MetaPathFinder
        from importlib.util import find_spec as _find_spec
    except ImportError:
        sys.stderr.write("[write-gate] importlib unavailable; skipping\n")
        return False

    class _WriteGateFinder(MetaPathFinder):
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
                        f"[write-gate] deferred patch error (no-op): "
                        f"{type(exc).__name__}: {exc}\n"
                    )

            spec.loader.exec_module = patched_exec  # type: ignore[attr-defined]
            return spec

    sys.meta_path.insert(0, _WriteGateFinder())
    return True


# ── CLI (arm / disarm / status) ──────────────────────────────────────────────

def _cli_arm(note: str, ttl: int = 600) -> None:
    """Arm the gate with a time-limited grant."""
    if not note or not note.strip():
        print("ERROR: note is required (describe what you're approving)", file=sys.stderr)
        sys.exit(1)
    ttl = max(1, min(ttl, 3600))
    now = time.time()
    grant = {
        "armed_at": now,
        "expires": now + ttl,
        "note": note.strip(),
    }
    os.makedirs(os.path.dirname(_GRANT_PATH), exist_ok=True)
    with open(_GRANT_PATH, "w", encoding="utf-8") as f:
        json.dump(grant, f, indent=2)
    _audit_log("ARM", f"ttl={ttl} note={note.strip()[:100]}")
    print(f"🔓 Write gate ARMED for {ttl}s: {note.strip()}")


def _cli_disarm() -> None:
    """Disarm the gate (remove grant file)."""
    if os.path.exists(_GRANT_PATH):
        os.remove(_GRANT_PATH)
        _audit_log("DISARM", "manual")
        print("🔒 Write gate DISARMED")
    else:
        print("🔒 Write gate already disarmed (no grant file)")


def _cli_status() -> None:
    """Print gate status."""
    grant = _read_grant()
    if grant is None:
        print("🔒 Write gate: DISARMED (no valid grant)")
        print(f"   Mode: {MODE}")
        print(f"   Enabled: {ENABLED}")
    else:
        remaining = max(0, grant["expires"] - time.time())
        print(f"🔓 Write gate: ARMED ({remaining:.0f}s remaining)")
        print(f"   Note: {grant.get('note', '?')}")
        print(f"   Mode: {MODE}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Hermes write gate CLI")
    sub = parser.add_subparsers(dest="cmd")

    arm_p = sub.add_parser("arm", help="Arm the gate")
    arm_p.add_argument("note", help="Approval note (what are you greenlighting?)")
    arm_p.add_argument("--ttl", type=int, default=600, help="Time-to-live in seconds (default 600, max 3600)")

    sub.add_parser("disarm", help="Disarm the gate")
    sub.add_parser("status", help="Show gate status")

    args = parser.parse_args()

    if args.cmd == "arm":
        _cli_arm(args.note, args.ttl)
    elif args.cmd == "disarm":
        _cli_disarm()
    elif args.cmd == "status":
        _cli_status()
    else:
        parser.print_help()
