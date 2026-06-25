"""
kanban_checkpoint.py — per-turn kanban/delegate nudge for hermes-agent.
=======================================================================

PURPOSE
-------
Three complementary gates, all injected into the first tool result each turn:

1. PHASE GATE — fires when the user's message describes a multi-phase
   SEQUENTIAL task (each step depends on the prior). Nudges toward
   kanban_create() with a phase breakdown.

   Triggers (score >= 2, any combination):
     - Explicit phase/step language: "refactor", "migration", "rebuild",
       "step by step", "several stages", etc.                     (+2)
     - Sequential connectors: 2+ of first/then/next/finally       (+2)
     - 3+ distinct system words: server, docker, api, auth, …     (+2)
     - 3+ numbered steps in the message                           (+2)
     - Structural-change verbs: revert, migrate, overhaul, …      (+1)

2. MULTI-PART GATE — fires when the user's message looks like multiple
   independent tasks or questions. Nudges toward delegate_task or kanban
   swarm fan-out.

   NOTE: both gates score independently. When BOTH fire, the fan-out nudge
   wins (stronger action). Previously the phase gate returned early and
   suppressed multi-part — that caused prompts like "inventory then bring
   it all in" (with bullet constraints) to only get "one card" when they
   deserved a fan-out prompt.

3. POST-ANALYSIS RE-FIRE GATE — fires after a turn where the agent made
   many read-only tool calls (inventory/analysis pattern) without yet
   routing to kanban. Nudges "you just analyzed — is this fan-out shaped?"

   Triggers: >= READ_TOOL_THRESHOLD read-only tool calls in the assistant
   batch (read_file, search_files, terminal read-commands, web_search,
   web_extract, browser_snapshot, session_search, honcho_search) AND no
   kanban/delegate tool was called. Suppressed if the user message already
   triggered gate 1 or 2 this turn (no double-nudge).

All gates:
  - Fire at most ONCE per user turn
  - Are suppressed if the agent already called a kanban/delegate tool
  - Are suppressed inside dispatcher-spawned workers (HERMES_KANBAN_TASK set)
  - Are fail-open — any exception = no-op

DISABLE
-------
  export HERMES_KANBAN_CHECKPOINT=off

ROLLBACK
--------
Delete this file + remove the block from sitecustomize.py + restart gateway.
"""

from __future__ import annotations

import json
import os
import re
import sys


# ── Tunables ─────────────────────────────────────────────────────────────────

ENABLED = (
    os.environ.get("HERMES_KANBAN_CHECKPOINT", "on").strip().lower()
    not in {"off", "0", "false", "no", "disabled"}
)

# ── Whole-objective gate (pre-execution intercept) ───────────────────────────
# Distinct from the post-execution nudge below: this PRE-execution layer blocks
# write_file/patch calls until an inventory.json artifact exists and routing is
# resolved, for objectives shaped like "surface/inventory everything".
OBJGATE_ENABLED = (
    os.environ.get("HERMES_OBJGATE", "on").strip().lower()
    not in {"off", "0", "false", "no", "disabled"}
)
OBJGATE_K = int(os.environ.get("HERMES_OBJGATE_K", "3"))
HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
INVENTORY_PATH = os.path.join(HERMES_HOME, "run", "inventory.json")

# Inventory-intent regex: does the user's objective look like a whole-objective
# "surface everything / inventory all gaps" task?
_OBJ_INTENT = re.compile(
    r'inventory|surface|bring\s+.{0,20}\s+in|every\s+(dataset|field|gap|table|column)'
    r'|what.{0,5}(missing|unsurfaced|not\s+surfaced)|populate|fill\s+in',
    re.IGNORECASE
)

# Module-level objective state (session-level, not per-agent-instance — these
# track objective progress across the whole session, mirroring the existing
# module-level globals like _INSTALL_STARTED).
_objgate_armed: bool = False
_objgate_turn_hash: str = ""
_objgate_cleared: bool = False

# Minimum signal score to fire multi-part gate.
SIGNAL_THRESHOLD = 1

