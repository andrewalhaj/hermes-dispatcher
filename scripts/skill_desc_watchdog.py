#!/usr/bin/env python3
"""skill_desc_watchdog.py — silent-by-default watchdog for the 60-char skill
description cliff.

Runs the canonical audit (skill_desc_audit.py) over LOCAL PROFILE skills only,
filters to truncated offenders, and:
  - prints NOTHING when clean (cron no_agent => silent, no message sent)
  - prints a concise alert when any LIVE skill description is over the cliff

Scope decision (deliberate):
  - LOCAL profile skills only (~/.hermes/skills). Core builtins under
    /usr/local/lib/hermes-agent are excluded: editing them reverts on every
    `hermes update`, so an alert there would be an un-fixable false positive
    that trains the operator to ignore the watchdog.
  - Archived skills are already skipped by the audit's EXCLUDED set
    (.archive / .decommissioned), so retired skills never trip this.

Exit code is always 0 on a successful run (clean or dirty) — the ALERT is the
stdout payload, per the cron no_agent watchdog contract. Non-zero exit only on
a real failure (audit missing / crashed), which cron surfaces as an error.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

AUDIT = Path(
    "~/.hermes/skills/productivity/hermes-maintenance/scripts/skill_desc_audit.py"
).expanduser()


def main() -> int:
    if not AUDIT.exists():
        print(f"[skill-desc-watchdog] ERROR: audit tool missing at {AUDIT}",
              file=sys.stderr)
        return 1

    try:
        # No --all: local profile skills only (the ones we can durably fix).
        proc = subprocess.run(
            [sys.executable, str(AUDIT), "--json"],
            capture_output=True, text=True, timeout=120,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[skill-desc-watchdog] ERROR: audit failed to run: {e}",
              file=sys.stderr)
        return 1

    if proc.returncode != 0:
        print(f"[skill-desc-watchdog] ERROR: audit exited {proc.returncode}: "
              f"{proc.stderr.strip()[:300]}", file=sys.stderr)
        return 1

    try:
        rows = json.loads(proc.stdout)
    except Exception as e:  # noqa: BLE001
        print(f"[skill-desc-watchdog] ERROR: bad audit JSON: {e}",
              file=sys.stderr)
        return 1

    offenders = [r for r in rows if r.get("truncated")]
    if not offenders:
        # Clean — stay SILENT. Empty stdout => cron sends nothing.
        return 0

    # Dirty — emit a concise, actionable alert.
    lines = [
        f"⚠️ Skill description cliff: {len(offenders)} skill(s) over 60 chars "
        f"— trigger keyword is being TRUNCATED out of the system prompt.",
        "",
    ]
    for r in offenders:
        lines.append(f"• {r['name']} ({r['len']}c)")
        lines.append(f"    SEES: {r['shown']}")
        lost = (r.get("lost_tail") or "")[:90]
        if lost:
            lines.append(f"    LOST: {lost}{'…' if len(r.get('lost_tail') or '') > 90 else ''}")
    lines.append("")
    lines.append("FIX: front-load the trigger keyword into the first ~50 chars; "
                 "push rich detail into load_when: + body. "
                 "Verify: skill_desc_audit.py --check <name>")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
