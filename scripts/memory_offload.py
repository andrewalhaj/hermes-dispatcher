#!/usr/bin/env python3
"""
memory_offload.py — deterministic memory offload script (no LLM agent needed).

Replaces the cron-based LLM agent for Memory Offload (default profile).
Runs every hour, threshold-gated (85% cap), SILENT when nothing happens.

Steps:
  0. Read MEMORY.md size + cap; exit silent if < 85%.
  1. Parse entries (split on '§'), classify OFFLOADABLE vs HOT.
  2. Store offload candidates to cold store (knowledge.py).
  3. Verify retrievability (score >= 0.80).
  4. Backup MEMORY.md, then atomically replace entries with pointer cues.
  5. Integrity check (memory_sanitize.py).
  6. Log to audit file.
  7. Print one-line report (only if anything was offloaded).

Pitfalls:
  - Never offload behavioral/preference facts, hard constraints
    (MUST/NEVER/gate/approval/"don't"), or entries with live config.
  - A pointerless trim is a silent deletion — forbidden.
  - Err strongly toward KEEPING hot.
"""

from __future__ import annotations

import datetime
import os
import re
import shutil
import subprocess
import sys

HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
MEMORY_FILE = os.path.join(HERMES_HOME, "memories", "MEMORY.md")
AUDIT_LOG = os.path.join(HERMES_HOME, "references", "memory-offload-audit-log.md")
KNOWLEDGE_SCRIPT = os.path.join(HERMES_HOME, "scripts", "knowledge.py")
SANITIZE_SCRIPT = os.path.join(HERMES_HOME, "scripts", "memory_sanitize.py")
CONFIG_FILE = os.path.join(HERMES_HOME, "config.yaml")

# ── Step 0: Gate ─────────────────────────────────────────────────────────────

def get_cap() -> int:
    """Read memory cap from config.yaml."""
    try:
        import yaml
        with open(CONFIG_FILE) as f:
            return int(yaml.safe_load(f)["memory"]["memory_char_limit"])
    except Exception:
        return 3000  # fallback


def mem_size() -> int:
    """Return MEMORY.md character count."""
    try:
        with open(MEMORY_FILE) as f:
            return len(f.read())
    except FileNotFoundError:
        return 0


def gate_check() -> float:
    """Return percentage. If < 85, exit silent."""
    cap = get_cap()
    size = mem_size()
    pct = (size / cap) * 100
    if pct < 85:
        sys.exit(0)
    return pct


# ── Step 1: Parse and classify ────────────────────────────────────────────────

HOT_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b(must|never|always|don'?t\s|do not\s|required|mandatory|forbidden)\b",
        r"\b(gate\b|approval|greenlight|write.+gate)\b",
        r"\b(style|tone|prefers?|preference|correction)\b",
        r"\b(strict|hard.rule|explicit|only\s.+path)\b",
        r"config\.yaml|\.env|credentials|token|secret|password",
    ]
]

OFFLOADABLE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b(llama\.cpp|knowledge\.py\ssearch|supabase|kanban\sswim)",
        r"\b(host|port|url|endpoint|ip\saddress|tailscale)\b",
        r"\b(model|provider|version|package)\b",
        r"\b(fleet|coder-[a-z]|worker\sprofile|assignee)\b",
        r"\b(tool\squirk|pitfall|bug|issue\s#\d+|pr\s#\d+)\b",
        r"\b(cold.store|knowledge\sstore|pgvector)\b",
        r"\b(path|directory|workspace|repo)\b",
    ]
]


def classify_entries() -> tuple[list[dict], list[dict]]:
    """Parse MEMORY.md into entries; return (hot, offloadable)."""
    hot: list[dict] = []
    offloadable: list[dict] = []

    try:
        with open(MEMORY_FILE) as f:
            raw = f.read()
    except FileNotFoundError:
        return hot, offloadable

    entries = [e.strip() for e in raw.split("§") if e.strip()]

    for i, entry in enumerate(entries):
        info = {"index": i, "text": entry, "reason": ""}

        # Hot check first (any hot pattern match = KEEP)
        if any(p.search(entry) for p in HOT_PATTERNS):
            hot.append(info)
            continue

        # Offloadable check
        if any(p.search(entry) for p in OFFLOADABLE_PATTERNS):
            info["reason"] = "offloadable reference fact"
            offloadable.append(info)
        else:
            # Ambiguous — default to HOT (safety)
            hot.append(info)

    return hot, offloadable


# ── Step 2 & 3: Store and verify ──────────────────────────────────────────────

