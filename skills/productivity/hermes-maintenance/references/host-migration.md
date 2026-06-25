# Hermes host-to-host migration (proven 2026-06-12, hil-1 → andrew-Macmini)

Full migration of a Hermes install (default + satellite profiles, OAuth bypass,
patch-guard, systemd gateways) to a new Linux box. ~2.4GB, ~30 min, brief cutover gap.

## Pre-flight

1. **Match the run user.** If source runs as root with `/root/` hardcoded across
   patches/scripts (`grep -rc "/root/" ~/.hermes/patches ~/.hermes/scripts`),
   run as **root on the target too** — path surgery across 60+ files is not worth it.
   Enable root SSH: install pubkey into `/root/.ssh/authorized_keys` via the sudo user;
   stock Ubuntu `PermitRootLogin prohibit-password` allows key auth already.
2. **Verify the CURRENT key.** The agent's SSH pubkey can rotate between gateway
   restarts — always `cat ~/.ssh/id_ed25519.pub` fresh and compare fingerprints
   (`ssh -v` shows which key is offered) instead of reusing a key pasted earlier
   in the conversation.
3. Prune dead profiles first (old `pre-update-*`, `stable-*`, swarm workers) —
   they can be >half the transfer size.

## Install Hermes on target

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh -o /tmp/hermes-install.sh
bash /tmp/hermes-install.sh --skip-setup
```
- Do NOT `curl | bash -- --flags` — the flags get eaten ("--skip-setup: No such file or directory"). Download, then run.
- Installs to `/usr/local/lib/hermes-agent/` with its own Python 3.11 venv regardless of system python.
- `cp /root/.hermes/config.yaml{,.fresh-install.bak}` before rsyncing over it.

## Sync (no downtime — source keeps running)

```bash
rsync -avz --exclude='hermes-agent/' --exclude='__pycache__' \
      --exclude='audio_cache/' --exclude='logs/' \
      ~/.hermes/ root@TARGET:/root/.hermes/
rsync -avz ~/hermes-claude-auth/ root@TARGET:/root/hermes-claude-auth/
rsync -avz ~/.claude/ root@TARGET:/root/.claude/          # OAuth creds
rsync -avz ~/.config/systemd/user/hermes-gateway*.service root@TARGET:/root/.config/systemd/user/
```

## OAuth bypass on target — two traps

1. **`install.sh` hangs over non-interactive SSH** at its `systemctl --user restart`
   step (no user session bus). Don't run it blind with a timeout; run its real steps
   manually: copy bypass file to `~/.hermes/patches/`, append `sitecustomize_hook.py`
   to the venv's `sitecustomize.py` if marker absent.
2. **PITFALL 1 strikes on BOTH hosts:** the repo's `anthropic_billing_bypass.py` is
   the vanilla one — copying it clobbers the custom classifier on the target, and the
   rsync of a clobbered source clobbers it everywhere. After any bypass install:
   `grep -c _classify_complexity ~/.hermes/patches/anthropic_billing_bypass.py` must
   be 2 on both hosts; restore from
   `~/.hermes/references/patch-guard/anthropic_billing_bypass.golden.py` if 0.

## Cutover + verify

```bash
# target
systemctl --user daemon-reload && systemctl --user enable --now hermes-gateway hermes-gateway-ha-bot
# source
systemctl --user stop hermes-gateway hermes-gateway-ha-bot && systemctl --user disable ...
```
- Only ONE gateway per bot token may run — two instances fight over Telegram polling.
- **`hostname` before any claim about which host is live.** Mid-migration, the session
  itself can silently move hosts (gateway restart picks up the synced config on the
  target). "Not loaded" errors from the OLD host's units are success, not failure.
- Post-cutover: both services `active (running)`, send a live message, then update
  topology memory (primary host, IPs, what stays on the old box).

## Rollback
Old host's install is intact until you disable its units — `systemctl --user start hermes-gateway` there reverts the cutover.
