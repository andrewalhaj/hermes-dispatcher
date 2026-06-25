#!/usr/bin/env python3
"""Functional health-audit harness — PRESENCE != CORRECTNESS.

Reusable shape proven 2026-06-16. Each probe must prove a subsystem WORKS,
not merely that it EXISTS. Three result states; UNVERIFIABLE is surfaced
loudly and never silently treated as PASS.

Design rules (the whole point):
  1. Scope is INVENTORY-DRIVEN, not memory-driven. List every subsystem in a
     canonical file (e.g. references/system-inventory.md). An unlisted
     subsystem is an invisible one. Adding a row here = adding monitoring.
  2. Every probe returns (state, detail) where state in {PASS, FAIL,
     UNVERIFIABLE}. A probe that CANNOT run returns UNVERIFIABLE — never PASS.
  3. Functional > existence. Examples that bit us:
       - MCP server: parse `hermes mcp test <name>` -> "Tools discovered: N";
         PASS iff N > 0 (a 0 right after restart may be a cold daemon that
         self-heals — re-probe before declaring FAIL).
       - Retrieval: fire a CANNED query, assert the KNOWN-right hit returns
         above the score floor. Row count is NOT recall quality.
       - Index freshness: compare the index's recorded commit to the live
         source HEAD; mismatch = stale = FAIL.
  4. Exit 0 iff no FAILs. UNVERIFIABLE does not fail the run but MUST print.

Adapt the PROBES list to your system; the runner/printer is generic.
"""
import subprocess, sys

PASS, FAIL, UNVERIFIABLE = "PASS", "FAIL", "UNVERIFIABLE"


def run(cmd, timeout=60):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return -1, "", str(e)


# ---- example probes (replace with your inventory's functional checks) ----

def probe_service_active(unit="hermes-gateway"):
    rc, out, _ = run(["systemctl", "--user", "is-active", unit])
    return (PASS, "active") if out.strip() == "active" else (FAIL, out.strip() or "inactive")


def probe_mcp_tools(name="codegraph"):
    """FUNCTIONAL: connects AND serves >0 tools. 0 may be a cold daemon."""
    rc, out, err = run(["hermes", "mcp", "test", name])
    combined = out + err
    for line in combined.splitlines():
        if "tools discovered" in line.lower():
            try:
                n = int(line.rsplit(":", 1)[1].strip())
            except ValueError:
                return UNVERIFIABLE, f"could not parse count: {line.strip()}"
            return (PASS, f"{n} tools") if n > 0 else (FAIL, "0 tools (cold daemon? re-probe)")
    return UNVERIFIABLE, "hermes mcp test produced no tool count"


def probe_memory_headroom(path, cap, label):
    try:
        chars = len(open(path, encoding="utf-8").read())
    except OSError as e:
        return UNVERIFIABLE, f"{label}: unreadable ({e})"
    pct = chars / cap * 100
    return (PASS if pct < 90 else FAIL), f"{label}:{chars}/{cap} ({pct:.1f}%)"


# Each entry: (id, callable-returning-(state,detail))
PROBES = [
    ("gateway", probe_service_active),
    ("mcp_tools", probe_mcp_tools),
    # ("memory", lambda: probe_memory_headroom("/path/USER.md", 2250, "USER")),
]


def main():
    print("=" * 60)
    print("  Functional Health Audit")
    print("=" * 60)
    counts = {PASS: 0, FAIL: 0, UNVERIFIABLE: 0}
    fails = []
    for pid, fn in PROBES:
        try:
            state, detail = fn()
        except Exception as e:
            state, detail = UNVERIFIABLE, f"probe raised: {e}"
        counts[state] += 1
        print(f"[{state:13}] {pid}: {detail}")
        if state == FAIL:
            fails.append(f"{pid}: {detail}")
    print("-" * 60)
    print(f"  PASS:{counts[PASS]}  FAIL:{counts[FAIL]}  UNVERIFIABLE:{counts[UNVERIFIABLE]}")
    if fails:
        print("  FAILED:")
        for f in fails:
            print(f"    - {f}")
    sys.exit(1 if counts[FAIL] else 0)


if __name__ == "__main__":
    main()
