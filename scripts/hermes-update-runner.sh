#!/bin/bash
# ============================================================================
# hermes-update-runner.sh  —  detached Hermes core update + bypass reinstall
# ============================================================================
# Runs as a system-level systemd transient unit so it SURVIVES the gateway
# restart that kills the controlling chat session. Reports each step to
# Telegram out-of-band via the Bot API (the gateway is down during the run).
#
# Sequence:
#   1. Pre-update full snapshot (rollback point)
#   2. hermes update --yes --backup
#   3. config migrate (default) + config check (satellites, read-only)
#   4. Reinstall hermes-claude-auth OAuth bypass (venv rebuild wiped it)
#   5. Restart gateways
#   6. Anthropic bypass health test (real hermes call through the venv)
#   7. Final status report
#
# Every step logged to LOGFILE and reported to Telegram. Non-fatal steps
# continue; fatal failures (update itself) abort with a report.
# ============================================================================

set -uo pipefail

HERMES="/usr/local/lib/hermes-agent/venv/bin/hermes"
ENV_FILE="/root/.hermes/.env"
CLAUDE_AUTH_DIR="/root/hermes-claude-auth"
CHAT_ID="8878729385"
TS="$(date +%Y%m%d-%H%M%S)"
LOGFILE="/root/.hermes/logs/update-runner-${TS}.log"
SNAP="pre-update-2026-06"

# --- restart scope: voice-changer is crash-looping pre-update; default skip ---
RESTART_VOICE_CHANGER="${RESTART_VOICE_CHANGER:-no}"

mkdir -p /root/.hermes/logs

# Read bot token at runtime (never passed in by the agent).
TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r\n')"

log() {
    echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGFILE"
}

notify() {
    # Send to Telegram; never fail the script if Telegram is unreachable.
    local msg="$1"
    log "$msg"
    if [ -n "$TOKEN" ]; then
        curl -s --max-time 20 \
            "https://api.telegram.org/bot${TOKEN}/sendMessage" \
            --data-urlencode "chat_id=${CHAT_ID}" \
            --data-urlencode "text=${msg}" \
            -d "disable_web_page_preview=true" >/dev/null 2>&1 || true
    fi
}

notify "🔧 Hermes update started (${TS}). This chat will go dark when gateways restart — progress will arrive here. Log: ${LOGFILE}"

# --- Step 1: pre-update snapshot -------------------------------------------
notify "1/7 📸 Creating rollback snapshot '${SNAP}' (--clone-all)…"
if "$HERMES" profile create "$SNAP" --clone-all >>"$LOGFILE" 2>&1; then
    notify "1/7 ✅ Snapshot '${SNAP}' created. Rollback: hermes profile use ${SNAP}"
else
    notify "1/7 ⚠️ Snapshot may already exist or failed — check log. Continuing (update has its own --backup)."
fi

# --- Step 2: the update (FATAL if it fails) --------------------------------
notify "2/7 ⬇️ Running 'hermes update --yes --backup' (373 commits)… this is the long step."
if "$HERMES" update --yes --backup >>"$LOGFILE" 2>&1; then
    NEWVER="$("$HERMES" --version 2>/dev/null | head -1)"
    notify "2/7 ✅ Update complete. Now: ${NEWVER}"
else
    notify "2/7 ❌ UPDATE FAILED — aborting. System left on pre-update code. Check ${LOGFILE}. Rollback available: hermes profile use ${SNAP}"
    exit 1
fi

# --- Step 3: config migration + satellite check ----------------------------
notify "3/7 🔧 Migrating default config…"
"$HERMES" config migrate --yes >>"$LOGFILE" 2>&1 && notify "3/7 ✅ Default config migrated." || notify "3/7 ⚠️ config migrate returned non-zero — check log."

SAT_REPORT="3/7 Satellite config check:"
for prof in executor ha-bot voice-changer stable-2026-06-02; do
    OUT="$("$HERMES" --profile "$prof" config check 2>&1 | tail -1)"
    SAT_REPORT="${SAT_REPORT}
  • ${prof}: ${OUT}"
done
notify "$SAT_REPORT"

# --- Step 4: reinstall OAuth bypass (venv rebuild wiped sitecustomize) ------
notify "4/7 🔑 Reinstalling hermes-claude-auth OAuth bypass (venv rebuild wiped it)…"
if [ -x "${CLAUDE_AUTH_DIR}/install.sh" ]; then
    if ( cd "$CLAUDE_AUTH_DIR" && ./install.sh ) >>"$LOGFILE" 2>&1; then
        notify "4/7 ✅ Bypass reinstalled."
    else
        notify "4/7 ❌ Bypass install.sh failed — Anthropic calls will 401 until fixed. Check ${LOGFILE}."
    fi
else
    notify "4/7 ❌ ${CLAUDE_AUTH_DIR}/install.sh not found/executable — bypass NOT reinstalled."
fi

# Sanity: sitecustomize present again?
if [ -f /usr/local/lib/hermes-agent/venv/lib/python3.11/site-packages/sitecustomize.py ]; then
    notify "4/7 ✅ sitecustomize.py present in rebuilt venv."
else
    notify "4/7 ❌ sitecustomize.py MISSING after install — bypass will not load."
fi

# --- Step 5: restart gateways ----------------------------------------------
notify "5/7 🔄 Restarting gateways…"
systemctl --user restart hermes-gateway.service >>"$LOGFILE" 2>&1 && notify "5/7 ✅ default gateway restarted." || notify "5/7 ❌ default gateway restart failed."
systemctl --user restart hermes-gateway-ha-bot.service >>"$LOGFILE" 2>&1 && notify "5/7 ✅ ha-bot gateway restarted." || notify "5/7 ❌ ha-bot gateway restart failed."
if [ "$RESTART_VOICE_CHANGER" = "yes" ]; then
    systemctl --user restart hermes-gateway-voice-changer.service >>"$LOGFILE" 2>&1 && notify "5/7 ✅ voice-changer restarted." || notify "5/7 ⚠️ voice-changer restart failed (was already crash-looping)."
else
    notify "5/7 ⏭️ voice-changer LEFT AS-IS (was crash-looping pre-update; debug separately)."
fi

# --- Step 6: Anthropic bypass health test ----------------------------------
notify "6/7 🧪 Testing Anthropic OAuth bypass (live hermes call)…"
sleep 5
HEALTH="$("$HERMES" chat -q 'Reply with exactly: AUTH TEST OK' --provider anthropic -m claude-sonnet-4-6 -Q 2>>"$LOGFILE")"
if echo "$HEALTH" | grep -q "AUTH TEST OK"; then
    notify "6/7 ✅ Anthropic bypass WORKING. Main model healthy."
else
    notify "6/7 ❌ Anthropic bypass test did NOT return expected string. Got: $(echo "$HEALTH" | head -c 200). Check ${LOGFILE} — may need: cd ${CLAUDE_AUTH_DIR} && ./install.sh; claude auth login --claudeai"
fi

# --- Step 7: done ----------------------------------------------------------
notify "7/7 🏁 Update sequence finished. Review log: ${LOGFILE}. Next: A + sitecustomize delegation-guard patch (separate gated step) on the updated base."
