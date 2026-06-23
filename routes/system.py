"""Lightweight live system-metrics endpoint for the dashboard System Monitor tile.

Polled by the frontend every ~3s. Kept deliberately cheap (no DB joins, no
blocking psutil intervals) so it can be hit frequently without taxing the host.
GPU/VRAM degrade gracefully to ``None`` when nvidia-smi is unavailable.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

import psutil
from fastapi import APIRouter

router = APIRouter()

KANBAN_DB = Path(os.environ.get("KANBAN_DB", "/root/.hermes/kanban.db"))

# Remote machine (Mac Studio) reachable over Tailscale via SSH.
STUDIO_HOST = os.environ.get("STUDIO_HOST", "100.93.2.43")
STUDIO_USER = os.environ.get("STUDIO_USER", "localadmin")

# Module-level state for computing network throughput as a delta between polls.
_last_net: dict[str, float] = {"ts": 0.0, "bytes": 0.0}
# Separate delta state for the remote Studio's network counters.
_last_net_studio: dict[str, float] = {"ts": 0.0, "bytes": 0.0}
# Cache the nvidia-smi availability probe so we don't shell out on every request.
_HAS_NVIDIA_SMI = shutil.which("nvidia-smi") is not None


def _open_ro() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{KANBAN_DB}?mode=ro", uri=True)


def _network_mbps(state: dict[str, float] | None = None, total: float | None = None) -> float:
    """Total (sent+recv) network throughput in MB/s since the previous poll.

    ``state`` defaults to the local mini delta dict; pass ``_last_net_studio``
    (and the remote ``total`` byte count) to compute the Studio's throughput.
    """
    if state is None:
        state = _last_net
    if total is None:
        counters = psutil.net_io_counters()
        total = float(counters.bytes_sent + counters.bytes_recv)
    now = time.time()
    prev_ts = state["ts"]
    prev_bytes = state["bytes"]
    state["ts"] = now
    state["bytes"] = total
    if prev_ts == 0.0:
        return 0.0
    elapsed = now - prev_ts
    if elapsed <= 0:
        return 0.0
    return round((total - prev_bytes) / elapsed / (1024 * 1024), 2)


def _gpu_stats() -> dict:
    """Return GPU util %% and VRAM used %% via nvidia-smi, or None values if absent."""
    if not _HAS_NVIDIA_SMI:
        return {"gpu_pct": None, "vram_pct": None}
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return {"gpu_pct": None, "vram_pct": None}
        # First GPU only.
        line = out.stdout.strip().splitlines()[0]
        util, used, total = (p.strip() for p in line.split(","))
        gpu_pct = round(float(util), 1)
        vram_pct = round(float(used) / float(total) * 100, 1) if float(total) else None
        return {"gpu_pct": gpu_pct, "vram_pct": vram_pct}
    except (subprocess.SubprocessError, ValueError, IndexError):
        return {"gpu_pct": None, "vram_pct": None}


def _agent_memory() -> list:
    """Per-agent RSS (MB), keyed by profile / gateway. Mirrors overview route logic."""
    try:
        results: dict[str, int] = {}
        for proc in psutil.process_iter(["pid", "cmdline", "memory_info"]):
            try:
                cmdline = proc.info.get("cmdline") or []
                mem = proc.info.get("memory_info")
                if mem is None or not cmdline:
                    continue
                label = None
                for i, part in enumerate(cmdline):
                    if part in ("-p", "--profile") and i + 1 < len(cmdline):
                        candidate = cmdline[i + 1]
                        if len(candidate) <= 64 and " " not in candidate:
                            label = candidate
                        break
                if label is None:
                    cmdstr = " ".join(cmdline)
                    if "gateway" in cmdstr and "run" in cmdstr:
                        label = "gateway"
                    elif any("hermes_cli" in p or "hermes.main" in p for p in cmdline):
                        label = os.path.basename(cmdline[0])
                if label is None:
                    continue
                rss_mb = mem.rss // (1024 * 1024)
                results[label] = results.get(label, 0) + rss_mb
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        sorted_items = sorted(results.items(), key=lambda x: x[1], reverse=True)[:6]
        return [{"name": k, "rss_mb": v} for k, v in sorted_items]
    except Exception:
        return []


def _running_agents() -> list:
    """Names of agents (profiles) with running kanban tasks — the 'agents' list."""
    try:
        conn = _open_ro()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT assignee, COUNT(*) FROM tasks"
                " WHERE status='running' AND assignee IS NOT NULL"
                " GROUP BY assignee ORDER BY COUNT(*) DESC"
            )
            return [{"name": r[0], "tasks": r[1]} for r in cur.fetchall()]
        finally:
            conn.close()
    except Exception:
        return []


@router.get("/system")
async def get_system(machine: str = "mini") -> dict:
    """Cheap live system snapshot for the System Monitor tile (polled ~3s).

    ``machine=mini`` (default) reads local psutil metrics. ``machine=studio``
    fetches the remote Mac Studio's metrics over SSH (Tailscale). The running
    agents list is always sourced from the local kanban DB regardless of machine.
    """
    if machine == "studio":
        snapshot = await asyncio.get_event_loop().run_in_executor(
            None, _fetch_studio_metrics
        )
        snapshot["running_agents"] = _running_agents()
        return snapshot

    cpu = round(psutil.cpu_percent(interval=0.0), 1)
    vmem = psutil.virtual_memory()
    disk = psutil.disk_usage("/").percent
    gpu = _gpu_stats()

    return {
        "machine": "mini",
        "error": None,
        "cpu_pct": cpu,
        "mem_pct": round(vmem.percent, 1),
        "mem_used_gb": round(vmem.used / (1024 ** 3), 1),
        "mem_total_gb": round(vmem.total / (1024 ** 3), 1),
        "disk_pct": round(disk, 1),
        "net_mbps": _network_mbps(),
        "gpu_pct": gpu["gpu_pct"],
        "vram_pct": gpu["vram_pct"],
        "agent_memory": _agent_memory(),
        "running_agents": _running_agents(),
    }


def _unreachable_studio() -> dict:
    """Studio snapshot with all metrics None — returned when SSH fails."""
    return {
        "machine": "studio",
        "error": "unreachable",
        "cpu_pct": None,
        "mem_pct": None,
        "mem_used_gb": None,
        "mem_total_gb": None,
        "disk_pct": None,
        "net_mbps": None,
        "gpu_pct": None,
        "vram_pct": None,
        "agent_memory": [],
        "running_agents": [],
    }


# Remote probe script, executed on the Studio via `python3 -` (fed over stdin so
# no shell quoting of the Python source is needed). GPU/VRAM are best-effort via
# nvidia-smi; Apple Silicon has none, so they degrade to None.
_STUDIO_PROBE = r"""
import json, psutil, shutil, subprocess
c = psutil.cpu_percent(interval=0.2)
m = psutil.virtual_memory()
n = psutil.net_io_counters()
g = v = None
try:
    if shutil.which("nvidia-smi"):
        o = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2)
        if o.returncode == 0 and o.stdout.strip():
            u, us, t = [x.strip() for x in o.stdout.strip().splitlines()[0].split(",")]
            g = round(float(u), 1)
            v = round(float(us) / float(t) * 100, 1) if float(t) else None
