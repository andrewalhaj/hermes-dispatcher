# Sizing a Kanban worker fleet to host RAM

Workers are full OS processes, ~400–500MB resident each. The limiting resource is RAM,
not CPU (agent workers are I/O-bound waiting on LLM API responses, so 2 vCPU handles
several concurrent workers fine). Size the fleet from real free memory.

## Probe live before promising capacity (read-only)

```bash
free -h                                   # distinguish truly-free from buff/cache
ps -eo pid,rss,comm --sort=-rss | head    # what's already resident (gateways ~350-450MB each)
docker stats --no-stream --format '  {{.Name}}: {{.MemUsage}} ({{.MemPerc}})'
nproc                                      # cores (rarely the wall)
swapon --show                             # is it already dipping into swap?
dmesg | grep -ci "out of memory"          # OOM history = it HAS been starved
```

## Rule of thumb

```
safe_concurrent_workers ≈ (free_RAM_GB - 1.0_headroom) / 0.5_per_worker
```

| Host RAM | Baseline (gateways+OS+docker) | Safe concurrent workers | Full swarm (4w+verifier+synth ≈ 2.4–3GB)? |
|---|---|---|---|
| 8 GB  | ~1.5–2GB | 2–3 (swaps under Docker load) | No — OOM risk |
| 16 GB | ~2GB | 2–3 comfortable | Tight but workable |
| 32 GB | ~2GB | 3+ with cache margin | Yes, + Docker, no anxiety |

`delegation.max_concurrent_children: 3` is a natural ceiling to mirror for swarm workers.

## Two-host sizing lesson (June 2026)

Right-size each box to its JOB, never blanket-upgrade both:
- **Worker box** (runs Kanban workers + Docker/OD + gateways) → the box that benefits from
  more RAM. Upgraded 8→32GB / 2→8 vCPU. This is where swarms run.
- **HA/appliance box** (Home Assistant core + dashboard + a domain-bot gateway only, NO
  Kanban workers) → tiny by design. Was a 2GB box idling <1GB used, dipping ~350MB into
  swap with 0 OOM-kills = mildly tight, not starved. Right fix = 2→4GB, NOT 32GB. Blanket
  "both to 32GB" would have ~16x over-bought the appliance box for capacity it never touches.

## Hetzner resize gotchas

- Resize requires the server **powered off** from the Cloud console.
- Disk grows **permanently** — you cannot shrink it back later. RAM/CPU-only resizes are
  reversible; a disk bump is not. Prefer RAM/CPU-only when you might downsize.
- Reboot drops the gateways. Verify recovery after (see "post-reboot health probe" below).

## Post-reboot health probe (what reboots love to break)

```bash
# auto-start prerequisites for user services:
loginctl show-user root | grep -i linger          # MUST be Linger=yes or services won't start on boot
systemctl --user is-enabled hermes-gateway.service hermes-gateway-<sat>.service
systemctl --user is-active  hermes-gateway.service hermes-gateway-<sat>.service
docker ps --format '{{.Names}} ({{.Status}})'      # restart policies honored?
# delegation key survived (the EnvironmentFile regression — see below):
grep -A3 '^delegation:' ~/.hermes/config.yaml | sed 's/api_key:.*/api_key: <present>/'
hermes kanban stats                                 # board sane, no orphaned 'running'
```

**Verified regression (June 2026):** a resize/reboot RESET the gateway unit files,
dropping the hardened `EnvironmentFile=-/root/.hermes/.env` line from both units. They came
back with only PATH/VIRTUAL_ENV/HERMES_HOME. Delegation still worked ONLY because the
DeepSeek key also lives in `config.yaml → delegation.api_key` (belt-and-suspenders). Lesson:
keep the key in BOTH config.yaml and .env, and re-check the unit files after any
reboot/upgrade — the EnvironmentFile line is a recurring casualty. Re-hardening it is a
gated unit-file edit + `systemctl --user daemon-reload`.
