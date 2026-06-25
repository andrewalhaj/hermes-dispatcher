#!/usr/bin/env python3
"""
Synthetic tests for the whole-objective gate in kanban_checkpoint.py
====================================================================
Run against the live kanban_checkpoint module with a fake agent + fake
tool_calls (same pattern as test_write_gate.py).

    /usr/local/lib/hermes-agent/venv/bin/python \
        ~/.hermes/patches/test_objgate.py
    # or simply: python3 ~/.hermes/patches/test_objgate.py

Exit 0 = all green. Non-zero = a regression; do NOT ship the edit.

The objgate is a PRE-execution intercept: it arms when the user's message
matches an "inventory / surface everything" objective AND scores multi-part,
then blocks write_file/patch calls until an inventory.json artifact exists
with resolved routing. Blocking is done by rewriting the tool_call in place
to a `terminal` echo (mirrors write_gate.py — never silent).

Covers:
  1. Armed + no inventory.json                              → BLOCK write_file
  2. Armed + stale turn_hash                                → BLOCK
  3. Armed + chunk_count > K + routing != "inline"         → BLOCK
  4. Armed + chunk_count > K + routing="inline" + reason   → PASS
  5. Armed + chunk_count <= K                              → PASS
  6. Armed + routing tool fired (delegate_task in batch)   → PASS (clear gate)
  7. HERMES_KANBAN_TASK set                                → never arms (PASS)
  8. Non-inventory user message (no intent match)          → never arms (PASS)
  9. Guard exception (malformed inventory JSON shape)      → fail-open (PASS)
 10. (bonus) Write targeting inventory.json itself         → PASS (exempt)
"""

import json
import os
import sys
import shutil
import tempfile
import types

# Ensure the patches dir is importable
sys.path.insert(0, os.path.expanduser("~/.hermes/patches"))

# Make sure we are not seen as a dispatcher-spawned worker at import time
os.environ.pop("HERMES_KANBAN_TASK", None)
os.environ["HERMES_OBJGATE"] = "on"

import kanban_checkpoint as ko  # noqa: E402

FAILS = []


def check(label, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    msg = f"  [{status}] {label}"
    if detail and not cond:
        msg += f"  -- {detail}"
    print(msg)
    if not cond:
        FAILS.append(label)


# ── Fakes (same shape as test_write_gate.py) ─────────────────────────────────

class FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = json.dumps(arguments) if isinstance(arguments, dict) else arguments


class FakeToolCall:
    """Mimics assistant_message.tool_calls[i]."""
    def __init__(self, name, arguments, tcid=None):
        self.id = tcid or f"call_{name}_{id(self)}"
        self.function = FakeFunction(name, arguments)


class FakeAssistantMessage:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


class FakeAgent:
    """Minimal agent stub. Its _execute_tool_calls is the 'original' that the
    wrapper defers to AFTER the pre-execution gate has (possibly) rewritten the
    tool_calls in place."""
    def __init__(self):
        self.session_id = "test-session"
        self._executed_calls = []  # sentinel: what actually got dispatched

    def _execute_tool_calls(self, assistant_message, messages, effective_task_id, api_call_count=0):
        for tc in assistant_message.tool_calls:
            fn = tc.function
            try:
                args = json.loads(fn.arguments) if isinstance(fn.arguments, str) else fn.arguments
            except Exception:
                args = {}
            self._executed_calls.append((fn.name, dict(args) if isinstance(args, dict) else args))
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": fn.name,
                "content": f"Result: {fn.name} executed",
            })


def make_agent_with_patch():
    """Create a FakeAgent and install the kanban-checkpoint wrapper (idempotent)."""
    agent = FakeAgent()
    fake_mod = types.ModuleType("fake_run_agent")
    fake_mod.AIAgent = FakeAgent
    ko._patch_class(fake_mod)
    return agent


# ── Test harness helpers ─────────────────────────────────────────────────────

# Intent-matching, multi-part user objective → arms the gate.
ARMED_TEXT = (
    "Inventory every dataset in the warehouse and surface all the gaps. "
    "Also bring them all in and populate the missing fields."
)
# No inventory intent (but still multi-part via 'also') → must NOT arm.
NOINTENT_TEXT = (
    "Please fix the broken login flow and also restyle the dashboard "
    "buttons to match the new palette."
)

TMPDIR = tempfile.mkdtemp(prefix="objgate_test_")
INV_PATH = os.path.join(TMPDIR, "inventory.json")
OUT_PATH = os.path.join(TMPDIR, "output.md")   # write target (NOT inventory.json)

# Redirect the module's inventory location at run-time (functions read the
# module global at call time, so this is sufficient and never touches ~/.hermes/run).
ko.INVENTORY_PATH = INV_PATH


def reset_objgate():
    ko._objgate_armed = False
    ko._objgate_turn_hash = ""
    ko._objgate_cleared = False


def write_inventory(obj):
    with open(INV_PATH, "w") as f:
        if isinstance(obj, str):
            f.write(obj)             # raw (for malformed-shape tests)
        else:
            json.dump(obj, f)


