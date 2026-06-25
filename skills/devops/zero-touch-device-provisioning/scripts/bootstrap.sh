#!/usr/bin/env bash
# zero-touch device bootstrap — Tailscale + SSH + Hermes handoff.
# Run once on a device you own (Linux/macOS). No secrets baked in; all via env,
# so this file is safe to host/share. Verified working 2026-06-16.
#
#   TS_AUTHKEY    Tailscale reusable/ephemeral auth key   (required)
#   SSH_PUBKEY    operator public key to authorize        (required)
#   HOSTNAME_TAG  optional tailnet hostname override       (optional)
#   TG_TOKEN      Telegram bot token for "online" ping     (optional)
#   TG_CHAT       Telegram chat id                         (optional)
#
# Trigger (the "one-liner"), run on the target shell:
#   TS_AUTHKEY=*** SSH_PUBKEY="ssh-ed25519 ..." bash <(curl -fsSL https://<host>/bootstrap.sh)

set -euo pipefail
log()  { printf '[bootstrap] %s\n' "$*"; }
need() { [ -n "${!1:-}" ] || { echo "[bootstrap] missing required env: $1" >&2; exit 1; }; }

need TS_AUTHKEY
need SSH_PUBKEY

OS="$(uname -s)"
log "OS=$OS host=$(hostname)"

case "$OS" in
  Linux)
    command -v tailscale >/dev/null 2>&1 || { log "installing tailscale (linux)"; curl -fsSL https://tailscale.com/install.sh | sh; }
    if command -v systemctl >/dev/null 2>&1; then
      sudo systemctl enable --now ssh 2>/dev/null || sudo systemctl enable --now sshd 2>/dev/null || true
    fi
    ;;
  Darwin)
    if ! command -v tailscale >/dev/null 2>&1; then
      if command -v brew >/dev/null 2>&1; then log "installing tailscale (brew)"; brew install tailscale;
      else echo "[bootstrap] brew not found — install Tailscale.app manually" >&2; exit 1; fi
    fi
    # NOTE: on macOS, enabling Remote Login here may silently no-op without Full Disk
    # Access. If SSH refuses after this runs, toggle it via System Settings → General →
    # Sharing → Remote Login (GUI bypasses the FDA requirement).
    sudo systemsetup -setremotelogin on 2>/dev/null || true
    ;;
  *) echo "[bootstrap] unsupported OS: $OS" >&2; exit 1 ;;
esac

mkdir -p "$HOME/.ssh"; chmod 700 "$HOME/.ssh"
touch "$HOME/.ssh/authorized_keys"; chmod 600 "$HOME/.ssh/authorized_keys"
grep -qF "$SSH_PUBKEY" "$HOME/.ssh/authorized_keys" || printf '%s\n' "$SSH_PUBKEY" >> "$HOME/.ssh/authorized_keys"
log "ssh key authorized"

log "bringing up tailscale"
sudo tailscale up --authkey "$TS_AUTHKEY" --ssh ${HOSTNAME_TAG:+--hostname "$HOSTNAME_TAG"} || true

TSIP="$(tailscale ip -4 2>/dev/null | head -1 || true)"
log "tailnet ip: ${TSIP:-unknown}"

if [ -n "${TG_TOKEN:-}" ] && [ -n "${TG_CHAT:-}" ]; then
  curl -fsS "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TG_CHAT}" \
    --data-urlencode "text=device online: $(hostname) / ${TSIP:-?}" >/dev/null || true
fi
log "done — reachable at ${TSIP:-<tailnet ip>} over Tailscale/SSH"
