#!/usr/bin/env python3
"""Hermes memory headroom watchdog.

Checks MEMORY.md and USER.md against their character caps (read live from
config.yaml).  Prints an alert line for each store at >= 90 % of its cap.
Silent (stdout empty, exit 0) when both stores are below 90 % — designed for
a no_agent cron that delivers stdout verbatim.
"""

import sys
import os

import yaml

HERMES_DIR = os.path.expanduser("~/.hermes")
CONFIG_PATH = os.path.join(HERMES_DIR, "config.yaml")
MEMORY_PATH = os.path.join(HERMES_DIR, "memories", "MEMORY.md")
USER_PATH = os.path.join(HERMES_DIR, "memories", "USER.md")

THRESHOLD_PCT = 90.0


def _die(msg: str) -> None:
    """Print *msg* to stdout (so cron can surface it) and exit 1."""
    print(msg)
    sys.exit(1)


def _read_chars(path: str) -> int:
    """Return character count of *path* (len of file text, matching ``wc -m``)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return len(fh.read())
    except FileNotFoundError:
        _die(f"WATCHDOG ERROR: file not found: {path}")
    except Exception as exc:
        _die(f"WATCHDOG ERROR: cannot read {path}: {exc}")


def _read_cap(config_path: str, key: str) -> int:
    """Read a numeric cap from config.yaml under the 'memory' key."""
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
    except FileNotFoundError:
        _die(f"WATCHDOG ERROR: config not found: {config_path}")
    except Exception as exc:
        _die(f"WATCHDOG ERROR: cannot parse {config_path}: {exc}")

    memory = cfg.get("memory")
    if memory is None:
        _die("WATCHDOG ERROR: missing 'memory' section in config.yaml")
    val = memory.get(key)
    if val is None:
        _die(f"WATCHDOG ERROR: missing 'memory.{key}' in config.yaml")
    try:
        return int(val)
    except (TypeError, ValueError):
        _die(f"WATCHDOG ERROR: memory.{key} is not numeric: {val!r}")


def main() -> None:
    mem_cap = _read_cap(CONFIG_PATH, "memory_char_limit")
    usr_cap = _read_cap(CONFIG_PATH, "user_char_limit")

    mem_chars = _read_chars(MEMORY_PATH)
    usr_chars = _read_chars(USER_PATH)

    mem_pct = mem_chars / mem_cap * 100
    usr_pct = usr_chars / usr_cap * 100

    alerts = []
    if mem_pct >= THRESHOLD_PCT:
        alerts.append(
            f"MEMORY: {mem_chars}/{mem_cap} chars ({mem_pct:.1f}%)"
        )
    if usr_pct >= THRESHOLD_PCT:
        alerts.append(
            f"USER: {usr_chars}/{usr_cap} chars ({usr_pct:.1f}%)"
        )

    if alerts:
        print("\n".join(alerts))
        print("Action: compact inline — pointer-ize cold entries to a reference doc")

    sys.exit(0)


if __name__ == "__main__":
    main()
