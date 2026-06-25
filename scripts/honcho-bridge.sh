#!/usr/bin/env bash
# Honcho-to-Obsidian Bridge
# Uses the Honcho Python SDK (avoids raw REST URL fragility across API versions).
exec python3 - <<'PYEOF'
import sys, json, pathlib, datetime
sys.path.insert(0, '/usr/local/lib/hermes-agent')

VAULT = pathlib.Path('/root/Documents/Obsidian Vault/hermes-memories/honcho')
VAULT.mkdir(parents=True, exist_ok=True)
TIMESTAMP = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
PEER_ID = '8878729385'

try:
    from plugins.memory.honcho.client import HonchoClientConfig, get_honcho_client
    cfg = HonchoClientConfig.from_global_config()
    client = get_honcho_client(cfg)
    peer = client.peer(PEER_ID)

    # Peer card
    card = peer.get_card() or []
    card_json = json.dumps({'peer_card': card}, indent=2)

    # User representation (summary synthesised by the dialectic)
    try:
        rep = peer.representation()
        rep_text = rep if isinstance(rep, str) else json.dumps(rep, indent=2)
    except Exception as e:
        rep_text = f'(unavailable: {e})'

except Exception as e:
    card_json = json.dumps({'error': str(e)})
    rep_text = f'(error: {e})'

(VAULT / 'peer-card.md').write_text(
    f'# Honcho Peer Card — Andrew Alhaj\n**Last sync:** {TIMESTAMP}\n\n```json\n{card_json}\n```\n'
)
(VAULT / 'user-model.md').write_text(
    f'# Honcho User Model\n**Last sync:** {TIMESTAMP}\n\n{rep_text}\n'
)

print(f'Bridge sync complete at {TIMESTAMP}')
print('Files:')
import subprocess
subprocess.run(['ls', '-la', str(VAULT)])
PYEOF
