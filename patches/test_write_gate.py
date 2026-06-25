#!/usr/bin/env python3
"""
Synthetic tests for write_gate.py
==================================
Run against the live write_gate module with a fake agent + fake tool_calls.

    /usr/local/lib/hermes-agent/venv/bin/python \
        ~/.hermes/patches/test_write_gate.py

Exit 0 = all green. Non-zero = a regression; do NOT ship the edit.

Covers:
  1. terminal "systemctl --user restart hermes-gateway" → BLOCKED
  2. write_file path=/root/.hermes/config.yaml → BLOCKED
  3. write_file path=/root/.hermes/memories/MEMORY.md → ALLOWED
  4. terminal "journalctl --user -u hermes-gateway -n 50" → ALLOWED
  5a. ssh "ssh host docker ps" → ALLOWED (read-only docker)
  5b. ssh "ssh host docker restart x" → BLOCKED (state-changing docker)
  6. Gated call with valid grant → ALLOWED, audit-logged
  7. Expired grant → BLOCKED
  8. HERMES_WRITE_GATE_MODE=warn → executes (sentinel fires) but result contains warning
  9. Guard internal exception → action ALLOWED (fail-open)
  10. HERMES_WRITE_GATE=off → all allowed
"""

import json
import os
import sys
import time
import importlib
import types

# Ensure the patches dir is importable
sys.path.insert(0, os.path.expanduser("~/.hermes/patches"))

import write_gate as wg  # noqa: E402

FAILS = []


def check(label, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    msg = f"  [{status}] {label}"
    if detail and not cond:
        msg += f"  -- {detail}"
    print(msg)
    if not cond:
        FAILS.append(label)


# ── Helpers ──────────────────────────────────────────────────────────────────

class FakeToolCall:
    """Mimics the structure of assistant_message.tool_calls[i]."""
    def __init__(self, name, arguments, tcid=None):
        self.id = tcid or f"call_{name}_{id(self)}"
        self.function = FakeFunction(name, arguments)


class FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = json.dumps(arguments) if isinstance(arguments, dict) else arguments


class FakeAssistantMessage:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


class FakeAgent:
    """Minimal agent stub with _execute_tool_calls."""
    def __init__(self):
        self.session_id = "test-session"
        self._executed_calls = []  # sentinel: records what was actually dispatched
        self._original_dispatched = False

    def _execute_tool_calls(self, assistant_message, messages, effective_task_id, api_call_count=0):
        """Fake original: record each tool_call as 'executed' and append tool results."""
        self._original_dispatched = True
        for tc in assistant_message.tool_calls:
            fn = tc.function
            args = json.loads(fn.arguments) if isinstance(fn.arguments, str) else fn.arguments
            self._executed_calls.append((fn.name, dict(args)))
            # Append a synthetic tool result
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": fn.name,
                "content": f"Result: {fn.name} executed with {json.dumps(args)}",
            })


def make_agent_with_patch():
    """Create a FakeAgent, install the write gate. Returns (agent, fake_module)."""
    agent = FakeAgent()

    # Create a fake module that has AIAgent = FakeAgent so _patch_class can find it
    fake_mod = types.ModuleType("fake_run_agent")
    fake_mod.AIAgent = FakeAgent

    # Apply patch
    wg._patch_class(fake_mod)

    return agent, fake_mod


def run_tool_turn(agent, tool_calls):
    """Simulate one turn: create assistant_message, messages, call _execute_tool_calls."""
    msg = FakeAssistantMessage(tool_calls)
    messages = []
    agent._execute_tool_calls(msg, messages, "task-test")
    return messages


def setup_grant(ttl=600, note="test approval"):
    """Create a valid grant file and return its path."""
    now = time.time()
    grant = {"armed_at": now, "expires": now + ttl, "note": note}
    grant_path = os.path.expanduser("~/.hermes/.write_gate_grant")
    os.makedirs(os.path.dirname(grant_path), exist_ok=True)
    with open(grant_path, "w") as f:
        json.dump(grant, f)
    return grant_path


def cleanup_grant():
    """Remove the grant file."""
    grant_path = os.path.expanduser("~/.hermes/.write_gate_grant")
    if os.path.exists(grant_path):
        os.remove(grant_path)


