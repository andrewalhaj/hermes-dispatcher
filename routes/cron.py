"""Cron jobs API — exposes scheduled cron jobs as selectable "channels" and
their most-recent run output as a read-only message feed for the Chat panel.

Mounted with: app.include_router(cron.router)   (router already carries the
/api/cron prefix).

Data sources (real shapes, verified 2026-06-23):
  - /root/.hermes/cron/jobs.json   ->  {"jobs": [ {id, name, schedule:{display|expr}, enabled, ...}, ... ]}
  - /root/.hermes/cron/output/<job_id>/<YYYY-MM-DD_HH-MM-SS>.md   (one file per run)
    The newest .md file in the job's dir is the latest run output.
"""
import json
import os
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/cron")

_HERMES_HOME = Path(os.environ.get("HERMES_HOME", "/root/.hermes"))
# HERMES_HOME may point at a profile subdir in worker contexts; cron lives at
# the top-level hermes home, so resolve it explicitly with a fallback.
JOBS = _HERMES_HOME / "cron" / "jobs.json"
if not JOBS.exists():
    JOBS = Path("/root/.hermes/cron/jobs.json")
OUTPUT_DIR = JOBS.parent / "output"


def _schedule_str(j: dict) -> str:
    sched = j.get("schedule")
    if isinstance(sched, dict):
        return str(sched.get("display") or sched.get("expr") or "")
    if isinstance(sched, str):
        return sched
    return str(j.get("schedule_display") or j.get("cron") or "")


@router.get("")
def list_cron():
    try:
        data = json.loads(JOBS.read_text())
    except Exception:
        return []
    jobs = data if isinstance(data, list) else data.get("jobs", [])
    out = []
    for j in jobs:
        jid = j.get("id") or j.get("job_id") or j.get("name")
        out.append({
            "id": jid,
            "name": j.get("name") or jid or "cron job",
            "schedule": _schedule_str(j),
            "enabled": j.get("enabled", True),
            "lastStatus": j.get("last_status") or "",
            "lastRunAt": j.get("last_run_at") or "",
        })
    return out


def _latest_output_file(job_id: str) -> Path | None:
    if not OUTPUT_DIR.exists():
        return None
    job_dir = OUTPUT_DIR / job_id
    candidates: list[Path] = []
    if job_dir.is_dir():
        candidates = [p for p in job_dir.glob("*.md") if p.is_file()]
        if not candidates:
            candidates = [p for p in job_dir.iterdir() if p.is_file()]
    else:
        # Fallback: a flat <job_id>.log file, or any path containing the id.
        flat = OUTPUT_DIR / f"{job_id}.log"
        if flat.is_file():
            return flat
        candidates = [p for p in OUTPUT_DIR.glob(f"*{job_id}*") if p.is_file()]
    if not candidates:
        return None
    # Newest by mtime (filenames are timestamped, but mtime is authoritative).
    return max(candidates, key=lambda p: p.stat().st_mtime)


@router.get("/output")
def all_cron_output():
    """Return recent output from ALL cron jobs, merged and sorted newest-first."""
    if not OUTPUT_DIR.exists():
        return []

    messages = []
    for job_dir in OUTPUT_DIR.iterdir():
        if not job_dir.is_dir():
            continue
        job_id = job_dir.name
        outputs = sorted(job_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not outputs:
            continue
        latest = outputs[0]
        try:
            text = latest.read_text(errors="ignore")[:4000]
        except Exception:
            continue
        mtime = latest.stat().st_mtime
        messages.append({
            "role": "assistant",
            "content": text,
            "created_at": mtime,
            "job_id": job_id,
            "file": latest.name,
        })

    messages.sort(key=lambda m: m["created_at"], reverse=True)
    return messages[:20]


@router.get("/{job_id}/output")
def cron_output(job_id: str):
    """Return the most recent run output for a cron job as read-only messages."""
    f = _latest_output_file(job_id)
    if not f or not f.exists():
        return []
    try:
        text = f.read_text(errors="ignore")[-12000:]
    except Exception:
        return []
    return [{"role": "assistant", "content": text, "created_at": f.name}]