# Number of read-only tool calls in one assistant batch that triggers the
# post-analysis re-fire gate.
READ_TOOL_THRESHOLD = 4

_MARKER = "_kanban_checkpoint_patched"
_INSTALL_STARTED = False

_NUDGE = (
    "\n\n[Kanban checkpoint: HERMES_KANBAN_TASK is empty — you are the board orchestrator, not a worker. "
    "This message looks multi-part. Create the task graph now: "
    "(1) 3+ independent parallel chunks → fan-out DAG via `kanban_create` (parallel cards, no parents) + integrator card; "
    "(2) single domain task owned by a peer → `kanban_create` assigned to that profile; "
    "(3) genuinely sequential dependency chain → proceed directly, state why in one line. "
    "PARTITION FIRST: identify ALL independent chunks before creating any card. "
    "Do not dispatch one card then discover parallel work remains — the full surface must be partitioned in one move. "
    "Do not execute multi-part work inline when the board is the right tool. "
    "Suppressed once a kanban or delegate action is taken this turn.]\n"
)

_PHASE_NUDGE = (
    "\n\n[Kanban phase gate: HERMES_KANBAN_TASK is empty — you are the board orchestrator. "
    "This looks like a multi-phase sequential task (each step depends on the prior). "
    "Create a kanban card with a phase breakdown now — don't inline it. "
    "Board-shaped work belongs on the board: tracked, resumable, survivable across restarts. "
    "Exception: say 'inline' / 'just go' to skip the board and proceed directly.]\n"
)

_ANALYSIS_NUDGE = (
    "\n\n[Post-analysis gate: HERMES_KANBAN_TASK is empty — you are the board orchestrator. "
    "You just ran a read-heavy inventory ({count} read-only tool calls) without routing. "
    "Fan-out DAG now: N independent gaps = N author cards (parallel, no parents) + 1 integrator card (parents=[all authors]). "
    "A monolith card is the wrong shape. A sequential inline is the wrong path. "
    "If genuinely sequential → state why in one line and proceed.]\n"
)

# Read-only tool names that count toward the analysis threshold
_READ_TOOLS = frozenset([
    "read_file", "search_files", "web_search", "web_extract",
    "browser_snapshot", "browser_navigate", "browser_scroll",
    "session_search", "honcho_search", "honcho_profile", "honcho_context",
    "terminal",   # counted only when the command looks read-only (see below)
    "kanban_list", "kanban_show",  # board reads don't route, but count as analysis
])

# Terminal subcommands/patterns that are read-only (grep, cat, ls, echo, python -c, etc.)
_READ_TERMINAL_PATTERNS = re.compile(
    r'^\s*(grep|rg|find|ls|cat|head|tail|echo|wc|stat|file|python\s+-c|python3\s+-c'
    r'|sqlite3.*\.tables|sqlite3.*pragma|curl\s+-s|ps\s+aux|systemctl\s+status'
    r'|journalctl|df\s|du\s|env\b|printenv|which\b|type\b)',
    re.IGNORECASE,
)


# ── Signal detection ─────────────────────────────────────────────────────────

_MULTIPART_KEYWORDS = [
    "also", "and also", "additionally", "as well", "as well as",
    "while you're at it", "while you are at it", "another thing",
    "few things", "couple of things", "couple things", "few questions",
    "couple of questions", "on top of that", "in addition", "plus,",
    "second,", "secondly,", "third,", "thirdly,", "lastly,", "firstly,",
    "first,", "finally,", "and then", "and make sure", "and check",
    "and verify", "and confirm", "can you also", "could you also",
    "also make", "also check", "also verify", "also look",
]

# ── Phase/step signal detection ───────────────────────────────────────────────

_PHASE_KEYWORDS = [
    r"\bphases?\b", r"\bstep by step\b", r"\bmulti.?step\b",
    r"\bmultiple steps\b", r"\bmultiple phases\b",
    r"\bseveral steps\b", r"\bseveral phases\b",
    r"\bstages?\b", r"\brollout\b", r"\bmigration\b",
    r"\brefactor\b", r"\boverhaul\b", r"\brebuild\b",
    r"\bredesign\b", r"\brework\b", r"\brewrite\b",
    r"\bfrom scratch\b", r"\bground up\b",
]

