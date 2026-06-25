#!/bin/bash
# Detached Hermes core-update runner — 2026-06-09 (371 commits, v0.16.0 → latest)
# Launch: systemd-run --unit=hermes-update-$(date +%s) --collect bash <this>
# Reports to Andrew's Telegram DM out-of-band (session goes dark on gateway restart).
set -uo pipefail
HERMES="/usr/local/lib/hermes-agent/venv/bin/hermes"
LIB="/usr/local/lib/hermes-agent"
ENV_FILE="/root/.hermes/.env"
CLAUDE_AUTH_DIR="/root/hermes-claude-auth"
CHAT_ID="8878729385"
TS="$(date +%Y%m%d-%H%M%S)"
LOGFILE="/root/.hermes/logs/update-runner-${TS}.log"
SNAP="pre-update-2026-06-09b"
UNIT_DIR="/root/.config/systemd/user"
export XDG_RUNTIME_DIR=/run/user/0
mkdir -p /root/.hermes/logs

TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r\n')"
log()    { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGFILE"; }
notify() { log "$1"; [ -n "$TOKEN" ] && curl -s --max-time 20 \
  "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${CHAT_ID}" --data-urlencode "text=$1" \
  -d "disable_web_page_preview=true" >/dev/null 2>&1 || true; }

# GOLDEN copy before update (undoes install.sh classifier clobber — PITFALL 1)
cp /root/.hermes/patches/anthropic_billing_bypass.py /tmp/bypass.ORIG.py

notify "🔧 Hermes update started (${TS}). 371 commits. This chat goes dark on gateway restart — progress posts here. Log: ${LOGFILE}"

# 1. SNAPSHOT
notify "1/8 📸 Snapshot ${SNAP} (--clone-all)…"
"$HERMES" profile create "$SNAP" --clone-all >>"$LOGFILE" 2>&1 \
  && notify "1/8 ✅ Snapshot ok." || notify "1/8 ⚠️ snapshot issue — continuing (update has --backup)."

# 2. UPDATE (fatal-abort)
notify "2/8 ⬇️ hermes update --yes --backup…"
if "$HERMES" update --yes --backup >>"$LOGFILE" 2>&1; then
  notify "2/8 ✅ $("$HERMES" --version | head -1)"
else
  notify "2/8 ❌ UPDATE FAILED — still on old code. Rollback: hermes profile use ${SNAP}"; exit 1
fi

# 3. CONFIG MIGRATE (default + active satellites; NO voice-changer — decommissioned)
notify "3/8 🔧 config migrate (no --yes flag in v0.16.0+)…"
"$HERMES" config migrate >>"$LOGFILE" 2>&1 && notify "3/8 ✅ default migrated." || notify "3/8 ⚠️ check log."
R="3/8 satellites:"; for p in executor ha-bot swarm-synthesizer swarm-verifier swarm-worker-a swarm-worker-b swarm-worker-c; do
  R="${R} | ${p}: $("$HERMES" --profile "$p" config migrate 2>&1 | tail -1)"; done; notify "$R"

# 4. REINSTALL BYPASS (HOME set) + restore classifier from golden (PITFALL 1)
notify "4/8 🔑 reinstall bypass (HOME=/root)…"
( cd "$CLAUDE_AUTH_DIR" && HOME=/root ./install.sh ) >>"$LOGFILE" 2>&1 \
  && notify "4/8 ✅ bypass reinstalled." || notify "4/8 ⚠️ install.sh nonzero — verify."
if [ "$(grep -c _classify_complexity /root/.hermes/patches/anthropic_billing_bypass.py)" -lt 2 ]; then
  cp /tmp/bypass.ORIG.py /root/.hermes/patches/anthropic_billing_bypass.py
  notify "4/8 ♻️ classifier was clobbered by install.sh — restored from golden."
fi

# 4b. PITFALL 6 — ensure both gateway units load .env (durable delegation-key fix)
notify "4b/8 🔧 PITFALL-6: EnvironmentFile in gateway units…"
for U in hermes-gateway.service hermes-gateway-ha-bot.service; do
  UF="${UNIT_DIR}/${U}"
  if [ -f "$UF" ] && ! grep -q "EnvironmentFile=-/root/.hermes/.env" "$UF"; then
    cp "$UF" "${UF}.bak-${TS}"
    sed -i '/^Environment="HERMES_HOME=/a EnvironmentFile=-/root/.hermes/.env' "$UF"
    notify "4b/8 ✅ added EnvironmentFile to ${U}"
  else
    notify "4b/8 ⏭️ ${U}: already present or missing."
  fi
done
systemctl --user daemon-reload >>"$LOGFILE" 2>&1 || true

# 5. PATCH-GUARD — heal/verify all 6 patches; surfaces anchor-not-found for the 3 fragile core patches
notify "5/8 🩹 patch_guard self-heal + verify (bypass/deleg/skill/B-full/Honcho/delegate)…"
PG="$(cd /root/.hermes && python3 scripts/patch_guard.py 2>&1)"
if [ -z "$PG" ]; then
  notify "5/8 ✅ all 6 patches healthy (silent no-op)."
else
  notify "5/8 ⚠️ patch_guard report:
${PG}"
fi
# explicit marker census so we KNOW what survived
MB="$(grep -c _classify_complexity /root/.hermes/patches/anthropic_billing_bypass.py 2>/dev/null)"
BF="$(grep -c '_bfull_retrieve(message_text)' ${LIB}/gateway/run.py 2>/dev/null)"
HO="$(grep -c 'HERMES-PATCH drift-suppression' ${LIB}/plugins/memory/honcho/__init__.py 2>/dev/null)"
DG="$(grep -c 'Fallback: when parent inheritance produces a falsy key' ${LIB}/tools/delegate_tool.py 2>/dev/null)"
notify "5/8 markers — classifier:${MB}(want≥2) Bfull:${BF}(want1) Honcho:${HO}(want1) delegate:${DG}(want1)"

# 6. RESTART GATEWAYS (default + ha-bot)
notify "6/8 🔄 restart gateways…"
systemctl --user restart hermes-gateway.service >>"$LOGFILE" 2>&1 || notify "6/8 ⏭️ default user-bus restart unavailable (expected from systemd unit)."
systemctl --user restart hermes-gateway-ha-bot.service >>"$LOGFILE" 2>&1 || true
sleep 6

# 7. HEALTH — bypass auth + delegation key env (PITFALL-6 proof) + B-full marker live
notify "7/8 🧪 health checks…"
H="$("$HERMES" chat -q 'Reply with exactly: AUTH TEST OK' --provider anthropic -m claude-sonnet-4-6 -Q 2>>"$LOGFILE")"
echo "$H" | grep -q "AUTH TEST OK" && notify "7/8 ✅ Anthropic bypass WORKING." \
  || notify "7/8 ❌ bypass test failed. Got: $(echo "$H" | head -c 200)"
GWPID="$(systemctl --user show -p MainPID --value hermes-gateway.service 2>/dev/null)"
KEYS="$(tr '\0' '\n' < /proc/${GWPID}/environ 2>/dev/null | grep -cE '^(DEEPSEEK_API_KEY|ANTHROPIC)')"
notify "7/8 delegation env: ${KEYS} key(s) loaded in gateway PID ${GWPID} (want ≥1 → PITFALL-6 fixed)"

# 8. DONE
notify "8/8 🏁 Update complete. Review markers above; any <want = manual re-port needed (skill: hermes-core-update-with-bypass). Log: ${LOGFILE}"
