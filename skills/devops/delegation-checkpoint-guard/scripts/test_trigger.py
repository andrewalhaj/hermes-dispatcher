#!/usr/bin/env python3
"""Synthetic trigger test for delegation_checkpoint.py.

Proves a threshold edit fires on the target blowout pattern AND stays silent
on a light session — WITHOUT needing a live gateway. Run from the patches dir:

    cd ~/.hermes/patches && python3 ~/.hermes/skills/devops/delegation-checkpoint-guard/scripts/test_trigger.py
"""
import sys, types
sys.path.insert(0, ".")  # run from ~/.hermes/patches
import delegation_checkpoint as dc


class FC:
    def __init__(self, name):
        self.function = types.SimpleNamespace(name=name)


class Msg:
    def __init__(self, names):
        self.tool_calls = [FC(n) for n in names]


def make_agent(context_tokens):
    class Comp:
        last_prompt_tokens = context_tokens

    class Agent:
        context_compressor = Comp()
        session_id = "test"

        def _execute_tool_calls(self, am, msgs, tid, acc=0):
            return "orig"

    Agent._execute_tool_calls = dc._make_wrapper(Agent._execute_tool_calls)
    return Agent()


# Trigger B: inline-authoring blowout (the $100 Jarvis pattern) — tiny context
a = make_agent(1691)
msgs = [{"role": "tool", "content": "x"}]
for i in range(10):
    a._execute_tool_calls(Msg(["patch"] if i < 7 else ["write_file"]), msgs, "t")
    if getattr(a, "_deleg_ckpt_fired", False):
        break
assert getattr(a, "_deleg_ckpt_fired", False), "FAIL: trigger B did not fire"
assert "Delegation checkpoint" in msgs[0]["content"], "FAIL: nudge not appended"
print(f"PASS trigger B: fired at writes={a._deleg_ckpt_writes}, context={a.context_compressor.last_prompt_tokens}")

# Negative: light read-only session must NOT fire
b = make_agent(5000)
m2 = [{"role": "tool", "content": "y"}]
for _ in range(3):
    b._execute_tool_calls(Msg(["read_file"]), m2, "t")
assert not getattr(b, "_deleg_ckpt_fired", False), "FAIL: fired on light session"
print("PASS negative: light session stayed silent")
print("ALL TESTS PASS")