_PHASE_SYSTEM_WORDS = [
    "server", "database", "frontend", "backend", "api", "service",
    "docker", "nginx", "systemd", "deployment", "pipeline",
    "config", "schema", "endpoint", "auth", "proxy", "gateway",
]

_INLINE_OVERRIDE = frozenset([
    "inline", "just do it", "do it now", "go ahead", "proceed",
    "don't use kanban", "skip kanban", "no kanban", "just go",
])


def _score_multiphase(text: str) -> int:
    """Return a phase-complexity score. >= 2 = route to kanban."""
    if not text or len(text.strip()) < 30:
        return 0

    score = 0
    tl = text.lower()

    # Explicit phase/step language
    for pat in _PHASE_KEYWORDS:
        if re.search(pat, tl):
            score += 2
            break

    # Sequential connectors (first X, then Y, then Z)
    seq_hits = re.findall(
        r'\b(first|then|next|after that|finally|lastly|subsequently)\b', tl
    )
    if len(seq_hits) >= 2:
        score += 2

    # Multiple distinct systems mentioned (implies cross-system work)
    sys_hits = sum(1 for w in _PHASE_SYSTEM_WORDS if w in tl)
    if sys_hits >= 3:
        score += 2
    elif sys_hits >= 2:
        score += 1

    # Numbered steps (3+ = clearly phased)
    numbered = re.findall(r'(?:^|\n)\s*\d+[\.\)]\s+\S', text)
    if len(numbered) >= 3:
        score += 2

    # Action verbs indicating structural change
    if re.search(r'\b(revert|migrate|refactor|overhaul|rebuild|rewire|rearchitect)\b', tl):
        score += 1

    return score


def _has_inline_override(text: str) -> bool:
    tl = text.lower()
    return any(kw in tl for kw in _INLINE_OVERRIDE)


_IMPERATIVE_VERBS = frozenset([
    "check", "make", "verify", "confirm", "set", "get", "update",
    "add", "remove", "fix", "look", "find", "show", "tell", "list",
    "ensure", "review", "audit", "run", "test", "build", "deploy",
    "install", "configure", "enable", "disable", "create", "delete",
    "fetch", "pull", "push", "move", "copy", "rename", "restart",
    "start", "stop", "reload", "refresh", "sync", "backup", "restore",
])


def _score_multipart(text: str) -> int:
    """Return a signal score. Caller fires if score >= SIGNAL_THRESHOLD."""
    if not text or len(text.strip()) < 20:
        return 0

    score = 0
    t = text
    tl = text.lower()

    # Strong: numbered list items (1. 2. or 1) 2))
    numbered = re.findall(r'(?:^|\n)\s*\d+[\.\)]\s+\S', t)
    if len(numbered) >= 2:
        score += 2

    # Strong: bullet items (- or * or bullet)
    bullets = re.findall(r'(?:^|\n)\s*[-*\u2022]\s+\S', t)
    if len(bullets) >= 2:
        score += 2

    # Strong: multiple question marks (2+ distinct questions)
    if t.count('?') >= 2:
        score += 2

    # Weak: multi-part keywords
    for kw in _MULTIPART_KEYWORDS:
        if kw in tl:
            score += 1
            break  # count the whole group once

    # Weak: multiple imperative-verb sentences
    sentences = re.split(r'[.!?\n]\s*', t)
    imp_count = sum(
        1 for s in sentences
        if s.strip() and s.strip().split()[0].lower().rstrip('s') in _IMPERATIVE_VERBS
    )
    if imp_count >= 2:
        score += 1

    # Weak: long message with multiple "and" clauses
    if len(t) > 150 and tl.count(' and ') >= 2:
        score += 1

    return score


