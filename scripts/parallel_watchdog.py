#!/usr/bin/env python3
"""parallel_watchdog.py — silent-by-default guard against silent Parallel.ai
web re-exposure.

WHY THIS EXISTS
---------------
Hermes' web backend resolver (tools/web_tools.py `_get_backend`) hardcodes a
keyless ``("parallel", True)`` terminal default. If our explicit web config or
the web-parallel plugin-disable ever vanish — which a `hermes setup` reinstall
does, because it strips config.yaml — web_search/web_extract silently reroute
to ``search.parallel.ai/mcp``, shipping our queries + extracted page content to
a third party we never opted into. (Supply-chain issue: PR #43798 made Parallel
the undisclosed keyless default; upstream revert PR #46350.)

This watchdog asserts the two defense layers are intact and SELF-HEALS the
plugin-disable layer (idempotent, safe). It alerts when it heals or finds drift
so the operator knows a reinstall re-exposed the box.

CONTRACT (cron no_agent=True watchdog)
--------------------------------------
- Clean + nothing healed  -> print NOTHING, exit 0  (cron sends no message)
- Drift found / healed     -> print concise alert to stdout, exit 0
- Real failure (can't read config / heal failed) -> stderr + exit 1 (cron
  surfaces as an error alert; a broken watchdog must not fail silently)

The self-heal only touches the plugin-disable (reversible, `hermes plugins
enable web-parallel` undoes it). It does NOT write config.yaml (gated) — if the
web.backend/search_backend settings drift, it ALERTS for manual re-assert
rather than editing a gated file autonomously.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

CONFIG = Path("~/.hermes/config.yaml").expanduser()
PLUGIN_NAME = "web-parallel"
PLUGIN_DISABLED_KEY = "web/parallel"
# Acceptable web backends (anything that is NOT parallel). We assert the
# resolver won't fall through to the keyless parallel default.
SAFE_BACKENDS = {"firecrawl", "searxng", "tavily", "exa", "brave-free", "ddgs"}


def _load_config() -> dict:
    import yaml  # lazy; present in the hermes venv

    with open(CONFIG, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _plugin_disabled(cfg: dict) -> bool:
    disabled = (((cfg.get("plugins") or {}).get("disabled")) or [])
    return PLUGIN_DISABLED_KEY in disabled


def _backends_safe(cfg: dict) -> tuple[bool, str, str]:
    """Return (is_safe, backend, search_backend). Safe = neither resolves to
    parallel AND at least the shared backend is an explicit non-parallel value
    (so the resolver returns early before the keyless parallel candidate)."""
    web = cfg.get("web") or {}
    backend = (web.get("backend") or "").lower().strip()
    search = (web.get("search_backend") or "").lower().strip()
    # Explicit parallel anywhere = unsafe.
    if "parallel" in (backend, search):
        return False, backend, search
    # Shared backend must be an explicit safe value, else the resolver
    # auto-detects and can fall through to keyless parallel.
    safe = backend in SAFE_BACKENDS
    return safe, backend, search


def _heal_plugin_disable() -> tuple[bool, str]:
    """Re-disable the web-parallel plugin. Returns (healed, detail)."""
    hermes = shutil.which("hermes") or os.path.expanduser("~/.local/bin/hermes")
    try:
        proc = subprocess.run(
            [hermes, "plugins", "disable", PLUGIN_NAME],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as e:  # noqa: BLE001
        return False, f"heal failed to run: {e}"
    if proc.returncode != 0:
        return False, f"heal exited {proc.returncode}: {proc.stderr.strip()[:200]}"
    return True, proc.stdout.strip()[:200]


def main() -> int:
    try:
        cfg = _load_config()
    except Exception as e:  # noqa: BLE001
        print(f"[parallel-watchdog] ERROR: cannot read config: {e}",
              file=sys.stderr)
        return 1

    alerts: list[str] = []

    # Layer 1: plugin must be disabled. Self-heal if not.
    if not _plugin_disabled(cfg):
        healed, detail = _heal_plugin_disable()
        if healed:
            alerts.append(
                "web-parallel plugin was RE-ENABLED (likely a `hermes setup` "
                f"reinstall) — auto-re-disabled. {detail}"
            )
        else:
            print(f"[parallel-watchdog] ERROR: plugin re-enabled and "
                  f"self-heal failed: {detail}", file=sys.stderr)
            return 1

    # Layer 2: web backend config must not resolve to parallel. Config writes
    # are gated, so ALERT for manual re-assert rather than autonomous edit.
    safe, backend, search = _backends_safe(cfg)
    if not safe:
        alerts.append(
            "WEB BACKEND DRIFT: web.backend=%r search_backend=%r — resolver may "
            "fall through to the keyless Parallel default. Re-assert: "
            "`hermes config set web.backend firecrawl` + "
            "`hermes config set web.search_backend searxng`."
            % (backend or "<unset>", search or "<unset>")
        )

    if alerts:
        print("🛡️ PARALLEL WATCHDOG — web re-exposure detected:")
        for a in alerts:
            print(f"  • {a}")
        return 0

    # Clean: silent.
    return 0


if __name__ == "__main__":
    sys.exit(main())
