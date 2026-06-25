# Mac Studio Inference Tuning — Final State (P=4)
**Applied:** 2026-06-17 ~23:13 EDT
**Supersedes:** performance-baseline-pre-context-tuning-2026-06-17.md
**Change:** P=4 push + vision offloaded to Sonnet + aux-model reference cleanup

---

## What changed (this session, cumulative)

### Studio Ollama env (plist, applied via launchctl bootout+bootstrap)
| Var | Before | After |
|---|---|---|
| OLLAMA_NUM_PARALLEL | 2 | **4** |
| OLLAMA_MAX_LOADED_MODELS | 2 | **1** |
| OLLAMA_KEEP_ALIVE | 30m | 30m |

### Models on Studio
- **Kept:** `qwen2.5-32b-32k` (delegation/compression/curator/web_extract), `qwen2.5:72b` (heavy)
- **Deleted:** `qwen2.5-32b-64k`, `qwen2.5vl:7b`, `qwen2.5vl-8k`
- **Disk reclaimed:** 87G → 63G (**24GB** — the 64k held a full 19GB blob copy, NOT shared with 32k)

### config.yaml (main, default profile)
| Key | Before | After |
|---|---|---|
| delegation.model | qwen2.5-32b-64k | qwen2.5-32b-32k |
| delegation.max_concurrent_children | 8 | 12 |
| auxiliary.vision.model | qwen2.5vl:7b | **claude-sonnet-4-6** |
| auxiliary.vision.provider | custom:mac-studio | **anthropic** |
| auxiliary.compression.model | qwen2.5-32b-64k | qwen2.5-32b-32k |
| auxiliary.curator.model | qwen2.5-32b-64k | qwen2.5-32b-32k |
| auxiliary.web_extract.model | qwen2.5-32b-64k | qwen2.5-32b-32k |
| custom_providers.mac-studio.models | qwen2.5-32b-64k:65536 | qwen2.5-32b-32k:32768 |

---

## Verified end-state

### VRAM (P=4, vision gone)
```
qwen2.5-32b-32k   54.4GB / 56GB cap  (97% — all 4 KV slots reserved)
MAX_LOADED=1 → nothing else can load → tight margin is SAFE
```

### Concurrency proof (live 4-wide test)
- Single task: 13.1s
- 4 concurrent wall-clock: 30.4s
- Speedup vs serial: **1.7x** (43% parallel efficiency)
- All 4 requests completed (done=True)

### 32B eval speed (unchanged, as expected)
- Warm eval: ~13.5 t/s (identical to baseline — same weights)

---

## Vision now routes to Sonnet
- `vision_analyze` → claude-sonnet-4-6 via anthropic (OAuth billing-bypass, no metered key)
- Volume: ~5 calls / 14 days — negligible cost
- Privacy: images now leave the box to Anthropic (user approved 2026-06-17)
- Quality: UP (frontier vs local 7B). Latency: ~2-4s API vs 0.2s warm local.

---

## Rollback (if needed)
1. Config: `cp /root/.hermes/config.yaml.bak-p4-20260617T230709 /root/.hermes/config.yaml`
2. Studio plist: restore `~/Library/LaunchAgents/com.ollama.server.plist.bak-p4-20260617T230709`, then `launchctl bootout gui/501/com.ollama.server && launchctl bootstrap gui/501 <plist>`
3. Re-pull deleted models: `ollama pull` + rebuild Modelfiles (64k/vl:7b) — weights gone, ~10min pull
4. Restart gateway: `XDG_RUNTIME_DIR=/run/user/0 systemctl --user restart hermes-gateway`

---

## PITFALL learned this session
**launchctl plain-kill does NOT reload an edited plist.** A `kill <pid>` triggers launchd KeepAlive respawn from launchd's CACHED (in-memory) plist copy — env changes on disk are ignored. The running PID came back with OLD env (2/2) despite correct on-disk plist (4/1).
**Fix that works:** `launchctl bootout gui/$UID/com.ollama.server` then `launchctl bootstrap gui/$UID <plist-path>` — forces a fresh plist read. This works ONLY when launchd (not the Ollama.app GUI) owns the service. Confirm via `launchctl list | grep ollama` showing a real PID and no GUI app process running.
This corrects the ollama-inference-node-ops skill's kill-respawn recipe.