# ── Setup ────────────────────────────────────────────────────────────────────
os.environ["HERMES_WRITE_GATE_MODE"] = "block"
os.environ["HERMES_WRITE_GATE"] = "on"
cleanup_grant()
importlib.reload(wg)


# ── Test 1: terminal systemctl restart → BLOCKED ────────────────────────────
print("Test 1: terminal 'systemctl --user restart hermes-gateway' → BLOCKED")

agent1, fm1 = make_agent_with_patch()
tc1 = FakeToolCall("terminal", {"command": "systemctl --user restart hermes-gateway"}, "tcid-1")
msgs1 = run_tool_turn(agent1, [tc1])

# Check that the original dispatched (neutralized) tool
check("original dispatched (neutralized)", agent1._original_dispatched is True)

# Check that the executed command was neutralized (echo, not systemctl)
executed = agent1._executed_calls
check("tool call was executed", len(executed) == 1)
if executed:
    cmd = executed[0][1].get("command", "")
    check("command was neutralized to echo", "echo '" in cmd,
          detail=f"got command: {cmd[:80]}")

# Check that the tool result contains the block message
tool_results = [m for m in msgs1 if m.get("role") == "tool" and m.get("tool_call_id") == "tcid-1"]
check("tool result exists for tcid-1", len(tool_results) >= 1)
if tool_results:
    content = tool_results[-1].get("content", "")
    check("block message in result", "[WRITE GATE]" in content,
          detail=f"content preview: {content[:120]}")


# ── Test 2: write_file path=config.yaml → BLOCKED ───────────────────────────
print("\nTest 2: write_file path=/root/.hermes/config.yaml → BLOCKED")
agent2, fm2 = make_agent_with_patch()
tc2 = FakeToolCall("write_file", {
    "path": "/root/.hermes/config.yaml",
    "content": "evil config"
}, "tcid-2")
msgs2 = run_tool_turn(agent2, [tc2])

executed2 = agent2._executed_calls
check("tool call was executed", len(executed2) == 1)
if executed2:
    path = executed2[0][1].get("path", "")
    check("path neutralized to /dev/null", path == "/dev/null",
          detail=f"got path: {path}")

tool_results2 = [m for m in msgs2 if m.get("role") == "tool" and m.get("tool_call_id") == "tcid-2"]
if tool_results2:
    content = tool_results2[-1].get("content", "")
    check("block message in write_file result", "[WRITE GATE]" in content,
          detail=f"content preview: {content[:120]}")


# ── Test 3: write_file path=memories/MEMORY.md → ALLOWED ─────────────────────
print("\nTest 3: write_file path=/root/.hermes/memories/MEMORY.md → ALLOWED")
agent3, fm3 = make_agent_with_patch()
tc3 = FakeToolCall("write_file", {
    "path": "/root/.hermes/memories/MEMORY.md",
    "content": "memory entry"
}, "tcid-3")
msgs3 = run_tool_turn(agent3, [tc3])

executed3 = agent3._executed_calls
check("tool call was executed", len(executed3) == 1)
if executed3:
    path = executed3[0][1].get("path", "")
    check("path NOT neutralized (memories is allowed)", "/dev/null" not in path and "MEMORY" in path,
          detail=f"got path: {path}")

tool_results3 = [m for m in msgs3 if m.get("role") == "tool" and m.get("tool_call_id") == "tcid-3"]
if tool_results3:
    content = tool_results3[-1].get("content", "")
    check("NO block message for allowed path", "[WRITE GATE]" not in content,
          detail=f"content preview: {content[:120]}")


# ── Test 4: terminal "journalctl --user -u hermes-gateway -n 50" → ALLOWED ──
print("\nTest 4: terminal 'journalctl --user -u hermes-gateway -n 50' → ALLOWED")
agent4, fm4 = make_agent_with_patch()
tc4 = FakeToolCall("terminal", {"command": "journalctl --user -u hermes-gateway -n 50"}, "tcid-4")
msgs4 = run_tool_turn(agent4, [tc4])

executed4 = agent4._executed_calls
check("tool call was executed", len(executed4) == 1)
if executed4:
    cmd = executed4[0][1].get("command", "")
    check("command NOT neutralized (journalctl is read-only)", "journalctl" in cmd and "echo" not in cmd,
          detail=f"got command: {cmd[:80]}")

