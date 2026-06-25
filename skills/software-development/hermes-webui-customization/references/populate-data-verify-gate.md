# Populate-phase: the two syntax traps + the mandatory node-check gate

When the ask is "populate the remaining mock data" on the patched-standalone
WebUI (`hermes-webui-new/server.py` `_patch_standalone`), you add a batch of
new `_replace_block(...)` / `js.replace(...)` calls. Two of those patches WILL
introduce a JS syntax error that is invisible server-side and shows as a red
**`Root: Unexpected string`** / **`Unexpected token ':'`** banner with a blank
main panel in the live browser. Proven 2026-06-19 populating Profiles, Agents
summary, Overview chips/heatmap/day-streak, Insights token-split + skills table
(8 gaps, all in `server.py`, no `standalone.html` edits).

## TRAP 1 — `_replace_block` end marker that lands MID-EXPRESSION

`_replace_block(js, start, end, repl)` keeps `js[ei:]` — everything from the
END marker onward — and splices `repl` before it. So the end marker text is
PRESERVED, not consumed. If you pick an end marker that sits in the MIDDLE of
the expression you're replacing, the tail of the old expression survives as
orphaned source.

Concrete failure (Insights skills list):
- mock was `skills: [{ skill: 'web-fetch', ... }, ... { ... w: '39%' }],\n        };`
- I used end marker `"'39%' }],\n        };"` thinking it closed the array.
- `_replace_block` preserved `'39%' }],` → after my `skills: (...),\n` replacement,
  the next line was a bare **`'39%' }],`** → `SyntaxError: Unexpected string`.

THE RULE: the end marker must sit at a **clean statement/expression boundary
AFTER the entire block you're replacing**, never mid-literal. For a value
inside an object, anchor the end marker on the NEXT structural token — here the
fix was `"\n        };\n      })()"` (the closing of the enclosing `ins:` IIFE),
so the preserved tail starts at `};` not at an orphan array fragment. This is a
DISTINCT bug from the already-documented "end marker repeated in the
replacement string doubles `};`" trap — here the marker is too SHALLOW
(mid-expression) rather than duplicated.

## TRAP 2 — server-side build success is NOT proof of valid JS

`python -c "import server; server._build_global_data()"` exiting 0 only proves
the Python builders run and the `__RD_*` dict assembles. It says NOTHING about
whether the patched component JS parses. A broken `_replace_block` produces a
perfectly valid Python string that is invalid JavaScript — the server starts
clean, serves 200s, and the browser white-screens.

## THE GATE (run BEFORE every gated restart)

Extract the patched component JS and `node --check` it. This is the cheap,
deterministic proof that catches both traps above before they hit the browser.
See `scripts/check_patched_js.py` in this skill — run it from the served dir
with the hermes-agent venv:

    cd /root/projects/hermes-webui-new && \
    HERMES_HOME=/root/.hermes /usr/local/lib/hermes-agent/venv/bin/python \
    <skill>/scripts/check_patched_js.py

Exit 0 + "node --check: PASS" = safe to restart. A FAIL prints the exact line
(`node` reports the line number in the DECODED component JS, which maps to your
patch region). Fix the marker, re-run, only then arm the write-gate restart.

Post-restart, re-verify on the LIVE wire (not just the in-process patch): pull
the served page authenticated, extract `scripts[-1]` from the bundler template,
`node --check` THAT. A served 200 with a clean in-process check can still be a
stale build if the restart didn't actually reload — confirm
`ActiveEnterTimestamp` moved (see SKILL.md restart pitfall).

## Real-data sourcing notes for the common populate gaps (this host)

- **Profiles panel** → real profiles live in `~/.hermes/profiles/` (dir listing,
  `default` is implicit, not a subdir). Join run counts from kanban.db
  `task_runs GROUP BY profile`; running state from `tasks WHERE status='running'`.
- **Agents summary bar / Overview agent ring** → kanban.db `task_runs` by profile
  (already surfaced via `_agents_ops_for_ui` / `_ov_agents_for_ui`).
- **Overview chips ready/blocked, heatmap, day-streak** → consume the ALREADY
  INJECTED `window.__RD_KANBAN__` (task status counts) and `window.__RD_INS_DAYS__`
  (14-day message-per-day array) in the patched JS — no new endpoint needed.
- **Insights token in/out split** → state.db sessions `SUM(input_tokens)` /
  `SUM(output_tokens)` SEPARATELY (the existing builder only summed them). NB on
  this host `output_tokens` reads 0 for many sessions — faithfully reflect the DB,
  don't fabricate a plausible split.
- **Insights skills table** → tally `tasks.skills` (JSON-or-CSV column) from
  kanban.db, `Counter.most_common(5)`.
- **Intentionally-skip**: sysMetrics/sysData CPU/GPU/VRAM sparklines (no real
  source without a new `psutil` `/api/system` endpoint — that's a feature, not a
  populate); template-baked static subtitles (e.g. Agents header naming fixture
  workers) can't be patched without touching `standalone.html`.