def remove_inventory():
    if os.path.exists(INV_PATH):
        os.remove(INV_PATH)


def run_turn(agent, tool_calls, user_text, kanban_task=None):
    """Drive one turn. Returns (messages, assistant_message)."""
    prev = os.environ.get("HERMES_KANBAN_TASK")
    if kanban_task is not None:
        os.environ["HERMES_KANBAN_TASK"] = kanban_task
    else:
        os.environ.pop("HERMES_KANBAN_TASK", None)
    try:
        msg = FakeAssistantMessage(tool_calls)
        messages = [{"role": "user", "content": user_text}]
        agent._execute_tool_calls(msg, messages, "task-test")
        return messages, msg
    finally:
        if prev is not None:
            os.environ["HERMES_KANBAN_TASK"] = prev
        else:
            os.environ.pop("HERMES_KANBAN_TASK", None)


def executed_names(agent):
    return [n for (n, _a) in agent._executed_calls]


def find_executed(agent, original_name):
    """Find the executed entry for a tool call. After a BLOCK it is rewritten to
    'terminal'; we can't match by name, so callers use executed_names/order."""
    for n, a in agent._executed_calls:
        if n == original_name:
            return (n, a)
    return None


def block_command_text(agent):
    """Return the echo command text of the first rewritten (terminal) call, or ''."""
    for n, a in agent._executed_calls:
        if n == "terminal" and isinstance(a, dict):
            return str(a.get("command", ""))
    return ""


# ── Test 1: Armed + no inventory.json → BLOCK ────────────────────────────────
print("Test 1: armed + no inventory.json -> BLOCK write_file")
reset_objgate()
remove_inventory()
ag = make_agent_with_patch()
run_turn(ag, [FakeToolCall("write_file", {"path": OUT_PATH, "content": "x"}, "tc1")], ARMED_TEXT)
check("gate armed", ko._objgate_armed is True)
check("write_file rewritten to terminal (blocked)", "terminal" in executed_names(ag) and "write_file" not in executed_names(ag),
      detail=f"executed={executed_names(ag)}")
check("block message: produce inventory.json", "produce inventory.json first" in block_command_text(ag),
      detail=f"cmd={block_command_text(ag)[:120]}")


# ── Test 2: Armed + stale turn_hash → BLOCK ──────────────────────────────────
print("\nTest 2: armed + stale turn_hash -> BLOCK")
reset_objgate()
write_inventory({"turn_hash": "stale9999xxxx", "chunk_count": 1, "routing": "", "reason": ""})
ag = make_agent_with_patch()
run_turn(ag, [FakeToolCall("write_file", {"path": OUT_PATH, "content": "x"}, "tc2")], ARMED_TEXT)
check("gate armed", ko._objgate_armed is True)
check("computed hash differs from stale stored hash", ko._objgate_turn_hash != "stale9999xxxx")
check("write_file blocked (stale)", "terminal" in executed_names(ag) and "write_file" not in executed_names(ag),
      detail=f"executed={executed_names(ag)}")
check("block message: hash mismatch / previous objective",
      ("hash mismatch" in block_command_text(ag)) or ("previous objective" in block_command_text(ag)),
      detail=f"cmd={block_command_text(ag)[:120]}")


# ── Test 3: Armed + chunk_count > K + routing != inline → BLOCK ──────────────
print("\nTest 3: armed + chunk_count > K + routing != 'inline' -> BLOCK")
reset_objgate()
write_inventory({"chunk_count": 5, "routing": "fanout", "reason": "", "gaps": [], "chunks": []})
ag = make_agent_with_patch()
run_turn(ag, [FakeToolCall("write_file", {"path": OUT_PATH, "content": "x"}, "tc3")], ARMED_TEXT)
check("gate armed", ko._objgate_armed is True)
check("write_file blocked (chunk_count>K)", "terminal" in executed_names(ag) and "write_file" not in executed_names(ag),
      detail=f"executed={executed_names(ag)}")
check("block message: chunk_count=5 > K=3", "chunk_count=5 > K=3" in block_command_text(ag),
      detail=f"cmd={block_command_text(ag)[:140]}")


# ── Test 4: Armed + chunk_count > K + routing=inline + reason → PASS ─────────
print("\nTest 4: armed + chunk_count > K + routing='inline' + reason -> PASS")
reset_objgate()
write_inventory({"chunk_count": 5, "routing": "inline", "reason": "one trivial file, no fan-out warranted"})
ag = make_agent_with_patch()
run_turn(ag, [FakeToolCall("patch", {"path": OUT_PATH, "old_string": "a", "new_string": "b"}, "tc4")], ARMED_TEXT)
check("gate armed", ko._objgate_armed is True)
check("patch NOT rewritten (inline override passes)", "patch" in executed_names(ag) and "terminal" not in executed_names(ag),
      detail=f"executed={executed_names(ag)}")