tool_results4 = [m for m in msgs4 if m.get("role") == "tool" and m.get("tool_call_id") == "tcid-4"]
if tool_results4:
    content = tool_results4[-1].get("content", "")
    check("NO block message for read-only command", "[WRITE GATE]" not in content,
          detail=f"content preview: {content[:120]}")


# ── Test 5a: ssh "ssh host docker ps" → ALLOWED (read-only docker) ─────────
print("\nTest 5a: ssh 'ssh host docker ps' → ALLOWED (read-only docker)")
agent5a, fm5a = make_agent_with_patch()
tc5a = FakeToolCall("terminal", {"command": "ssh root@ash-1 docker ps"}, "tcid-5a")
msgs5a = run_tool_turn(agent5a, [tc5a])

executed5a = agent5a._executed_calls
if executed5a:
    cmd = executed5a[0][1].get("command", "")
    check("ssh+docker ps NOT blocked", "echo" not in cmd and "docker ps" in cmd,
          detail=f"got command: {cmd[:80]}")

tool_results5a = [m for m in msgs5a if m.get("role") == "tool" and m.get("tool_call_id") == "tcid-5a"]
if tool_results5a:
    check("NO block message for ssh+docker ps", "[WRITE GATE]" not in tool_results5a[-1].get("content", ""))


# ── Test 5b: ssh "ssh host docker restart x" → BLOCKED ──────────────────────
print("\nTest 5b: ssh 'ssh host docker restart x' → BLOCKED")
agent5b, fm5b = make_agent_with_patch()
tc5b = FakeToolCall("terminal", {"command": "ssh root@ash-1 docker restart mycontainer"}, "tcid-5b")
msgs5b = run_tool_turn(agent5b, [tc5b])

executed5b = agent5b._executed_calls
if executed5b:
    cmd = executed5b[0][1].get("command", "")
    check("ssh+docker restart IS blocked", "echo '" in cmd,
          detail=f"got command: {cmd[:80]}")

tool_results5b = [m for m in msgs5b if m.get("role") == "tool" and m.get("tool_call_id") == "tcid-5b"]
if tool_results5b:
    check("block message for ssh+docker restart", "[WRITE GATE]" in tool_results5b[-1].get("content", ""))


# ── Test 6: Gated call with valid grant → ALLOWED ────────────────────────────
print("\nTest 6: gated call with valid grant → ALLOWED")
setup_grant(ttl=600, note="test approval for systemctl restart")
agent6, fm6 = make_agent_with_patch()
tc6 = FakeToolCall("terminal", {"command": "systemctl --user restart hermes-gateway"}, "tcid-6")
msgs6 = run_tool_turn(agent6, [tc6])

executed6 = agent6._executed_calls
check("tool call was executed", len(executed6) == 1)
if executed6:
    cmd = executed6[0][1].get("command", "")
    check("command NOT neutralized (grant armed)", "echo" not in cmd and "systemctl" in cmd,
          detail=f"got command: {cmd[:80]}")

tool_results6 = [m for m in msgs6 if m.get("role") == "tool" and m.get("tool_call_id") == "tcid-6"]
if tool_results6:
    check("NO block message when armed", "[WRITE GATE]" not in tool_results6[-1].get("content", ""))

# Check audit log
audit_log_path = os.path.expanduser("~/.hermes/references/write-gate-audit.log")
check("audit log exists", os.path.exists(audit_log_path))

cleanup_grant()


# ── Test 7: Expired grant → BLOCKED ──────────────────────────────────────────
print("\nTest 7: expired grant → BLOCKED")
setup_grant(ttl=-1, note="expired grant")  # negative ttl = already expired
time.sleep(0.2)  # ensure expiry time has passed
agent7, fm7 = make_agent_with_patch()
tc7 = FakeToolCall("terminal", {"command": "systemctl --user restart hermes-gateway"}, "tcid-7")
msgs7 = run_tool_turn(agent7, [tc7])

executed7 = agent7._executed_calls
if executed7:
    cmd = executed7[0][1].get("command", "")
    check("command IS blocked (expired grant)", "echo '" in cmd,
          detail=f"got command: {cmd[:80]}")

