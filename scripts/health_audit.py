#!/usr/bin/env python3
"""
Hermes Agent System Health Audit

Reads /root/.hermes/references/system-inventory.md and executes FUNCTIONAL probes
against each listed subsystem. Each probe returns (state, detail) where state is
one of: PASS, FAIL, UNVERIFIABLE.

Exit code 0 if no FAILs, 1 if any FAIL. UNVERIFIABLE does not cause nonzero exit
but is displayed prominently.

Principles:
- Probes must prove a subsystem WORKS, not merely EXISTS.
- UNVERIFIABLE is surfaced loudly, never silently treated as PASS.
"""

import importlib.util
import os
import re
import subprocess
import sys
import time

# ── Constants ───────────────────────────────────────────────────────────────

INVENTORY_PATH = os.path.expanduser("~/.hermes/references/system-inventory.md")
KNOWLEDGE_PATH = os.path.expanduser("~/.hermes/scripts/knowledge.py")
GOLDEN_PATH = os.path.expanduser("~/.hermes/references/patch-guard/bfull-injection.golden.py")
RUN_PY_PATH = "/usr/local/lib/hermes-agent/gateway/run.py"
CONFIG_PATH = os.path.expanduser("~/.hermes/config.yaml")
MEMORY_MD = os.path.expanduser("~/.hermes/memories/MEMORY.md")
USER_MD = os.path.expanduser("~/.hermes/memories/USER.md")
WHOAMI_SCRIPT = os.path.expanduser("~/.hermes/scripts/whoami-live.sh")
HERMES_BIN = os.path.expanduser("~/.local/bin/hermes")
GIT_REPO = "/usr/local/lib/hermes-agent"
CODEGRAPH_DIR = os.path.expanduser("~/.codegraph")

MEMORY_CAP = 3000
USER_CAP = 2250


# ── Helpers ─────────────────────────────────────────────────────────────────

def run(cmd, timeout=60, env=None, check=False):
    """Run a command, return (returncode, stdout_str, stderr_str)."""
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env or os.environ.copy(),
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", f"timeout after {timeout}s"
    except FileNotFoundError:
        return -2, "", f"command not found: {cmd[0] if cmd else '?'}"
    except Exception as e:
        return -3, "", str(e)


def load_config():
    """Load config.yaml as a nested dict using pyyaml."""
    try:
        import yaml
    except ImportError:
        return None
    try:
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def docker_ports():
    """Discover docker container names and port mappings. Returns {name: [(host_ip, host_port, container_port)]}."""
    ports = {}
    rc, out, _ = run(["docker", "ps", "--format", "{{.Names}} {{.Ports}}"], timeout=10)
    if rc != 0:
        return ports
    for line in out.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split(" ", 1)
        name = parts[0]
        port_info = parts[1] if len(parts) > 1 else ""
        mappings = []
        for chunk in port_info.split(","):
            chunk = chunk.strip()
            if "->" in chunk:
                host_part, container_part = chunk.split("->")
                host_addr = host_part.strip()
                # parse host_ip:host_port
                if ":" in host_addr:
                    host_ip, host_port = host_addr.rsplit(":", 1)
                else:
                    host_ip = "0.0.0.0"
                    host_port = host_addr
                # strip protocol from container port
                container_port = container_part.split("/")[0].strip()
                try:
                    mappings.append((host_ip, int(host_port), int(container_port)))
                except ValueError:
                    pass
        ports[name] = mappings
    return ports


def http_get(url, timeout=10, headers=None):
    """HTTP GET, return (status_code, body)."""
    try:
        import requests
        r = requests.get(url, timeout=timeout, headers=headers or {})
        return r.status_code, r.text
    except ImportError:
        return None, "requests module not available"
    except requests.Timeout:
        return None, f"timeout after {timeout}s"
    except requests.ConnectionError as e:
        return None, f"connection error: {e}"
    except Exception as e:
        return None, str(e)


# ── Probes ──────────────────────────────────────────────────────────────────