# ── Test 5: Armed + chunk_count <= K → PASS ──────────────────────────────────
print("\nTest 5: armed + chunk_count <= K -> PASS")
reset_objgate()
write_inventory({"chunk_count": 2, "routing": "", "reason": ""})
ag = make_agent_with_patch()
run_turn(ag, [FakeToolCall("write_file", {"path": OUT_PATH, "content": "x"}, "tc5")], ARMED_TEXT)
check("gate armed", ko._objgate_armed is True)
check("write_file passes (chunk_count<=K)", "write_file" in executed_names(ag) and "terminal" not in executed_names(ag),
      detail=f"executed={executed_names(ag)}")


# ── Test 6: Armed + routing tool fired (delegate_task) → PASS (clear) ────────
print("\nTest 6: armed + delegate_task in batch -> PASS (gate cleared)")
reset_objgate()
remove_inventory()  # would normally BLOCK; clearing must bypass that
ag = make_agent_with_patch()
run_turn(ag, [
    FakeToolCall("delegate_task", {"prompt": "chunk 1"}, "tc6a"),
    FakeToolCall("write_file", {"path": OUT_PATH, "content": "x"}, "tc6b"),
], ARMED_TEXT)
check("gate cleared after routing tool", ko._objgate_cleared is True)
check("write_file NOT blocked (cleared)", "write_file" in executed_names(ag) and "terminal" not in executed_names(ag),
      detail=f"executed={executed_names(ag)}")
check("delegate_task executed", "delegate_task" in executed_names(ag))


# ── Test 7: HERMES_KANBAN_TASK set → never arms (PASS) ───────────────────────
print("\nTest 7: HERMES_KANBAN_TASK set -> never arms (PASS)")
reset_objgate()
remove_inventory()  # would BLOCK if it armed
ag = make_agent_with_patch()
run_turn(ag, [FakeToolCall("write_file", {"path": OUT_PATH, "content": "x"}, "tc7")], ARMED_TEXT,
         kanban_task="worker-123")
check("gate did NOT arm (worker context)", ko._objgate_armed is False)
check("write_file passes (gate inert in worker)", "write_file" in executed_names(ag) and "terminal" not in executed_names(ag),
      detail=f"executed={executed_names(ag)}")


# ── Test 8: Non-inventory user message → never arms (PASS) ───────────────────
print("\nTest 8: non-inventory user message (no intent) -> never arms (PASS)")
reset_objgate()
remove_inventory()  # would BLOCK if it armed
ag = make_agent_with_patch()
run_turn(ag, [FakeToolCall("write_file", {"path": OUT_PATH, "content": "x"}, "tc8")], NOINTENT_TEXT)
check("intent does NOT match", ko._obj_intent_matches(NOINTENT_TEXT) is False,
      detail=f"intent matched on: {NOINTENT_TEXT!r}")
check("gate did NOT arm (no intent)", ko._objgate_armed is False)
check("write_file passes (never armed)", "write_file" in executed_names(ag) and "terminal" not in executed_names(ag),
      detail=f"executed={executed_names(ag)}")


# ── Test 9: Guard exception (malformed inventory shape) → fail-open (PASS) ────
# A JSON *array* parses fine (so _read_inventory returns it, not None), but then
# inv.get(...) raises AttributeError inside _objgate_should_block. That propagates
# to the wrapper's pre-exec try/except → fail-open → the write executes unblocked.
print("\nTest 9: malformed inventory JSON shape (guard exception) -> fail-open (PASS)")
reset_objgate()
write_inventory("[1, 2, 3]")  # valid JSON, wrong shape (list, not dict)
ag = make_agent_with_patch()
crashed = False
try:
    run_turn(ag, [FakeToolCall("write_file", {"path": OUT_PATH, "content": "x"}, "tc9")], ARMED_TEXT)
except Exception as exc:  # the wrapper must NOT let this escape
    crashed = True
    print(f"    (agent raised: {type(exc).__name__}: {exc})")
check("wrapper did not crash (exception swallowed)", crashed is False)
check("write_file executed despite malformed inventory (fail-open)",
      "write_file" in executed_names(ag) and "terminal" not in executed_names(ag),
      detail=f"executed={executed_names(ag)}")


# ── Test 10 (bonus): write targeting inventory.json itself → PASS (exempt) ────
print("\nTest 10 (bonus): write to inventory.json itself -> PASS (exempt)")
reset_objgate()
remove_inventory()  # would BLOCK a normal write, but inventory writes are exempt
ag = make_agent_with_patch()
run_turn(ag, [FakeToolCall("write_file", {"path": INV_PATH, "content": "{}"}, "tc10")], ARMED_TEXT)
check("gate armed", ko._objgate_armed is True)
check("write to inventory.json NOT blocked (exempt)",
      "write_file" in executed_names(ag) and "terminal" not in executed_names(ag),
      detail=f"executed={executed_names(ag)}")


# ── Cleanup + summary ────────────────────────────────────────────────────────
shutil.rmtree(TMPDIR, ignore_errors=True)

print()
if FAILS:
    print(f"RESULT: {len(FAILS)} FAILURE(S):")
    for f in FAILS:
        print(f"  X {f}")
    sys.exit(1)
print("RESULT: ALL GREEN")
sys.exit(0)
