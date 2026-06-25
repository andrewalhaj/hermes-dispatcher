# Reading/writing Honcho peer cards WITHOUT the honcho_* tools (cron / restricted toolsets)

The 5 `honcho_*` tools (`honcho_profile`, `honcho_conclude`, etc.) are only present when
the Honcho recall mode exposes them AND the running context has them in its toolset. **Cron
jobs and other restricted-toolset runs often do NOT have them.** When a task says "call
`honcho_profile(peer='user')`" but that tool isn't available, drop to the SDK directly —
do not give up or fabricate a read.

## Verified path (matches what the tools do internally)

Source of truth for the mechanics: `plugins/memory/honcho/session.py`
(`get_peer_card` → `_fetch_peer_card`, `set_peer_card`, `create_conclusion`).

```python
from honcho import Honcho   # use the hermes venv python: /usr/local/lib/hermes-agent/venv/bin/python3
c = Honcho(api_key=API_KEY, workspace_id=WORKSPACE)   # from ~/.hermes/honcho.json
ai   = c.peer(AI_PEER)     # the profile's aiPeer, e.g. "hermes"   (the OBSERVER)
user = c.peer(USER_PEER)   # peerName, e.g. "root"                 (the TARGET)
```

Config values live in `~/.hermes/honcho.json`:
- top-level `apiKey`
- per-host block (e.g. `hosts.hermes`): `workspace`, `peerName` (user peer), `aiPeer`.
- `hermes honcho status` also prints AI peer / User peer / Workspace quickly.

### Read the user's curated card (= `honcho_profile(peer="user")`)

The plugin reads it as **observer=AI peer, target=user peer** when observation is
`directional` (the default — `ai.observeOthers=true`). So:

```python
card = ai.get_card(target=USER_PEER)        # primary path
if card is None:
    card = user.get_card()                  # fallback: card stored on target peer directly
# honcho_profile normalizes None -> []  (an EMPTY card asserts no facts)
```

`get_card()` returns `None` when the curated card is empty. `card()` is the deprecated
alias for the same thing. **An empty/None card means zero asserted facts** — for a drift
watchdog that's a CLEAN result, not an error.

**⚠️ Card items can be plain strings, not just dicts.** The SDK `get_card()` returns a
list where items may be either `dict` (with a `content` key) or plain `str`. Iterating
with `item.get('content', ...)` crashes on strings. Always handle both:

```python
card = ai.get_card(target=USER_PEER)
if card is None:
    print("RESULT: NONE_CARD")     # empty card, not an error
    sys.exit(0)

# Handle mixed item types (str or dict)
for idx, item in enumerate(card):
    if isinstance(item, dict):
        content = item.get('content', str(item))
    else:
        content = str(item)
    print(f'[{idx}] {content}')
```

**Also works for write.** When re-asserting a clean card via `ai.set_card(card_list, target=...)`,
pass a list of plain strings — the SDK accepts both forms.

### Write the user's curated card (= `honcho_profile(peer="user", card=[...])`)

```python
ai.set_card(new_list, target=USER_PEER)     # observer writes target's card (directional)
# if ai.observeOthers were false, you'd write user.set_card(new_list) instead
```

### Write a conclusion (= `honcho_conclude(peer="user", conclusion="...")`)

```python
# directional (ai observes others): AI peer authors the conclusion ABOUT the user
ai.conclusions_of(USER_PEER).create([{"content": text, "session_id": SESSION_ID}])
```
`session_id` is optional for a standalone re-plant; pass it if you have a live session.
For a self-conclusion (`peer="ai"`) use `ai.conclusions_of(AI_PEER)`.

## Pitfalls

- **Use the hermes venv interpreter**, not bare `python3` — the `honcho` package
  (honcho-ai) is installed there: `/usr/local/lib/hermes-agent/venv/bin/python3`.
- API base for the SDK is the hosted default; for raw REST it's `/v3` not `/v1`
  (see `store-level-deletion-api.md`).
- **`peerName: "root"` in `honcho.json` is NOT a valid peer ID for direct SDK/REST calls
  (PROVEN 2026-06-10).** `peerName` is a config alias that the plugin resolves internally.
  When you call `client.peer("root")` directly, the SDK returns `None` for any card/data
  call — `"root"` is not an actual peer registered in the Honcho workspace. The real
  operative peer ID is the Telegram user ID (e.g. `"8878729385"`). To find yours:
  `python3 -c "from plugins.memory.honcho.client import HonchoClientConfig, get_honcho_client; \
  cfg = HonchoClientConfig.from_global_config(); c = get_honcho_client(cfg); \
  print(c.peer('8878729385').get_card()[:1])"` — substitute IDs until you get data.
  The honcho_* tools in-session work fine (they use the plugin's resolution path); this
  only bites raw SDK/REST scripts like the Obsidian bridge.
- Observer vs target matters. In `directional`/`unified` modes the card lives in the
  observer→target slot, which is why the primary read is `ai.get_card(target=user)`, with
  `user.get_card()` only as a fallback. Reading the wrong slot returns None and looks
  (wrongly) like an empty card.
- **`card() is deprecated`** DeprecationWarning is harmless — prefer `get_card()`.
- Don't treat `None` as a failure to read. `None` is a successful read of an empty card.
  Distinguish "read failed (exception)" from "read succeeded, card empty" before deciding
  CLEAN vs DRIFT.
- **For the Obsidian bridge (`honcho-bridge.sh`) or any shell script calling Honcho: use
  the Python SDK via a heredoc (`exec python3 - <<'PYEOF' ... PYEOF`), not raw curl.**
  Raw curl breaks silently when the API version changes — the SDK absorbs version changes
  automatically. Confirmed: `/v1/` returns 404; the SDK POSTs to `/v3/workspaces` and GETs
  from `/v3/workspaces/<ws>/peers/<id>/card`. Using bash curl with a hardcoded version
  string means every API upgrade silently writes `{"detail":"Not Found"}` to Obsidian.