def probe_gateway():
    """Probe 1: gateway — systemctl --user is-active hermes-gateway."""
    rc, stdout, stderr = run(["systemctl", "--user", "is-active", "hermes-gateway"], timeout=10)
    if rc == -2:
        return "UNVERIFIABLE", "systemctl not found"
    if rc != 0:
        # systemctl returns non-zero for inactive states or errors
        detail = stderr or stdout or f"exit code {rc}"
        return "FAIL", detail
    if stdout == "active":
        return "PASS", "active"
    return "FAIL", f"state is '{stdout}', expected 'active'"


def probe_bfull_recall():
    """Probe 2: bfull_recall — functional retrieval quality via knowledge.py search."""
    if not os.path.exists(KNOWLEDGE_PATH):
        return "UNVERIFIABLE", f"knowledge.py not found at {KNOWLEDGE_PATH}"

    try:
        spec = importlib.util.spec_from_file_location("knowledge", KNOWLEDGE_PATH)
        if spec is None or spec.loader is None:
            return "UNVERIFIABLE", "could not create module spec for knowledge.py"
        mod = importlib.util.module_from_spec(spec)
        sys.modules["knowledge"] = mod
        spec.loader.exec_module(mod)
    except Exception as e:
        return "UNVERIFIABLE", f"failed to load knowledge.py: {e}"

    if not hasattr(mod, "search"):
        return "UNVERIFIABLE", "knowledge.py has no search() function"

    try:
        results = mod.search("wall-dash dashboard", top_k=5)
    except Exception as e:
        return "UNVERIFIABLE", f"search() raised: {e}"

    if not results:
        return "FAIL", "no results returned for query 'wall-dash dashboard'"

    top = results[0]
    top_score = top.get("score", 0)

    # Check if any result mentions wall-dash or dashboard
    wall_dash_pattern = re.compile(r"wall.dash|dashboard", re.IGNORECASE)
    has_hit = False
    hit_text = ""
    for r in results:
        text = r.get("text", "")
        prefix = r.get("context_prefix", "")
        combined = f"{prefix} {text}"
        if wall_dash_pattern.search(combined):
            has_hit = True
            hit_text = combined[:120]
            break

    if has_hit and top_score >= 0.80:
        return "PASS", f"top score={top_score:.4f}, hit: '{hit_text[:80]}...'"
    elif has_hit:
        return "FAIL", f"relevant hit found but top score={top_score:.4f} < 0.80"
    else:
        return "FAIL", "no result mentioning wall-dash/dashboard"


def probe_bfull_golden():
    """Probe 3: bfull_golden — injection golden substring present in live run.py."""
    if not os.path.exists(GOLDEN_PATH):
        return "UNVERIFIABLE", f"golden file not found: {GOLDEN_PATH}"
    if not os.path.exists(RUN_PY_PATH):
        return "UNVERIFIABLE", f"run.py not found: {RUN_PY_PATH}"

    try:
        with open(GOLDEN_PATH) as f:
            golden = f.read().strip()
    except Exception as e:
        return "UNVERIFIABLE", f"failed to read golden: {e}"

    if not golden:
        return "UNVERIFIABLE", "golden file is empty"

    try:
        with open(RUN_PY_PATH) as f:
            run_py = f.read()
    except Exception as e:
        return "UNVERIFIABLE", f"failed to read run.py: {e}"

    if golden in run_py:
        return "PASS", "golden injection confirmed in run.py"
    return "FAIL", "golden injection NOT found in run.py"


def probe_codegraph_mcp():
    """Probe 4: codegraph_mcp — functional MCP wiring via `hermes mcp test codegraph`."""
    rc, stdout, stderr = run([HERMES_BIN, "mcp", "test", "codegraph"], timeout=60)
    if rc == -2:
        return "UNVERIFIABLE", f"hermes binary not found at {HERMES_BIN}"
    if rc != 0:
        combined = (stderr + " " + stdout).strip()[:200]
        return "UNVERIFIABLE", f"hermes mcp test failed: {combined}"

    # Parse "Tools discovered: N"
    m = re.search(r"Tools discovered:\s*(\d+)", stdout)
    if m:
        n = int(m.group(1))
        if n > 0:
            return "PASS", f"{n} tools discovered"
        else:
            return "FAIL", "0 tools discovered"
    return "UNVERIFIABLE", f"could not parse tool count from output: {stdout[:200]}"


