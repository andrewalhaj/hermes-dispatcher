#!/bin/bash
# Hermes core update runner — v0.16.0 → 0.17.0 (origin/main, +311)
# Detached system-level runner (PITFALL 5: gateway restart severs the chat).
# Launch: systemd-run --unit=hermes-update-<ts> --collect bash <this>
set -uo pipefail

export HOME=/root
export HERMES_HOME=/root/.hermes
export PATH=/root/.local/bin:$PATH

HERMES="/usr/local/lib/hermes-agent/venv/bin/hermes"
VENV_PY="/usr/local/lib/hermes-agent/venv/bin/python3"
UV="/root/.local/bin/uv"
ENV_FILE="/root/.hermes/.env"
CLAUDE_AUTH_DIR="/root/hermes-claude-auth"
BYPASS="/root/.hermes/patches/anthropic_billing_bypass.py"
PATCH_GUARD="/root/.hermes/scripts/patch_guard.py"
CHAT_ID="8878729385"
TS="$(date +%Y%m%d-%H%M%S)"
LOGFILE="/root/.hermes/logs/update-runner-${TS}.log"
SNAP="pre-update-2026-06-20"
mkdir -p /root/.hermes/logs

TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r\n')"
log()    { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGFILE"; }
notify() { log "$1"; [ -n "$TOKEN" ] && curl -s --max-time 20 \
  "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${CHAT_ID}" --data-urlencode "text=$1" \
  -d "disable_web_page_preview=true" >/dev/null 2>&1 || true; }

# Preserve the pre-update golden made in Step B; only copy if absent.
[ -f /tmp/bypass.ORIG.py ] || cp "$BYPASS" /tmp/bypass.ORIG.py

notify "🔧 Hermes update v0.16.0→0.17.0 started (${TS}). This chat goes dark on gateway restart — progress posts here. Log: ${LOGFILE}"

# 1/8 — snapshot
notify "1/8 📸 Snapshot profile ${SNAP}…"
"$HERMES" profile create "$SNAP" --clone-all >>"$LOGFILE" 2>&1 \
  && notify "1/8 ✅ Snapshot ok." \
  || notify "1/8 ⚠️ snapshot issue — continuing (update has --backup + we have /tmp nets)."

# 2/8 — the update (FATAL on failure)
notify "2/8 ⬇️ hermes update --yes --backup (311 commits; may take a few min)…"
if "$HERMES" update --yes --backup >>"$LOGFILE" 2>&1; then
  notify "2/8 ✅ $("$HERMES" --version 2>/dev/null | head -1)"
else
  notify "2/8 ❌ UPDATE FAILED (likely git conflict on kanban_tools.py or carried telegram commit). Still on old code. Tail: $(tail -8 "$LOGFILE" | tr '\n' ' ' | head -c 400)"
  notify "2/8 ↩️ Rollback if needed: hermes profile use ${SNAP}"
  exit 1
fi

# 3/8 — config migrate (default + the 2 real satellites)
notify "3/8 🔧 config migrate (no --yes flag in v0.16.0+)…"
"$HERMES" config migrate >>"$LOGFILE" 2>&1 && notify "3/8 ✅ default migrated." || notify "3/8 ⚠️ default migrate — check log."
R="3/8 satellites:"; for p in executor ha-bot; do
  R="${R} | ${p}: $("$HERMES" --profile "$p" config migrate 2>&1 | tail -1 | head -c 80)"; done; notify "$R"

# 4/8 — reinstall bypass + UNDO PITFALL 1 (install.sh ships vanilla bypass)
notify "4/8 🔑 reinstall OAuth bypass (HOME set)…"
( cd "$CLAUDE_AUTH_DIR" && HOME=/root ./install.sh ) >>"$LOGFILE" 2>&1 \
  && notify "4/8 ✅ bypass install.sh ran." || notify "4/8 ⚠️ install.sh nonzero — verifying classifier next."
# Single-file grep + head -1 + int-coerce (avoids the 0\n0 multi-file bug)
CC="$(grep -c _classify_complexity "$BYPASS" 2>/dev/null | head -1)"; CC="${CC:-0}"
if [ "$CC" -lt 2 ]; then
  cp /tmp/bypass.ORIG.py "$BYPASS"
  notify "4/8 ♻️ classifier clobbered by install.sh (count=${CC}) — restored from /tmp golden."
else
  notify "4/8 ✅ classifier intact (count=${CC})."
fi

# 5/8 — reinstall KB deps (venv rebuild drops LanceDB set; uv FULL PATH)
notify "5/8 📦 reinstall knowledge-store deps into rebuilt venv…"
if "$VENV_PY" -c "import lancedb" >/dev/null 2>&1; then
  notify "5/8 ✅ KB deps already present (venv not rebuilt or survived)."
else
  "$UV" pip install --python "$VENV_PY" \
    "lancedb==0.33.0" "pylance==7.0.0" "numpy==2.4.3" \
    "sentence-transformers==5.5.1" "pandas==3.0.3" "pyarrow==24.0.0" >>"$LOGFILE" 2>&1 \
    && notify "5/8 ✅ KB deps reinstalled." || notify "5/8 ❌ KB deps install FAILED — see log."
fi
KBS="$(cd /root/.hermes && "$VENV_PY" scripts/knowledge.py status 2>&1 | tail -2 | tr '\n' ' ' | head -c 160)"
notify "5/8 KB status: ${KBS}"

# 6/8 — patch-guard self-heal (re-applies surgical anchors B-full/honcho/delegate_tool;
#        restores any clobbered guard from the freshly-synced goldens)
notify "6/8 🩹 patch-guard self-heal…"
PG="$("$VENV_PY" "$PATCH_GUARD" 2>&1)"
if [ -z "$PG" ]; then
  notify "6/8 ✅ patch-guard silent — all 10 artifacts healthy (anchors survived)."
else
  notify "6/8 🩹 patch-guard acted: $(echo "$PG" | tr '\n' ' ' | head -c 400)"
fi

# 7/8 — restart gateways (best-effort; update already cycled them)
notify "7/8 🔄 restart gateways…"
systemctl --user restart hermes-gateway.service hermes-gateway-ha-bot.service >>"$LOGFILE" 2>&1 \
  && notify "7/8 ✅ gateways restarted." \
  || notify "7/8 ⏭️ user-bus restart unavailable from systemd unit (expected; update cycled them)."

# 8/8 — live bypass health + B-full marker check
notify "8/8 🧪 verification…"; sleep 6
H="$("$HERMES" chat -q 'Reply with exactly: AUTH TEST OK' --provider anthropic -m claude-sonnet-4-6 -Q 2>>"$LOGFILE")"
echo "$H" | grep -q "AUTH TEST OK" && notify "8/8 ✅ Anthropic bypass WORKING." \
  || notify "8/8 ❌ bypass test failed (may be Anthropic overload, not breakage). Got: $(echo "$H" | head -c 200)"
BF="$(grep -c '_bfull_retrieve(message_text)' /usr/local/lib/hermes-agent/gateway/run.py 2>/dev/null | head -1)"
notify "8/8 B-full marker in run.py: ${BF} (1=re-applied; verify live RAG on next real turn)."
VER="$("$HERMES" --version 2>/dev/null | head -1)"
notify "🏁 DONE. ${VER}. Verify: B-full fires on a real turn, kanban_phase_checkpoint fires (journal), unprotected files (base.py/.7z + kanban_tools.py) present — re-apply /tmp/*.patch if not. Log: ${LOGFILE}"