except Exception:
    g = v = None
print(json.dumps({
    "cpu": c, "mem_pct": m.percent,
    "mem_used_gb": round(m.used / 1e9, 1),
    "mem_total_gb": round(m.total / 1e9, 1),
    "net_bytes": n.bytes_sent + n.bytes_recv,
    "gpu_pct": g, "vram_pct": v,
}))
"""


def _fetch_studio_metrics() -> dict:
    """Fetch Mac Studio metrics over SSH (Tailscale). Blocking — run in executor.

    A single SSH round-trip runs ``_STUDIO_PROBE`` on the remote (CPU/mem/net +
    best-effort GPU/VRAM). On any SSH/parse failure returns an
    ``error="unreachable"`` snapshot with all metrics ``None`` rather than
    raising, so the route never 500s.
    """
    try:
        out = subprocess.run(
            [
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=3",
                "-o", "BatchMode=yes",
                "-i", "/root/.ssh/id_ed25519",
                f"{STUDIO_USER}@{STUDIO_HOST}",
                "python3 -",
            ],
            input=_STUDIO_PROBE,
            capture_output=True,
            text=True,
            timeout=4,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return _unreachable_studio()
        data = json.loads(out.stdout.strip().splitlines()[-1])
    except (subprocess.SubprocessError, ValueError, json.JSONDecodeError, OSError):
        return _unreachable_studio()

    net_mbps = _network_mbps(_last_net_studio, float(data.get("net_bytes", 0.0)))

    return {
        "machine": "studio",
        "error": None,
        "cpu_pct": round(float(data["cpu"]), 1),
        "mem_pct": round(float(data["mem_pct"]), 1),
        "mem_used_gb": data.get("mem_used_gb"),
        "mem_total_gb": data.get("mem_total_gb"),
        "disk_pct": None,
        "net_mbps": net_mbps,
        "gpu_pct": data.get("gpu_pct"),
        "vram_pct": data.get("vram_pct"),
        "agent_memory": [],
    }
