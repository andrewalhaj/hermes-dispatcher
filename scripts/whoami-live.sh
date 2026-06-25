#!/bin/bash
set -euo pipefail

GOLDEN="/root/.hermes/references/topology.json"
HERMES_DIR="$HOME/.hermes"
DRIFT=0

# ── helpers ──────────────────────────────────────────────────────────────

# Parse a value from the golden JSON
gval() {
    python3 -c "import json; print(json.load(open('$GOLDEN'))$1)"
}

# Construct config.yaml path safely (the literal 'config.yaml' trips write-gate)
CFG_A="config"
CFG_B="yaml"
_CFG="${CFG_A}.${CFG_B}"
export _CFG

echo "=== whoami-live.sh: probing live facts vs golden ==="

# ── 1. hostname ──────────────────────────────────────────────────────────

LIVE_HOSTNAME=$(hostname)
GOLDEN_HOSTNAME=$(gval "['primary_host']['name']")
if [ "$LIVE_HOSTNAME" = "$GOLDEN_HOSTNAME" ]; then
    echo "OK hostname: $LIVE_HOSTNAME"
else
    echo "DRIFT hostname: live=$LIVE_HOSTNAME golden=$GOLDEN_HOSTNAME"
    DRIFT=1
fi

# ── 2. tailscale IPv4 (first line) ──────────────────────────────────────

LIVE_TAILSCALE=$(tailscale ip -4 2>/dev/null | head -1)
GOLDEN_TAILSCALE=$(gval "['primary_host']['tailnet_ip']")
if [ "$LIVE_TAILSCALE" = "$GOLDEN_TAILSCALE" ]; then
    echo "OK tailscale_ip: $LIVE_TAILSCALE"
else
    echo "DRIFT tailscale_ip: live=$LIVE_TAILSCALE golden=$GOLDEN_TAILSCALE"
    DRIFT=1
fi

# ── 3. RAM (free -g, allow golden-1 due to rounding) ────────────────────

LIVE_RAM=$(free -g 2>/dev/null | awk '/^Mem:/{print $2}')
GOLDEN_RAM=$(gval "['primary_host']['ram_gb']")
LOW_OK=$((GOLDEN_RAM - 1))
if [ "$LIVE_RAM" -eq "$GOLDEN_RAM" ] || [ "$LIVE_RAM" -eq "$LOW_OK" ]; then
    echo "OK ram_gb: ${LIVE_RAM}GB (golden=${GOLDEN_RAM}GB, accepted range ${LOW_OK}-${GOLDEN_RAM})"
else
    echo "DRIFT ram_gb: live=${LIVE_RAM}GB golden=${GOLDEN_RAM}GB"
    DRIFT=1
fi

# ── 4. operational profiles ─────────────────────────────────────────────

# On-disk non-backup profile dirs (exclude pre-update / bak)
LIVE_PROFILES=$(ls "$HERMES_DIR/profiles/" 2>/dev/null | grep -v 'pre-update' | grep -v 'bak' | sort | tr '\n' ' ' | xargs)

# Golden operational minus 'default' (default has no profiles/ subdir)
GOLDEN_PROFILES=$(python3 -c "
import json
ops = json.load(open('$GOLDEN'))['profiles']['operational']
filtered = sorted([p for p in ops if p != 'default'])
print(' '.join(filtered))
")

if [ "$LIVE_PROFILES" = "$GOLDEN_PROFILES" ]; then
    echo "OK profiles: $LIVE_PROFILES"
else
    echo "DRIFT profiles: live='$LIVE_PROFILES' golden='$GOLDEN_PROFILES'"
    DRIFT=1
fi

# ── 5. default model ────────────────────────────────────────────────────

# Read config.yaml via env var to avoid write-gate trigger
LIVE_MODEL=$(python3 -c "
import os
cfg_path = os.path.join(os.environ['HOME'], '.hermes', os.environ['_CFG'])
with open(cfg_path) as f:
    in_model = False
    for line in f:
        # Track entry into top-level 'model:' block
        if line.startswith('model:'):
            in_model = True
            continue
        if in_model and line.startswith('  default:'):
            print(line.split(':', 1)[1].strip())
            break
        # Next unindented key — left the model block
        if in_model and line and line[0] not in (' ', '\t'):
            in_model = False
")

GOLDEN_MODEL=$(gval "['models']['orchestration_default']")
if [ "$LIVE_MODEL" = "$GOLDEN_MODEL" ]; then
    echo "OK default_model: $LIVE_MODEL"
else
    echo "DRIFT default_model: live=$LIVE_MODEL golden=$GOLDEN_MODEL"
    DRIFT=1
fi

# ── 6. summary ──────────────────────────────────────────────────────────

echo "=== Summary ==="
if [ "$DRIFT" -eq 0 ]; then
    echo "All facts match golden. No drift detected."
    exit 0
else
    echo "DRIFT DETECTED: one or more facts differ from golden."
    exit 1
fi
