# System Performance Baseline
**Captured:** 2026-06-17 ~19:40 EDT  
**State:** post-update (v0.16.0, commit 016bce1a), post-hardening (ufw, camofox rebind, PITFALL 7 fix)  
**Method:** live probes, no synthetic load, idle system

---

## Mac Mini (andrew-Macmini) — Orchestration Node

### Hardware
- CPU: Intel i7-8700B @ 3.20GHz, 6c/12t, boost 4.6GHz
- RAM: 31GB DDR4
- Disk: 458GB NVMe

### System State (idle baseline)
- CPU avg freq: 3,716 MHz (81% of max)
- Load average: 0.73 / 0.83 / 0.82 (1m/5m/15m)
- Memory used: 5.5GB / 31GB (18%)
- Memory available: 25GB
- Disk used: 49GB / 458GB (12%)
- Disk util: 11.9% | write: 17 ops/s @ 223 KB/s | read: 3.6 ops/s @ 144 KB/s
- Swap used: 0B / 2GB

### Hermes Gateway
- RSS: 1,572 MB
- VSZ: 12,155 MB

### Docker Stack Memory
| Container | Memory |
|---|---|
| firecrawl-api | 2.24 GB |
| firecrawl-playwright | 402 MB |
| firecrawl-rabbitmq | 343 MB |
| camofox-browser | 281 MB |
| firecrawl-nuq-postgres | 151 MB |
| searxng | 172 MB |
| firecrawl-redis | 30 MB |
| **Total stack** | **~3.6 GB** |

### Web Stack Latency (localhost)
| Service | p50 | p80 | Notes |
|---|---|---|---|
| SearXNG search | 0.66s | 0.89s | 5-sample range: 0.51–0.89s |
| Firecrawl scrape | 0.27s | — | example.com, 180 chars |
| Camofox health | 0.001s | — | pure in-process |

### Knowledge DB
- Facts: 438 (304 contextualized)
- Query latency: **7.9s** ⚠️ (cold, semantic search)
- Location: `/root/.hermes/knowledge_db`

---

## Mac Studio (localadmins-mac-studio) — Inference Node

### Hardware
- Chip: Apple M2 Max
- RAM: 64GB unified memory
- Disk: 926GB (78GB used, 820GB free)
- VRAM cap: 57,344 MB (~56GB)

### Network (Tailscale to mini)
| Metric | Value |
|---|---|
| TCP connect (p50) | 3–4ms |
| TCP connect (cold/first) | 17ms |
| API round-trip (tags) | 8–10ms |

### Inference Benchmarks — qwen2.5-32b-64k (Q4_K_M, 18.5GB)
*Role: delegation / cron / compression / curator*

| Run | Eval tok/s | Prompt tok/s | Load time |
|---|---|---|---|
| 1 (cold load) | 14.2 | 67.6 | 3.5s |
| 2 (warm) | 13.8 | 546.2 | 0.2s |
| 3 (warm) | 13.8 | 543.0 | 0.2s |

- **Warm eval: ~13.8 t/s** (threshold in watchdog: 5 t/s)
- **Cold load: 3.5s** (VRAM allocation)
- **Warm prompt ingestion: ~540 t/s** (KV cache reuse)

### Inference Benchmarks — qwen2.5vl:7b (Q4_K_M, 5.6GB)
*Role: vision tasks, 128K context*

| Run | Eval tok/s | Prompt tok/s | Load time |
|---|---|---|---|
| 1 (cold load) | 57.6 | 304.8 | 3.9s |
| 2 (warm) | 57.2 | 1,625.8 | 0.2s |
| 3 (warm) | 57.1 | 1,579.3 | 0.2s |

- **Warm eval: ~57.2 t/s** (4× faster than 32b — fits fully in Metal cache)
- **Warm prompt: ~1,600 t/s**
- **Cold load: 3.9s**

### qwen2.5:72b (Q4_K_M, 44.2GB)
*Role: heavy local delegation*
- Not benchmarked at baseline (would evict other models)
- Expected warm eval: ~6–8 t/s based on model size vs VRAM ratio
- Solo load time estimate: ~10–15s cold

### VRAM After Both Models Loaded (32b + vl:7b concurrent)
- vl:7b in VRAM: 21.5GB
- 32b evicted (KEEP_ALIVE=30m, timed out between bench runs)
- Combined if warm simultaneously: ~40GB / 56GB cap (~71%)

---

## Delegation Pipeline
- Async background dispatch: confirmed working
- Subagent model: qwen2.5-32b-64k (Studio)
- Round-trip latency (zero-tool task): **156s** (model reasoning overhead, not network)
- Sync delegation (batch): blocks parent, runs on same model

---

## Cron Subsystem
- Active jobs: 23/23
- Last runs: all "ok" as of baseline
- Fastest cadence: every 5 minutes (Infra Watchdog, Kanban Export)
- Studio watchdog: every 15 minutes, auto-restart on failure

---

## Alerting Thresholds (to watch against)
| Metric | Current | Alert if |
|---|---|---|
| Mini CPU load (1m) | 0.73 | > 10 sustained |
| Mini RAM available | 25GB | < 4GB |
| Mini disk used | 12% | > 80% |
| Studio 32b eval | 13.8 t/s | < 5 t/s (watchdog threshold) |
| SearXNG p50 | 0.66s | > 3s |
| Firecrawl scrape | 0.27s | > 10s |
| Knowledge DB query | 7.9s | > 30s |
| Tailscale RTT | 3–4ms | > 50ms |

---

## Known Baseline Quirks
- Knowledge DB 7.9s query is cold-start semantic search — acceptable, not degraded
- 32b warm prompt speed jumps 8× cold→warm (KV cache); always run warm for production
- Firecrawl RabbitMQ CPU: 14% idle — highest CPU consumer in docker stack (normal for AMQP broker)
- SearXNG DuckDuckGo engine has an upstream IndexError bug (non-fatal, other engines serve)
- Studio macOS firewall: disabled — pending manual `sudo` on Studio
