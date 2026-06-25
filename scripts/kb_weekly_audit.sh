#!/bin/bash
# Weekly KB audit: dedup scan + pointer-coverage (orphan ratio) in one pass.
# Created 2026-06-09 (memory-architecture audit, greenlit by Andrew).
# Both probes are READ-ONLY. Output is delivered verbatim by the no-agent cron.
cd /root/.hermes
echo "=== KB Dedup Scan ==="
python3 scripts/dedup_scan.py 2>/dev/null
echo
echo "=== Pointer Coverage (orphan ratio; baseline 25%, alarm = rise >=15pt) ==="
python3 scripts/orphan_ratio.py 2>/dev/null | tail -8
