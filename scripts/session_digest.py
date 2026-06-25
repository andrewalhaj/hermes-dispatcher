#!/usr/bin/env python3
"""Session Digest — dump the last N hours of real user/assistant conversation
from state.db as compact text, for a curation pass (cron or manual).

Excludes cron/system sessions and tool-result spam. Output is plain text
suitable for feeding to an LLM curation prompt or session_capture.py.

Usage:
  python3 session_digest.py [--hours 24] [--source telegram,cli,discord] [--max-chars 20000]
"""
import sqlite3, sys, time, argparse, html

DB = "/root/.hermes/state.db"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--source", default="telegram,cli,discord")  # exclude cron by default
    ap.add_argument("--max-chars", type=int, default=20000)
    args = ap.parse_args()

    sources = [s.strip() for s in args.source.split(",") if s.strip()]
    cutoff = time.time() - args.hours * 3600

    con = sqlite3.connect(DB)
    cur = con.cursor()
    placeholders = ",".join("?" * len(sources))
    cur.execute(f"""
        SELECT id, source, title, started_at, message_count
        FROM sessions
        WHERE source IN ({placeholders})
          AND COALESCE(ended_at, started_at) >= ?
          AND message_count > 2
        ORDER BY started_at
    """, (*sources, cutoff))
    sessions = cur.fetchall()

    out = []
    for sid, source, title, started, mc in sessions:
        out.append(f"\n===== SESSION [{source}] {title or sid[:18]} ({mc} msgs) =====")
        cur.execute("""
            SELECT role, content FROM messages
            WHERE session_id=? AND role IN ('user','assistant')
              AND content IS NOT NULL AND content != ''
            ORDER BY timestamp
        """, (sid,))
        for role, content in cur.fetchall():
            c = (content or "").strip()
            if not c:
                continue
            # Skip system-reminder noise and pure-tool echoes
            if c.startswith("<system-reminder") or c.startswith("[CONTEXT COMPACTION"):
                continue
            c = c[:1500]  # cap per-message
            out.append(f"{role.upper()}: {c}")
    con.close()

    text = "\n".join(out)
    if len(text) > args.max_chars:
        text = text[-args.max_chars:]  # keep most recent
    print(text)

if __name__ == "__main__":
    main()
