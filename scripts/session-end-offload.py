#!/usr/bin/env python3
"""
session-end-offload.py — probe MEMORY.md and store offload candidates to Supabase.

Called by the on_session_end shell hook when a conversation ends.
Does NOT trim MEMORY.md — that requires LLM judgment and stays with the
hourly cron / in-session memory_checkpoint.py nudge.

What it does:
  1. Read MEMORY.md size vs cap from config.yaml (live, not injected header)
  2. Gate at THRESHOLD% — exit silently if below
  3. Run offload_probe.py scan --json to identify TRIM-SAFE + POINTER entries
  4. Call knowledge.py store for each candidate → Supabase pgvector
  5. Append one-line entry to references/memory-offload-audit-log.md
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys

# ── Config ────────────────────────────────────────────────────────────────────

HERMES_HOME   = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
VENV_PY       = "/usr/local/lib/hermes-agent/venv/bin/python3"
SCRIPTS       = os.path.join(HERMES_HOME, "scripts")
CONFIG        = os.path.join(HERMES_HOME, "config.yaml")
MEMORY        = os.path.join(HERMES_HOME, "memories", "MEMORY.md")
AUDIT_LOG     = os.path.join(HERMES_HOME, "references", "memory-offload-audit-log.md")
THRESHOLD_PCT = int(os.environ.get("HERMES_OFFLOAD_THRESHOLD", "85"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_mem_cap() -> int:
    try:
        import yaml  # type: ignore
        with open(CONFIG, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return int((cfg.get("memory") or {}).get("memory_char_limit", 3000))
    except Exception:
        return 3000


def _mem_pct(cap: int) -> tuple[int, int]:
    """Return (chars, pct)."""
    try:
        size = len(open(MEMORY, encoding="utf-8").read())
        return size, round(size * 100 / cap)
    except FileNotFoundError:
        return 0, 0
    except Exception:
        return 0, 0


def _log(line: str) -> None:
    try:
        os.makedirs(os.path.dirname(AUDIT_LOG), exist_ok=True)
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    cap = _read_mem_cap()
    size, pct = _mem_pct(cap)

    if pct < THRESHOLD_PCT:
        return  # below threshold — silent exit

    # Run offload probe
    try:
        probe = subprocess.run(
            [VENV_PY, os.path.join(SCRIPTS, "offload_probe.py"), "--json", "scan"],
            capture_output=True, text=True, cwd=HERMES_HOME, timeout=120,
        )
    except Exception as exc:
        _log(f"- {_ts()}: session-end hook ERROR (probe failed): {exc}")
        return

    if probe.returncode != 0 or not probe.stdout.strip():
        _log(f"- {_ts()}: session-end hook — probe returned no output (mem={pct}%)")
        return

    try:
        data = json.loads(probe.stdout)
    except json.JSONDecodeError as exc:
        _log(f"- {_ts()}: session-end hook ERROR (json parse): {exc}")
        return

    # Store TRIM-SAFE + POINTER candidates
    stored = failed = skipped = 0
    env = {
        **os.environ,
        "KNOWLEDGE_TAGS": "memory,offload,session-end",
        "KNOWLEDGE_PRIORITY": "high",
    }

    for verdict in ("TRIM-SAFE", "POINTER"):
        for item in data.get(verdict, []):
            fact = (item.get("fact") or "").strip()
            if not fact:
                skipped += 1
                continue
            try:
                r = subprocess.run(
                    [VENV_PY, os.path.join(SCRIPTS, "knowledge.py"), "store", fact],
                    capture_output=True, text=True, cwd=HERMES_HOME,
                    env=env, timeout=30,
                )
                if r.returncode == 0:
                    stored += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

    summary = data.get("summary", {})
    _log(
        f"- {_ts()}: session-end hook — mem={summary.get('current_pct', pct)}% "
        f"({size}/{cap}), stored={stored} TRIM-SAFE/POINTER entries to Supabase, "
        f"failed={failed}, skipped={skipped}. "
        f"KEEP-HOT={len(data.get('KEEP-HOT', []))}. "
        f"(trimming deferred to cron)"
    )


def _ts() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


if __name__ == "__main__":
    main()