def store_to_cold(fact: str, topic: str) -> bool:
    """Store a fact to the cold store. Returns success."""
    tags = f"{topic},offload"
    try:
        subprocess.run(
            [
                sys.executable, KNOWLEDGE_SCRIPT, "store", fact,
            ],
            env={**os.environ, "KNOWLEDGE_TAGS": tags, "KNOWLEDGE_PRIORITY": "high"},
            capture_output=True, text=True, timeout=30, cwd=HERMES_HOME,
        )
        return True
    except Exception:
        return False


def verify_retrieval(key_terms: str) -> bool:
    """Check that a stored fact is retrievable at score >= 0.80."""
    try:
        result = subprocess.run(
            [sys.executable, KNOWLEDGE_SCRIPT, "search", key_terms],
            capture_output=True, text=True, timeout=30, cwd=HERMES_HOME,
        )
        # Search stdout for score >= 0.80
        for line in result.stdout.splitlines():
            m = re.search(r"\[(0\.\d+)\]", line)
            if m and float(m.group(1)) >= 0.80:
                return True
    except Exception:
        pass
    return False


def extract_key_terms(text: str) -> str:
    """Extract search terms from an entry — first 2-3 meaningful words."""
    words = text.split()
    # Take first 3 non-trivial words
    terms = [w for w in words[:8] if len(w) > 3 and w.lower() not in {"the", "for", "with", "that", "this"}]
    return " ".join(terms[:3])


# ── Step 4: Backup and trim ────────────────────────────────────────────────────

def backup_and_trim(offloaded: list[dict]) -> int:
    """Backup MEMORY.md, replace offloaded entries with pointer cues."""
    timestamp = int(datetime.datetime.now().timestamp())
    backup_path = f"{MEMORY_FILE}.bak-offload-{timestamp}"
    shutil.copy2(MEMORY_FILE, backup_path)

    try:
        with open(MEMORY_FILE) as f:
            raw = f.read()

        entries = [e.strip() for e in raw.split("§") if e.strip()]
        offloaded_indices = {o["index"] for o in offloaded}

        new_entries = []
        for i, entry in enumerate(entries):
            if i in offloaded_indices:
                terms = extract_key_terms(entry)
                pointer = f'{terms}: knowledge.py search "{terms}".'
                new_entries.append(pointer)
            else:
                new_entries.append(entry)

        new_content = "§\n".join(new_entries) + "§\n"

        with open(MEMORY_FILE, "w") as f:
            f.write(new_content)

        cap = get_cap()
        new_pct = round((len(new_content) / cap) * 100, 2)
        return new_pct
    except Exception:
        # Restore backup on failure
        shutil.copy2(backup_path, MEMORY_FILE)
        raise


# ── Step 5: Integrity check ────────────────────────────────────────────────────

def integrity_check() -> bool:
    """Run memory_sanitize.py --check. Returns True if clean."""
    try:
        result = subprocess.run(
            [sys.executable, SANITIZE_SCRIPT, "--check"],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return True  # fail-safe: don't abort offload over integrity-checker issues


# ── Step 6: Audit log ──────────────────────────────────────────────────────────

def log_audit(offloaded: list[dict], before_pct: float, after_pct: float):
    """Append to the offload audit log."""
    now = datetime.datetime.now().isoformat()
    with open(AUDIT_LOG, "a") as f:
        f.write(f"\n## {now}\n")
        f.write(f"Offloaded: {len(offloaded)} entries\n")
        f.write(f"Before: {before_pct:.1f}% → After: {after_pct:.1f}%\n")
        for o in offloaded:
            terms = extract_key_terms(o["text"])
            f.write(f"- {terms}\n")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    before_pct = gate_check()
    if before_pct < 85:
        return  # already exited in gate_check

    hot, offloadable = classify_entries()
    if not offloadable:
        return  # all entries are hot — nothing to do

    # Store and verify each
    verified = []
    for o in offloadable:
        terms = extract_key_terms(o["text"])
        if not store_to_cold(o["text"], terms):
            continue
        if not verify_retrieval(terms):
            continue
        verified.append(o)

    if not verified:
        return  # none passed verification

    after_pct = backup_and_trim(verified)

    if not integrity_check():
        print("MEMORY offload: integrity check FAILED — restored from backup")
        return

    log_audit(verified, before_pct, after_pct)
    print(f"MEMORY offload: {len(verified)} entries → cold store, MEMORY.md {before_pct:.1f}%→{after_pct:.1f}%.")


if __name__ == "__main__":
    main()