def _count_read_tool_calls(assistant_message: object) -> int:
    """Count read-only tool calls in this assistant batch."""
    try:
        tcs = getattr(assistant_message, "tool_calls", None) or []
        count = 0
        for tc in tcs:
            fn = getattr(tc, "function", None)
            name = getattr(fn, "name", None) or ""
            if name in _READ_TOOLS:
                if name == "terminal":
                    # Only count terminal calls that look read-only
                    args_str = str(getattr(fn, "arguments", "") or "")
                    # Extract command value from JSON args
                    cmd_match = re.search(r'"command"\s*:\s*"([^"]{0,200})', args_str)
                    cmd = cmd_match.group(1) if cmd_match else args_str
                    if _READ_TERMINAL_PATTERNS.match(cmd):
                        count += 1
                else:
                    count += 1
        return count
    except Exception:
        return 0


# ── Runtime helpers ───────────────────────────────────────────────────────────

def _last_user_text(messages: list) -> str:
    """Return the most recent user message as plain text."""
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


def _user_turn_index(messages: list) -> int:
    """Count of user messages — proxy for current turn number."""
    try:
        return sum(1 for m in messages if isinstance(m, dict) and m.get("role") == "user")
    except Exception:
        return 0


def _kanban_used(assistant_message: object) -> bool:
    """True if this assistant batch already called a kanban/delegate tool."""
    try:
        tcs = getattr(assistant_message, "tool_calls", None) or []
        for tc in tcs:
            fn = getattr(tc, "function", None)
            name = getattr(fn, "name", None) or ""
            if name in {
                "kanban_create", "kanban_list", "kanban_show",
                "kanban_complete", "kanban_block", "kanban_comment",
                "kanban_unblock", "kanban_link", "kanban_heartbeat",
                "delegate_task",
            }:
                return True
            # Catch swarm/create via terminal
            if name == "terminal":
                args = str(getattr(fn, "arguments", "") or "")
                if "kanban swarm" in args or "kanban create" in args:
                    return True
    except Exception:
        pass
    return False


def _append_nudge(messages: list, nudge: str) -> bool:
    """Inject nudge into the most recent tool result. Returns True on success."""
    try:
        for i in range(len(messages) - 1, -1, -1):
            m = messages[i]
            if isinstance(m, dict) and m.get("role") == "tool":
                base = m.get("content")
                base = base if isinstance(base, str) else ("" if base is None else str(base))
                m["content"] = base + nudge
                return True
    except Exception:
        pass
    return False


# ── Whole-objective gate helpers ──────────────────────────────────────────────

def _obj_intent_matches(text: str) -> bool:
    return bool(_OBJ_INTENT.search(text))


def _compute_turn_hash(text: str, turn_index: int) -> str:
    import hashlib
    return hashlib.sha1(f"{turn_index}:{text[:200]}".encode()).hexdigest()[:12]


def _read_inventory() -> dict | None:
    """Read inventory.json if present. Returns None on any error."""
    try:
        with open(INVENTORY_PATH) as f:
            return json.loads(f.read())  # json must be imported at top
    except Exception:
        return None


def _objgate_should_block(tool_name: str, tool_args: dict, turn_hash: str) -> tuple[bool, str]:
    """
    Returns (should_block, reason_message).
    Only called when _objgate_armed is True and _objgate_cleared is False.
    """
    # Only intercept write_file and patch
    if tool_name not in ("write_file", "patch"):
        return False, ""

    # Never block writes to the inventory file itself
    target = tool_args.get("path") or tool_args.get("file_path") or ""
    if target and (target == INVENTORY_PATH or target.endswith("inventory.json")):
        return False, ""

    inv = _read_inventory()

    if inv is None:
        return True, (
            "[Whole-objective gate] Write blocked: produce inventory.json first. "
            f"Write to: {INVENTORY_PATH} with fields: gaps[], chunks[], chunk_count, routing, reason."
        )

    # Stale artifact check: a missing/empty turn_hash means the inventory was
    # written without a turn hash (e.g. a previous objective's leftover artifact).
    # Treat it as stale — force a refresh rather than letting it persist forever.
    stored_hash = inv.get("turn_hash", "")
    if not stored_hash:
        return True, (
            "[Whole-objective gate] Write blocked: inventory.json has no turn_hash "
            "(stale leftover from a previous objective). Update it for this objective first."
        )
    if stored_hash != turn_hash:
        return True, (
            "[Whole-objective gate] Write blocked: inventory.json is from a previous objective "
            f"(hash mismatch). Update it for this objective first."
        )

    chunk_count = int(inv.get("chunk_count", 0))
    routing = str(inv.get("routing", "")).strip().lower()
    reason = str(inv.get("reason", "")).strip()

    if routing == "inline" and reason:
        return False, ""  # explicit inline declaration with reason — pass

    if chunk_count > OBJGATE_K:
        return True, (
            f"[Whole-objective gate] Write blocked: chunk_count={chunk_count} > K={OBJGATE_K}. "
            "Fan out via delegate_task (one per chunk) then integrate. "
            "Or set routing='inline' with a non-empty reason in inventory.json to override."
        )

    return False, ""