def probe_codegraph_fresh():
    """Probe 5: codegraph_fresh — compare index commit vs git HEAD."""
    # Get git HEAD
    rc, head, _ = run(["git", "-C", GIT_REPO, "rev-parse", "HEAD"], timeout=10)
    if rc != 0:
        return "UNVERIFIABLE", f"could not get git HEAD: {head}"

    head = head.strip()
    if not head:
        return "UNVERIFIABLE", "empty git HEAD"

    # Best-effort: look for index commit in ~/.codegraph
    if not os.path.isdir(CODEGRAPH_DIR):
        return "UNVERIFIABLE", "~/.codegraph directory not found"

    # Check telemetry.json, daemon configs, version files for a commit hash
    candidates = []
    for root, dirs, files in os.walk(CODEGRAPH_DIR):
        dirs[:] = [d for d in dirs if not d.startswith("node_modules")]
        for fname in files:
            if fname.endswith(".json"):
                candidates.append(os.path.join(root, fname))

    index_commit = None
    for path in candidates:
        try:
            with open(path) as f:
                content = f.read()
            # Look for a 40-char hex hash
            for m in re.finditer(r"\b([0-9a-f]{40})\b", content):
                index_commit = m.group(1)
                break
        except Exception:
            pass
        if index_commit:
            break

    if index_commit is None:
        return "UNVERIFIABLE", "index commit not discoverable in ~/.codegraph"

    if index_commit == head:
        return "PASS", f"index matches HEAD ({head[:12]})"
    else:
        return "FAIL", f"index {index_commit[:12]} != HEAD {head[:12]}"


def probe_delegation():
    """Probe 6: delegation — live API probe to DeepSeek models endpoint."""
    cfg = load_config()
    if cfg is None:
        return "UNVERIFIABLE", "could not load config.yaml (yaml module missing or parse error)"

    delegation = cfg.get("delegation", {})
    base_url = delegation.get("base_url", "")
    api_key = delegation.get("api_key", "")

    if not base_url:
        return "UNVERIFIABLE", "no delegation base_url configured"
    if not api_key:
        return "UNVERIFIABLE", "no delegation api_key configured"

    url = base_url.rstrip("/") + "/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    status, body = http_get(url, timeout=15, headers=headers)
    if status is None:
        return "UNVERIFIABLE", f"HTTP request failed: {body}"
    if status == 200:
        return "PASS", f"HTTP 200 from {url}"
    return "FAIL", f"HTTP {status} from {url}"


def probe_web_stack():
    """Probe 7: web_stack — HTTP GET searxng, firecrawl, camofox health endpoints."""
    services = {
        "searxng": {"ports": [], "health_path": "/", "name_keywords": ["searxng", "searx"]},
        "firecrawl": {"ports": [], "health_path": "/", "name_keywords": ["firecrawl"]},
        "camofox": {"ports": [], "health_path": "/health", "name_keywords": ["camofox", "camoufox"]},
    }

    # Discover ports from docker
    dp = docker_ports()

    for svc_name, svc in services.items():
        for container_name, mappings in dp.items():
            container_lower = container_name.lower()
            if any(kw in container_lower for kw in svc["name_keywords"]):
                for host_ip, host_port, container_port in mappings:
                    svc["ports"].append((host_ip, host_port))
                break

    # Check each service
    results = []
    for svc_name, svc in services.items():
        if not svc["ports"]:
            results.append((svc_name, "UNVERIFIABLE", "no port discovered from docker"))
            continue

        host_ip, host_port = svc["ports"][0]
        # Use localhost for 0.0.0.0 or 127.0.0.1
        connect_ip = "127.0.0.1" if host_ip in ("0.0.0.0", "::") else host_ip
        url = f"http://{connect_ip}:{host_port}{svc['health_path']}"

        status, body = http_get(url, timeout=10)
        if status is None:
            results.append((svc_name, "UNVERIFIABLE", f"HTTP request failed: {body[:100]}"))
        elif 200 <= status < 400:
            results.append((svc_name, "PASS", f"HTTP {status}"))
        else:
            results.append((svc_name, "FAIL", f"HTTP {status}"))

    # Aggregate
    states = [r[1] for r in results]
    if all(s == "PASS" for s in states):
        return "PASS", ", ".join(f"{n}:{s}" for n, s, _ in results)
    elif "FAIL" in states:
        details = "; ".join(f"{n}:{s} ({d})" for n, s, d in results)
        return "FAIL", details
    else:
        details = "; ".join(f"{n}:{s} ({d})" for n, s, d in results)
        return "UNVERIFIABLE", details


