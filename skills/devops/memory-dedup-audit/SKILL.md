---
name: memory-dedup-audit
description: "Audit the Memory Honcho Dedup cron prompt."
category: devops
---

# Memory Honcho Dedup Audit

Weekly audit that validates the Memory Honcho Dedup cron job against the current system state. Reports drift to Cron Jobs channel. Read-only — never auto-patches.

## What it validates

1. **Cron prompt integrity** — does the dedup cron's prompt still reference the correct MEMORY.md path?
2. **MEMORY.md format** — is the '§' separator still valid? Has the file structure changed?
3. **Tool availability** — are `honcho_search`, `patch`, and `read_file` still available with expected signatures?
4. **Protection logic** — are the three safety conditions still present in the prompt?
5. **Schedule** — is the cron still on a reasonable frequency (daily)?

## Procedure

### STEP 1 — Read cron definition

```bash
cat ~/.hermes/cron/jobs.json | python3 -c "
import json, sys
jobs = json.load(sys.stdin)['jobs']
dedup = [j for j in jobs if j['name'].startswith('Memory Honcho Dedup')]
if not dedup:
    print('ERROR: Memory Honcho Dedup cron not found')
    sys.exit(1)
j = dedup[0]
print(f'ID: {j[\"id\"]}')
print(f'Schedule: {j[\"schedule\"][\"display\"]}')
print(f'Enabled: {j[\"enabled\"]}')
print(f'Toolsets: {j[\"enabled_toolsets\"]}')
print(f'Model: {j[\"model\"]}')
print(f'Last run: {j[\"last_run_at\"]}')
print(f'Last status: {j[\"last_status\"]}')
# Extract prompt
prompt = j['prompt']
print(f'Prompt length: {len(prompt)} chars')
checks = {
    'MEMORY.md path reference': 'memories/MEMORY.md' in prompt,
    '§ split instruction': '§' in prompt and 'split' in prompt.lower(),
    'honcho_search call': 'honcho_search' in prompt,
    'two-stage safety (flag first)': 'flag' in prompt.lower() and '3 day' in prompt.lower(),
    'content-based protection (no hardcoded list)': 'Do NOT use a hardcoded list' in prompt,
    'three safety conditions present': 'does NOT contain hard constraints' in prompt,
    'patch tool for edits': 'patch(old_string' in prompt,
    'audit-log.md reference': 'audit-log.md' in prompt,
    'SILENT response on clean run': '[SILENT]' in prompt,
}
for check, result in checks.items():
    status = 'PASS' if result else 'FAIL'
    print(f'  [{status}] {check}')
"
```

### STEP 2 — Validate MEMORY.md

```bash
python3 -c "
import os, sys, yaml
path = os.path.expanduser('~/.hermes/memories/MEMORY.md')
if not os.path.exists(path):
    print('ERROR: MEMORY.md not found at', path)
    sys.exit(1)
with open(path) as f:
    content = f.read()
cap = yaml.safe_load(open(os.path.expanduser('~/.hermes/config.yaml')))['memory']['memory_char_limit']
entries = content.split('§')
print(f'Entries: {len(entries)}')
print(f'Size: {len(content)} chars ({len(content)/cap*100:.0f}% of {cap} limit)')
# Check for existing flags
flags = [e for e in entries if '[HONCHO_DUP:' in e]
if flags:
    print(f'Flagged entries: {len(flags)}')
    for f in flags[:5]:
        print(f'  - {f.strip()[:120]}...')
else:
    print('No flagged entries')
"
```

### STEP 3 — Report

Aggregate STEP 1 and STEP 2 results. If ALL checks pass and MEMORY.md is healthy: respond `[SILENT]` — nothing to report. If any check FAILS: send a brief report to Cron Jobs channel listing only the failures, with the prefix `🔍 DEDUP AUDIT:`.

## Pitfalls

- The cron job's `prompt` field is stored as escaped JSON — direct grep of jobs.json will miss escaped characters. Always parse with python3's json module.
- MEMORY.md path may change if Hermes restructures its profile directory layout. The audit catches this.
- Honcho tool names may change during Hermes upgrades. The audit checks for `honcho_search` by name.
- The three safety conditions (hard constraints, technical config, same detail level) are the core protection mechanism. If these are missing or altered, the dedup could delete load-bearing entries.
- This skill is READ-ONLY. It reports drift but never patches the cron. Patching requires explicit user greenlight.

## Trigger

Load this skill weekly via cron: `0 8 * * 0` (Sunday 08:00 UTC). The cron job prompts: "Load skill memory-dedup-audit. Execute its STEP 1 and STEP 2 procedures. Report failures only to Cron Jobs channel."
