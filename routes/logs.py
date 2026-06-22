import asyncio
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()

HERMES_HOME = Path(os.environ.get("HERMES_HOME", "/root/.hermes"))
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mABCDEFGHJKLMSTfhilmnprsu]")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _tail(path: Path, n: int) -> list[str]:
    """Return last n lines from path, stripping ANSI."""
    try:
        lines = path.read_text(errors="replace").splitlines()
        return [_strip_ansi(l) for l in lines[-n:]]
    except (OSError, IOError):
        return []


def _newest_log(directory: Path) -> Path | None:
    """Return the newest *.log file in directory (top-level only)."""
    try:
        logs = list(directory.glob("*.log"))
        if not logs:
            return None
        return max(logs, key=lambda p: p.stat().st_mtime)
    except (OSError, IOError):
        return None


def _get_lines(source: str, lines: int) -> list[str]:
    if source == "hermes":
        log_dir = HERMES_HOME / "logs"
        # Prefer agent.log + gateway.log specifically; fall back to newest *.log
        preferred = ["agent.log", "gateway.log"]
        result: list[str] = []
        for name in preferred:
            p = log_dir / name
            if p.exists():
                result.extend(_tail(p, lines // len(preferred)))
        if not result:
            newest = _newest_log(log_dir)
            if newest:
                result = _tail(newest, lines)
        return result

    if source == "kanban":
        log_dir = HERMES_HOME / "kanban" / "logs"
        try:
            log_files = sorted(log_dir.glob("*.log"), key=lambda p: p.name)
        except (OSError, IOError):
            return []
        result: list[str] = []
        for lf in log_files:
            prefix = f"[{lf.name}] "
            result.extend(prefix + l for l in _tail(lf, 50))
        return result

    if source == "system":
        try:
            proc = subprocess.run(
                ["journalctl", "-u", "hermes-dashboard", "--no-pager", "-n", "100"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode != 0:
                return []
            return [_strip_ansi(l) for l in proc.stdout.splitlines()]
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return []

    return []


@router.get("/logs")
async def get_logs(source: str = "hermes", lines: int = 200) -> dict:
    source = source.lower()
    if source not in ("hermes", "kanban", "system"):
        source = "hermes"
    lines = max(1, min(lines, 5000))
    return {
        "lines": _get_lines(source, lines),
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/logs/stream")
async def stream_logs(source: str = "hermes") -> StreamingResponse:
    source = source.lower()

    # Resolve the file to tail once at stream start.
    if source == "hermes":
        log_dir = HERMES_HOME / "logs"
        target = _newest_log(log_dir)
    else:
        target = None  # streaming only supported for hermes; others get heartbeats only

    async def event_generator():
        offset = 0
        if target is not None and target.exists():
            offset = target.stat().st_size

        try:
            while True:
                await asyncio.sleep(1)
                if target is None or not target.exists():
                    yield ": keepalive\n\n"
                    continue
                try:
                    size = target.stat().st_size
                except OSError:
                    yield ": keepalive\n\n"
                    continue

                if size > offset:
                    try:
                        with target.open("rb") as fh:
                            fh.seek(offset)
                            chunk = fh.read(size - offset)
                        offset = size
                        raw = chunk.decode(errors="replace")
                        new_lines = raw.splitlines()
                        for line in new_lines:
                            clean = _strip_ansi(line)
                            payload = json.dumps({"line": clean})
                            yield f"data: {payload}\n\n"
                    except OSError:
                        yield ": keepalive\n\n"
                else:
                    # File truncated / rotated — reset offset
                    if size < offset:
                        offset = size
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
