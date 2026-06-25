#!/bin/bash
set -uo pipefail
HERMES="/usr/local/lib/hermes-agent/venv/bin/hermes"
VENV_PY="/usr/local/lib/hermes-agent/venv/bin/python3"
ENV_FILE="/root/.hermes/.env"
CLAUDE_AUTH_DIR="/root/hermes-claude-auth"
CHAT_ID="-1003947663220"   # Telegram Cron Jobs channel
TS="$(date +%Y%m%d-%H%M%S)"
LOGFILE="/root/.hermes/logs/update-runner-${TS}.log"
SNAP="pre-update-2026-06"
LIBDIR="/usr/local/lib/hermes-agent"
mkdir -p /root/.hermes/logs

TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r\n')"
log()    { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGFILE"; }
notify() { log "$1"; [ -n "$TOKEN" ] && curl -s --max-time 20 \
  "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${CHAT_ID}" --data-urlencode "text=$1" \
  -d "disable_web_page_preview=true" >/dev/null 2>&1 || true; }

# GOLDEN already saved to /tmp/bypass.ORIG.py by the orchestrator before launch.
[ -f /tmp/bypass.ORIG.py ] || cp /root/.hermes/patches/anthropic_billing_bypass.py /tmp/bypass.ORIG.py

notify "🔧 Hermes update started (${TS}). 11521 commits behind — BIG jump; anchor-heals (B-full/Honcho) may need manual re-port. Chat goes dark on gateway restart; progress here. Log: ${LOGFILE}"

# --- 1. Snapshot already done by orchestrator; verify it exists ---
if [ -d "/root/.hermes/profiles/${SNAP}" ]; then
  notify "1/8 ✅ Snapshot ${SNAP} present (rollback target)."
else
  notify "1/8 ⚠️ Snapshot ${SNAP} missing — creating now…"
  "$HERMES" profile create "$SNAP" --clone-all >>"$LOGFILE" 2>&1 || notify "1/8 ⚠️ snapshot issue — update --backup still covers."
fi

# --- 2. The update (FATAL on failure) ---
notify "2/8 ⬇️ hermes update --yes --backup… (this rebuilds the venv)"
if "$HERMES" update --yes --backup >>"$LOGFILE" 2>&1; then
  notify "2/8 ✅ $("$HERMES" --version 2>/dev/null | head -1)"
else
  notify "2/8 ❌ UPDATE FAILED — still on old code. Rollback: hermes profile use ${SNAP}"; exit 1
fi

# --- 3. Config migrate (default + satellites; NO --yes flag in v0.16.0+) ---
notify "3/8 🔧 config migrate (default)…"
"$HERMES" config migrate >>"$LOGFILE" 2>&1 && notify "3/8 ✅ default migrated." || notify "3/8 ⚠️ default migrate — check log."
R="3/8 satellites:"; for p in executor ha-bot; do
  R="${R} | ${p}: $("$HERMES" --profile "$p" config migrate 2>&1 | tail -1)"; done; notify "$R"

# --- 4. Reinstall bypass (HOME set; install.sh uses set -u) ---
notify "4/8 🔑 reinstall OAuth bypass (HOME=/root)…"
( cd "$CLAUDE_AUTH_DIR" && HOME=/root ./install.sh ) >>"$LOGFILE" 2>&1 \
  && notify "4/8 ✅ bypass install.sh ran." || notify "4/8 ⚠️ install.sh nonzero — verify below."
# UNDO PITFALL 1: install.sh ships vanilla bypass without the classifier
CC="$(grep -c _classify_complexity /root/.hermes/patches/anthropic_billing_bypass.py 2>/dev/null || echo 0)"
if [ "$CC" -lt 2 ]; then
  cp /tmp/bypass.ORIG.py /root/.hermes/patches/anthropic_billing_bypass.py
  notify "4/8 ♻️ classifier clobbered by install.sh — restored from golden (count was ${CC})."
else
  notify "4/8 ✅ classifier intact (count ${CC})."
fi

# --- 5. Reinstall knowledge-db venv packages (PITFALL 4b — venv rebuild drops them) ---
notify "5/8 📦 reinstall knowledge-db packages (venv was rebuilt)…"
if uv pip install --python "$VENV_PY" \
   "lancedb==0.33.0" "pylance==7.0.0" "numpy==2.4.3" \
   "sentence-transformers==5.5.1" "pandas==3.0.3" "pyarrow==24.0.0" "torch==2.12.0" >>"$LOGFILE" 2>&1; then
  KB="$(cd /root/.hermes && "$VENV_PY" scripts/knowledge.py status 2>/dev/null | head -1)"
  notify "5/8 ✅ packages reinstalled. KB: ${KB:-CHECK LOG}"
else
  notify "5/8 ⚠️ uv pip install issue — knowledge.py may be down, check log."
fi

# --- 6. Patch guard — restore/verify all goldens + anchor-heals ---
notify "6/8 🛡️ running patch_guard (restores goldens, re-applies anchor-heals)…"
"$VENV_PY" /root/.hermes/scripts/patch_guard.py >>"$LOGFILE" 2>&1 || true
# Verify the anchor-fragile patches by MARKER (the big-jump risk)
BF="$(grep -c '_bfull_retrieve' "$LIBDIR/gateway/run.py" 2>/dev/null || echo 0)"
HF="$(grep -c 'def ' "$LIBDIR/plugins/memory/honcho/__init__.py" 2>/dev/null || echo 0)"
DT="$(grep -c 'parent inheritance produces a falsy key' "$LIBDIR/tools/delegate_tool.py" 2>/dev/null || echo 0)"
notify "6/8 anchor-heal markers → B-full:${BF} (want>=1) | honcho fns:${HF} | delegate-fallback:${DT} (want 1). If B-full=0 → MANUAL RE-PORT needed."

# --- 7. Restart gateways (best-effort; update already cycled them) ---
notify "7/8 🔄 restart gateways (best-effort)…"
systemctl --user restart hermes-gateway.service >>"$LOGFILE" 2>&1 || notify "7/8 ⏭️ user-bus restart unavailable from systemd unit (expected; update already cycled)."
systemctl --user restart hermes-gateway-ha-bot.service >>"$LOGFILE" 2>&1 || true

# --- 8. Live health: Anthropic bypass + classifier ---
notify "8/8 🧪 live bypass health test…"; sleep 6
H="$("$HERMES" chat -q 'Reply with exactly: AUTH TEST OK' --provider anthropic -m claude-sonnet-4-6 -Q 2>>"$LOGFILE")"
if echo "$H" | grep -q "AUTH TEST OK"; then
  notify "8/8 ✅ Anthropic bypass WORKING."
else
  notify "8/8 ❌ bypass test failed. Got: $(echo "$H" | head -c 200) — check ANTHROPIC_API_KEY/creds + log."
fi

notify "🏁 Update sequence complete (${TS}). VERIFY MANUALLY: (1) B-full fires on a live turn, (2) knowledge.py status = ~398 facts, (3) Anthropic 200s. If B-full marker was 0, re-port gateway/run.py from bfull goldens then re-sync goldens. Log: ${LOGFILE}"