tool_results7 = [m for m in msgs7 if m.get("role") == "tool" and m.get("tool_call_id") == "tcid-7"]
if tool_results7:
    check("block message for expired grant", "[WRITE GATE]" in tool_results7[-1].get("content", ""))

cleanup_grant()


# ── Test 8: HERMES_WRITE_GATE_MODE=warn → executes but result contains warning
print("\nTest 8: HERMES_WRITE_GATE_MODE=warn → executes with warning")
os.environ["HERMES_WRITE_GATE_MODE"] = "warn"
cleanup_grant()

# Re-import to pick up new mode
importlib.reload(wg)

agent8, fm8 = make_agent_with_patch()
tc8 = FakeToolCall("terminal", {"command": "systemctl --user restart hermes-gateway"}, "tcid-8")
msgs8 = run_tool_turn(agent8, [tc8])

executed8 = agent8._executed_calls
check("tool call was executed", len(executed8) == 1)
if executed8:
    cmd = executed8[0][1].get("command", "")
    check("command NOT neutralized in warn mode (executes)", "echo" not in cmd and "systemctl" in cmd,
          detail=f"got command: {cmd[:80]}")

tool_results8 = [m for m in msgs8 if m.get("role") == "tool" and m.get("tool_call_id") == "tcid-8"]
if tool_results8:
    content = tool_results8[-1].get("content", "")
    check("warn message in result", "WARNING" in content,
          detail=f"content preview: {content[:120]}")

# Restore block mode
os.environ["HERMES_WRITE_GATE_MODE"] = "block"
importlib.reload(wg)


# ── Test 9: Guard internal exception → fail-open (ALLOW) ─────────────────────
print("\nTest 9: guard internal exception → fail-open (ALLOW)")
cleanup_grant()

agent9, fm9 = make_agent_with_patch()

# Monkey-patch _is_gated_command to raise an exception
original_is_gated = wg._is_gated_command
def _broken_matcher(cmd):
    raise RuntimeError("simulated guard bug")
wg._is_gated_command = _broken_matcher

try:
    tc9 = FakeToolCall("terminal", {"command": "systemctl --user restart hermes-gateway"}, "tcid-9")
    msgs9 = run_tool_turn(agent9, [tc9])

    executed9 = agent9._executed_calls
    check("tool call executed despite guard exception (fail-open)", len(executed9) == 1)
    if executed9:
        cmd = executed9[0][1].get("command", "")
        check("command NOT neutralized (guard error = fail-open)", "echo" not in cmd and "systemctl" in cmd,
              detail=f"got command: {cmd[:80]}")
    check("agent did not crash", True)
finally:
    wg._is_gated_command = original_is_gated


# ── Test 10: write_gate disabled → all allowed ──────────────────────────────
print("\nTest 10: HERMES_WRITE_GATE=off → all allowed")
os.environ["HERMES_WRITE_GATE"] = "off"
cleanup_grant()
importlib.reload(wg)

agent10, fm10 = make_agent_with_patch()
tc10 = FakeToolCall("terminal", {"command": "systemctl --user restart hermes-gateway"}, "tcid-10")
msgs10 = run_tool_turn(agent10, [tc10])

executed10 = agent10._executed_calls
if executed10:
    cmd = executed10[0][1].get("command", "")
    check("command NOT neutralized (gate disabled)", "echo" not in cmd and "systemctl" in cmd,
          detail=f"got command: {cmd[:80]}")

tool_results10 = [m for m in msgs10 if m.get("role") == "tool" and m.get("tool_call_id") == "tcid-10"]
if tool_results10:
    check("NO block message when disabled", "[WRITE GATE]" not in tool_results10[-1].get("content", ""))

# Restore
os.environ["HERMES_WRITE_GATE"] = "on"
importlib.reload(wg)


# ── Summary ──────────────────────────────────────────────────────────────────
print()
if FAILS:
    print(f"RESULT: {len(FAILS)} FAILURE(S):")
    for f in FAILS:
        print(f"  ❌ {f}")
    sys.exit(1)
print("RESULT: ALL GREEN")
sys.exit(0)