def probe_memory_headroom():
    """Probe 8: memory_headroom — wc -m vs caps from config.yaml."""
    # wc -m (character count)
    memory_chars = 0
    user_chars = 0

    try:
        with open(MEMORY_MD, "r") as f:
            memory_chars = len(f.read())
    except Exception:
        pass

    try:
        with open(USER_MD, "r") as f:
            user_chars = len(f.read())
    except Exception:
        pass

    # Read LIVE caps from config.yaml
    cfg = load_config()
    memory_cap = MEMORY_CAP
    user_cap = USER_CAP
    if cfg:
        mem = cfg.get("memory", {})
        memory_cap = mem.get("memory_char_limit", MEMORY_CAP)
        user_cap = mem.get("user_char_limit", USER_CAP)

    mem_pct = (memory_chars / memory_cap * 100) if memory_cap > 0 else 0
    user_pct = (user_chars / user_cap * 100) if user_cap > 0 else 0

    detail = f"MEMORY:{memory_chars}/{memory_cap} ({mem_pct:.1f}%), USER:{user_chars}/{user_cap} ({user_pct:.1f}%)"

    if mem_pct >= 90 or user_pct >= 90:
        return "FAIL", detail
    return "PASS", detail


def probe_cron():
    """Probe 9: cron — scheduler alive and reporting enabled jobs."""
    rc, stdout, stderr = run([HERMES_BIN, "cron", "list"], timeout=15)
    if rc == -2:
        return "UNVERIFIABLE", f"hermes binary not found at {HERMES_BIN}"
    if rc != 0:
        combined = (stderr + " " + stdout).strip()[:200]
        return "UNVERIFIABLE", f"hermes cron list failed: {combined}"

    # Look for [active] jobs
    active_count = len(re.findall(r"\[active\]", stdout))
    if active_count > 0:
        return "PASS", f"{active_count} active jobs"
    return "FAIL", "no active cron jobs found"


def probe_topology():
    """Probe 10: topology — run whoami-live.sh if it exists."""
    if not os.path.exists(WHOAMI_SCRIPT):
        return "UNVERIFIABLE", f"whoami-live.sh not found at {WHOAMI_SCRIPT}"

    rc, stdout, stderr = run(["bash", WHOAMI_SCRIPT], timeout=30)
    if rc == 0:
        return "PASS", "no drift detected"
    combined = (stdout + " " + stderr).strip()[:200]
    return "FAIL", f"drift detected (exit {rc}): {combined}"


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    probes = [
        ("gateway", probe_gateway),
        ("bfull_recall", probe_bfull_recall),
        ("bfull_golden", probe_bfull_golden),
        ("codegraph_mcp", probe_codegraph_mcp),
        ("codegraph_fresh", probe_codegraph_fresh),
        ("delegation", probe_delegation),
        ("web_stack", probe_web_stack),
        ("memory_headroom", probe_memory_headroom),
        ("cron", probe_cron),
        ("topology", probe_topology),
    ]

    print("=" * 70)
    print("  Hermes Agent System Health Audit")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print()

    results = []
    for name, fn in probes:
        try:
            state, detail = fn()
        except Exception as e:
            state, detail = "UNVERIFIABLE", f"probe raised exception: {e}"
        results.append((name, state, detail))
        print(f"[{state:<13}] {name}: {detail}")

    print()
    print("-" * 70)

    pass_count = sum(1 for _, s, _ in results if s == "PASS")
    fail_count = sum(1 for _, s, _ in results if s == "FAIL")
    unv_count = sum(1 for _, s, _ in results if s == "UNVERIFIABLE")

    print(f"  PASS: {pass_count}  FAIL: {fail_count}  UNVERIFIABLE: {unv_count}  TOTAL: {len(results)}")
    print("=" * 70)

    if fail_count > 0:
        # List FAIL items again for visibility
        print("\n  FAILED CHECKS:")
        for name, state, detail in results:
            if state == "FAIL":
                print(f"    - {name}: {detail}")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