# ── Wrapper factory ───────────────────────────────────────────────────────────

def _make_wrapper(original: object):
    def _wrapped(self, assistant_message, messages, effective_task_id, api_call_count=0):
        # ── Pre-execution: whole-objective gate ──────────────────────────────
        _blocked_ids: list[str] = []
        _block_messages: dict[str, str] = {}
        try:
            global _objgate_armed, _objgate_turn_hash, _objgate_cleared
            if (OBJGATE_ENABLED and not os.environ.get("HERMES_KANBAN_TASK")
                    and not _objgate_cleared):
                # Arm check: does this turn's user message match an inventory objective?
                current_turn = _user_turn_index(messages)
                user_text = _last_user_text(messages)
                multi_score = _score_multipart(user_text)
                if (not _objgate_armed
                        and multi_score >= SIGNAL_THRESHOLD
                        and _obj_intent_matches(user_text)):
                    _objgate_armed = True
                    _objgate_turn_hash = _compute_turn_hash(user_text, current_turn)
                    sys.stderr.write(
                        f"[kanban-checkpoint] objgate ARMED turn={current_turn} "
                        f"hash={_objgate_turn_hash}\n"
                    )

                # If armed, check each write call
                if _objgate_armed:
                    # Clear if routing tool was called this batch
                    if _kanban_used(assistant_message):
                        _objgate_cleared = True
                        sys.stderr.write("[kanban-checkpoint] objgate cleared (routing tool used)\n")
                    else:
                        tcs = getattr(assistant_message, "tool_calls", None) or []
                        for tc in tcs:
                            fn = getattr(tc, "function", None)
                            if fn is None:
                                continue
                            name = getattr(fn, "name", None) or ""
                            args_raw = getattr(fn, "arguments", None) or "{}"
                            try:
                                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                            except Exception:
                                args = {}
                            should_block, msg = _objgate_should_block(
                                name, args, _objgate_turn_hash
                            )
                            if should_block:
                                tc_id = getattr(tc, "id", None) or ""
                                _blocked_ids.append(tc_id)
                                _block_messages[tc_id] = msg
                                # Rewrite to echo so the block is visible as tool output
                                # (mirrors write_gate.py approach — never silent /dev/null)
                                try:
                                    fn.arguments = json.dumps({
                                        "command": f"echo {json.dumps(msg)}"
                                    })
                                    fn.name = "terminal"
                                except Exception:
                                    pass
                                sys.stderr.write(
                                    f"[kanban-checkpoint] objgate BLOCKED {name} "
                                    f"tc_id={tc_id}\n"
                                )
        except Exception as exc:
            try:
                sys.stderr.write(
                    f"[kanban-checkpoint] objgate pre-exec error (no-op): "
                    f"{type(exc).__name__}: {exc}\n"
                )
            except Exception:
                pass

        result = original(self, assistant_message, messages, effective_task_id, api_call_count)
        try:
            if not ENABLED:
                return result

            # Never fire inside a dispatcher-spawned worker
            if os.environ.get("HERMES_KANBAN_TASK"):
                return result

            # Skip if kanban/delegate already used this batch
            if _kanban_used(assistant_message):
                return result

            # Per-turn guard: fire at most once per user turn
            current_turn = _user_turn_index(messages)
            last_turn = getattr(self, "_kanban_ckpt_last_turn", -1)
            if current_turn <= last_turn:
                return result

            user_text = _last_user_text(messages)
            inline_override = _has_inline_override(user_text)

            # ── Gates 1 + 2: score independently, pick stronger nudge ──────────
            # Previously gate 1 returned early, preventing gate 2 from running.
            # Now both score; fan-out nudge wins when multi-part also fires.
            phase_score = _score_multiphase(user_text)
            multi_score = _score_multipart(user_text)

            phase_fires = phase_score >= 2 and not inline_override
            multi_fires = multi_score >= SIGNAL_THRESHOLD and not inline_override

            if phase_fires or multi_fires:
                # Fan-out wins when multi-part also fires (stronger action);
                # phase-only → single-card nudge
                if multi_fires:
                    nudge_text = _NUDGE
                    nudge_label = "multi+phase" if phase_fires else "multi"
                else:
                    nudge_text = _PHASE_NUDGE
                    nudge_label = "phase"

                if _append_nudge(messages, nudge_text):
                    self._kanban_ckpt_last_turn = current_turn
                    sys.stderr.write(
                        f"[kanban-checkpoint] {nudge_label} gate fired: "
                        f"phase={phase_score} multi={multi_score} "
                        f"turn={current_turn} "
                        f"session={getattr(self, 'session_id', '?')}\n"
                    )
                return result

            # ── Gate 3: post-analysis re-fire ────────────────────────────────
            # Fires when the agent ran a heavy read-only inventory turn without
            # routing to kanban. Intent: "you just analyzed — is this fan-out shaped?"
            # Only fires if gates 1+2 did NOT fire this turn (no double-nudge).
            read_count = _count_read_tool_calls(assistant_message)
            if read_count >= READ_TOOL_THRESHOLD and not inline_override:
                nudge_text = _ANALYSIS_NUDGE.format(count=read_count)
                if _append_nudge(messages, nudge_text):
                    self._kanban_ckpt_last_turn = current_turn
                    sys.stderr.write(
                        f"[kanban-checkpoint] post-analysis gate fired: "
                        f"read_tools={read_count} turn={current_turn} "
                        f"session={getattr(self, 'session_id', '?')}\n"
                    )

        except Exception as exc:
            try:
                sys.stderr.write(
                    f"[kanban-checkpoint] guard error (no-op): "
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
        sys.stderr.write("[kanban-checkpoint] agent class not found; skipping\n")
        return False
    if getattr(agent_cls, _MARKER, False):
        return True
    original = getattr(agent_cls, "_execute_tool_calls", None)
    if not callable(original):
        sys.stderr.write("[kanban-checkpoint] _execute_tool_calls not found; skipping\n")
        return False
    agent_cls._execute_tool_calls = _make_wrapper(original)
    setattr(agent_cls, _MARKER, True)
    sys.stderr.write(
        f"[kanban-checkpoint] installed "
        f"(signal_threshold>={SIGNAL_THRESHOLD}, "
        f"read_tool_threshold>={READ_TOOL_THRESHOLD}, enabled={ENABLED})\n"
    )
    return True


# ── Public entry point ────────────────────────────────────────────────────────

def apply_patches(run_agent_module: object = None) -> bool:
    """Install the kanban-checkpoint wrapper. Idempotent."""
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
        sys.stderr.write("[kanban-checkpoint] importlib unavailable; skipping\n")
        return False

    class _KanbanFinder(MetaPathFinder):
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
                        f"[kanban-checkpoint] deferred patch error (no-op): "
                        f"{type(exc).__name__}: {exc}\n"
                    )

            spec.loader.exec_module = patched_exec  # type: ignore[attr-defined]
            return spec

    sys.meta_path.insert(0, _KanbanFinder())
    return True
