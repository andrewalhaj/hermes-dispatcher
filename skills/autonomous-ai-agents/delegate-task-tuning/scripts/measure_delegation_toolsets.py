"""Measure delegate_task subagent tool-schema cost by toolset selection.

For each enabled_toolsets selection, prints the tool COUNT and the JSON
schema BYTES sent to the API on every iteration of a subagent's loop. Use this
to pick the minimum toolset per task archetype and to refresh the byte-weight
table in SKILL.md (numbers drift as tools are added/removed across versions).

Run with the hermes-agent venv:
    HERMES_HOME=/root/.hermes /usr/local/lib/hermes-agent/venv/bin/python \
    ~/.hermes/skills/autonomous-ai-agents/delegate-task-tuning/scripts/measure_delegation_toolsets.py

KEY INSIGHT this proves: there is NO forced core-tool floor — passing
["file"] yields EXACTLY 4 tools, nothing force-injected. So the minimum is
whatever the task genuinely needs. The atomic file/terminal toolsets are the
lean path; `coding` (31 tools) and `debugging` only LOOK minimal by name.
"""
import sys, json

sys.path.insert(0, "/usr/local/lib/hermes-agent")
import model_tools


def measure(toolsets):
    """Return (n_tools, schema_bytes, sorted_names) for an enabled_toolsets selection.
    toolsets=None means the FULL inherited set (what a child gets with no scope)."""
    try:
        defs = model_tools.get_tool_definitions(enabled_toolsets=toolsets)
    except Exception as e:
        return None, None, [f"ERR: {e}"]
    names = []
    for d in defs:
        fn = d.get("function", d)
        names.append(fn.get("name", "?"))
    return len(defs), len(json.dumps(defs)), sorted(names)


# Add/adjust scenarios as needed. None = full inherit (the default a child gets).
SCENARIOS = [
    ("FULL (inherit, no scope)", None),
    ("search (search only)", ["search"]),
    ("web", ["web"]),
    ("file", ["file"]),
    ("terminal", ["terminal"]),
    ("file+terminal", ["file", "terminal"]),
    ("file+terminal+web", ["file", "terminal", "web"]),
    ("file+terminal+skills", ["file", "terminal", "skills"]),
    ("coding (LOOKS minimal — it isn't)", ["coding"]),
]


def main():
    print(f"{'scenario':36s} {'n':>4s} {'schema_bytes':>13s}")
    print("-" * 56)
    full_bytes = None
    rows = []
    for label, ts in SCENARIOS:
        n, sb, names = measure(ts)
        rows.append((label, ts, n, sb, names))
        if ts is None:
            full_bytes = sb
        if n is None:
            print(f"{label:36s} {names[0]}")
        else:
            delta = f"  (−{round((1 - sb / full_bytes) * 100)}%)" if full_bytes and ts is not None else ""
            print(f"{label:36s} {n:>4d} {sb:>13,d}{delta}")

    # Print the tool names for the two most common lean archetypes.
    for want in ("file", "file+terminal"):
        for label, ts, n, sb, names in rows:
            if label == want:
                print(f"\n=== {want} tools ({n}) ===\n{names}")


if __name__ == "__main__":
    main()
