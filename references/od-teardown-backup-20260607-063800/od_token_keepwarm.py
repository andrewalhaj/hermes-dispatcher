#!/usr/bin/env python3
"""
od_token_keepwarm.py — keep the OD container's read-only OAuth token fresh.
=============================================================================

WHY
---
OD's claude runtime reads a READ-ONLY bind mount of /root/.claude-od (single-
writer design: the container physically cannot refresh the token, which kills
the dual-refresh race against host Hermes). The cost of read-only is that the
container can't refresh on its own — so THIS host-side job must keep the token
fresh and mirror it into the sidecar before OD ever sees an expired token.

WHAT IT DOES (every run)
------------------------
1. Reads /root/.claude/.credentials.json (host canonical, refreshed by Hermes).
2. If it expires within REFRESH_BUFFER_MIN, proactively refreshes it using
   Hermes' OWN logic (refresh_anthropic_oauth_pure + _write_claude_code_creds)
   — no new refresh implementation, just reuse.
3. Mirrors the (fresh) canonical creds -> /root/.claude-od/.credentials.json,
   chowned 1001:1001 0600, via atomic temp+replace.

SILENT WHEN HEALTHY: prints nothing, exits 0, unless it refreshed or hit an
error (so the no_agent cron stays quiet — watchdog pattern). Errors print to
stdout so the cron delivers them to the Cron Jobs channel.

Runs every 15 min; token life ~50 min, buffer 20 min => always fresh well
before any 5-30 min OD run could outlive it.
"""
import json
import os
import secrets
import shutil
import stat
import sys
import time

CANON = "/root/.claude/.credentials.json"
SIDECAR_DIR = "/root/.claude-od"
SIDECAR = SIDECAR_DIR + "/.credentials.json"
REFRESH_BUFFER_MIN = 20
UID = GID = 1001

msgs = []


def _read(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        return None


def _expires_ms(creds):
    try:
        return int(creds["claudeAiOauth"]["expiresAt"])
    except Exception:
        return 0


def _refresh_if_needed():
    """Reuse Hermes' own refresh path. Returns True if it refreshed."""
    creds = _read(CANON)
    if not creds:
        msgs.append(f"ERROR: canonical creds unreadable at {CANON}")
        return False
    now_ms = int(time.time() * 1000)
    exp = _expires_ms(creds)
    if exp and now_ms < (exp - REFRESH_BUFFER_MIN * 60_000):
        return False  # still fresh enough
    # Near expiry — refresh via Hermes' own functions.
    sys.path.insert(0, "/usr/local/lib/hermes-agent")
    try:
        from agent.anthropic_adapter import (
            refresh_anthropic_oauth_pure,
            _write_claude_code_credentials,
        )
    except Exception as e:
        msgs.append(f"ERROR: cannot import Hermes refresh logic: {e}")
        return False
    rt = creds.get("claudeAiOauth", {}).get("refreshToken", "")
    if not rt:
        msgs.append("ERROR: no refreshToken in canonical creds")
        return False
    try:
        refreshed = refresh_anthropic_oauth_pure(rt, use_json=False)
        _write_claude_code_credentials(
            refreshed["access_token"],
            refreshed["refresh_token"],
            refreshed["expires_at_ms"],
        )
        msgs.append("refreshed canonical token (was within buffer)")
        return True
    except Exception as e:
        msgs.append(f"ERROR: refresh failed: {e}")
        return False


def _mirror_to_sidecar():
    """Copy canonical -> sidecar atomically, chown 1001, 0600."""
    canon = _read(CANON)
    side = _read(SIDECAR)
    if not canon:
        msgs.append("ERROR: canonical missing at mirror step")
        return
    # Skip write if identical (avoid needless churn)
    if side and _expires_ms(side) == _expires_ms(canon):
        return
    os.makedirs(SIDECAR_DIR, exist_ok=True)
    tmp = SIDECAR + f".tmp.{os.getpid()}.{secrets.token_hex(4)}"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                     stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w") as fh:
            json.dump(canon, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, SIDECAR)
        os.chown(SIDECAR, UID, GID)
        os.chmod(SIDECAR, stat.S_IRUSR | stat.S_IWUSR)
        try:
            os.chown(SIDECAR_DIR, UID, GID)
        except OSError:
            pass
        msgs.append("mirrored fresh token to sidecar")
    except OSError as e:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        msgs.append(f"ERROR: sidecar mirror failed: {e}")


def main():
    _refresh_if_needed()
    _mirror_to_sidecar()
    errors = [m for m in msgs if m.startswith("ERROR")]
    if errors:
        print("OD token keep-warm — issues:")
        for m in msgs:
            print("  " + m)
        sys.exit(1)
    # Healthy: silent unless an actual refresh happened (informational only,
    # still silent to keep the channel quiet — comment out next block if you
    # want refresh confirmations).
    sys.exit(0)


if __name__ == "__main__":
    main()
