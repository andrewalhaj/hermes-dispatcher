# Migration Paths Off Single-Host — Game Plan
**Drafted:** June 2, 2026

> ⚠️ **SUPERSEDED (2026-06-08).** This document describes a Manifest + Railway-Postgres +
> nginx-LB horizontal-scaling plan that is **no longer in use**. Manifest was retired and
> routing is now direct-to-provider (see `infrastructure-summary.md`). There is no Manifest
> stack, no Railway DB, and no nginx load-balancer. Retained as a **historical planning record
> only** — do NOT follow any deploy/scaling steps here against the live system.

**Original status (historical):** Phase 1-4 complete (June 3, 2026) — dual Manifest instances on shared Railway DB behind nginx LB

---

## Current State (June 2)

**Manifest:** Docker Compose stack at `/root/manifest/`. Two containers — `manifestdotbuild/manifest:latest` (stateless app) + `postgres:16-alpine` (state). Bound to `127.0.0.1:2099`. PostgreSQL on a named Docker volume. Health check at `/api/v1/health`.

**Scheduler:** In-process with Hermes. State in `~/.hermes/cron/jobs.json` (5KB, backed up daily). No HA. One instance fires all cron.

**The common bottleneck:** PostgreSQL. Both migration paths converge on it.

---

## Manifest — Horizontal Scaling

### Phase 1: Externalize Postgres (prerequisite)
Pull postgres out of the Docker Compose stack onto its own host or a managed service (RDS, Crunchy, etc.). This is step zero — neither Manifest HA nor scheduler HA works without it.

```
Current:  [manifest + postgres] on one host
Phase 1:  [manifest] on host A  →  [postgres] on host B
```

Config change: update `DATABASE_URL` in `~/.hermes/.env` (passed to compose via the `.env` file at `/root/manifest/.env`). Set `POSTGRES_PASSWORD` to match. Test with `docker compose up -d`.

**Risk:** Low. PostgreSQL is PostgreSQL. TLS to managed service covers the wire. Downtime: <5 min to restart compose with new DB URL.

> **EXECUTION NOTES (June 2-3):**
> - **Neon:** Migrated successfully, but 260MB dump caused timeouts on VPS. Later dumped clean (66KB config-only) and restored to Railway.
> - **VPS Postgres:** Scram auth mismatch. Docker postgres on VPS fixed with trust auth, but VPS Postgres instance was abandoned in favor of Railway.
> - **Railway:** 297MB full dump (with session tables) restored successfully June 3. Both Manifest instances now share Railway.
> - **Password:** VPS .env had literal `***` placeholder — auth failed silently until corrected.

### Phase 2: Add a Second Manifest Instance
Spin up the same compose stack on a second host, pointing at the same postgres. No code changes — it's the same container image.

```
Phase 2:  [manifest-1] ─┐
          [manifest-2] ─┼→ [postgres] on host B
```

Test: `curl host2:2099/api/v1/health` → 200.

> **EXECUTION NOTES (June 3):** VPS Manifest started with Railway DB. Both instances (local + VPS) share the same database — structurally complete and functionally verified.

### Phase 3: Load Balancer
nginx or HAProxy in front. Health check on `/api/v1/health`. Round-robin.

```
Phase 3:  [nginx / HAProxy] → [manifest-1]
                            → [manifest-2]
                            → all → [postgres]
```

> **EXECUTION NOTES (June 3):** nginx LB on VPS:8080, round-robin between local Manifest (5.78.238.81:2099) and VPS Manifest (127.0.0.1:2099). Verified alternating health checks. Config at `/etc/nginx/sites-enabled/manifest-lb`.

### Phase 4: Point Hermes at the LB
Hermes config already supports this. Change `base_url` from `localhost:2099/v1` to LB endpoint. No Hermes restart needed if config hot-reloads.

> **EXECUTION NOTES (June 3):** Hermes `base_url` updated to `http://178.156.246.115:8080/v1`. Both `model.base_url` and `providers.manifest-vision.base_url` set. No restart needed.

### What This Doesn't Solve — Phase 5

**Postgres HA:** Railway managed Postgres provides automated backups and
point-to-time recovery on all tiers. True streaming replica + auto-failover
requires Railway Pro or higher. For a personal install, Railway's managed
backups + off-host backup (VPS) is sufficient. Upgrade path: Railway Pro →
enable read replicas → configure auto-failover in Railway dashboard.

**Load Balancer HA:** Currently single VPS nginx is a SPOF. Options:
- **Floating IP + keepalived:** Requires a second VPS ($5-10/mo). keepalived
  manages a shared virtual IP between the two VPSes. If one dies, the other
  takes over the IP. Standard pattern, well-documented.
- **Cloud Load Balancer:** Use a managed LB (DigitalOcean, Hetzner, AWS ALB).
  Eliminates the VPS entirely for LB. $10-20/mo. Best option if already using
  a cloud provider.
- **Accept SPOF:** For personal use, single VPS is fine. The recovery procedure
  is: if VPS dies, point Hermes directly at local Manifest (`localhost:2099/v1`)
  while VPS is rebuilt. 5 min config change.

**Scheduler HA:** Addressed by Option A (documented recovery). See
`/root/.hermes/references/scheduler-recovery-procedure.md`. Option B
(leader election) and Option C (standalone binary) remain available
for future scale.

### Rough Effort

| Phase | Item | Time | Status |
|-------|------|------|--------|
| 1 | Externalize postgres | 1 hour | ✅ Done (Railway) |
| 2 | Second manifest | 30 min | ✅ Done (VPS) |
| 3 | Load balancer | 2 hours | ✅ Done (nginx) |
| 4 | Point Hermes | 5 min | ✅ Done |
| 5a | Postgres HA | Railway plan upgrade | Deferred |
| 5b | LB HA | 2nd VPS + keepalived: ~4h | Deferred |
| 5c | Scheduler recovery | 30 min | ✅ Done |

No code changes required — all ops.

---

## Scheduler — Decoupling from Hermes

**The real problem:** The scheduler isn't just on one host — it's inside the Hermes process. If Hermes restarts, the scheduler restarts. If Hermes crashes, cron jobs don't fire.

### Option A: Documented Recovery (cheapest, solves 80%)
The scheduler state is 5KB of JSON. The daily backup already captures it. Recovery:

1. Restore `~/.hermes/cron/jobs.json` from backup
2. Start Hermes on new host
3. Scheduler picks up `next_run_at` from jobs.json, resumes

Downtime: minutes. Data loss: at most one missed tick per job. Good enough for personal/small-team. Write it down, test it once, done.

**Effort:** 30 min to write + test the recovery doc.

### Option B: Externalize State + Leader Election (real HA)
Externalize the scheduler state to the same postgres that Manifest uses (or a dedicated SQLite on shared storage). Add leader election so only one Hermes instance fires cron.

```
Current:    [Hermes] reads jobs.json, fires cron
Option B:   [Hermes-1] ─┐
            [Hermes-2] ─┼→ [postgres]  ← jobs table
            Only one holds the advisory lock → fires cron
```

Pseudocode:
```sql
-- Try to acquire lock, non-blocking
SELECT pg_try_advisory_lock(42);
-- If true: you're the leader. Fire cron jobs. Renew lock every 30s.
-- If false: standby. Poll every 30s.
```

Migration steps:
1. Add a `cron_jobs` table to postgres (schema: id, name, schedule, last_run, next_run, status, config_json)
2. Write a one-time migration script: jobs.json → postgres
3. Add leader election to the scheduler loop
4. Multiple Hermes instances can run — only the leader fires

**Effort:** 1-2 days. Touches Hermes core code. Worth it only if multi-Hermes is on the roadmap.

### Option C: Standalone Scheduler Binary (middle ground)
Extract the scheduler into its own process. Single binary, reads jobs.json, fires cron, no LLM, no gateway. Run it on a dedicated lightweight host or as a systemd service.

```
[Hermes host]      ← gateway, LLM, sessions
[Scheduler host]   ← just cron, tiny footprint
```

**Effort:** 1 day to extract, test, and document. Less code than Option B. Still single-host for the scheduler itself, but decoupled from Hermes — Hermes can restart/update without touching cron.

---

## Recommendation

### Manifest
- **Done:** Phases 1-4 complete. Multi-host Manifest with shared Railway DB.
- **Deferred:** Phase 5a (Postgres HA) — Railway Pro plan upgrade when needed.
- **Deferred:** Phase 5b (LB HA) — second VPS + keepalived when single-VPS
  reliability becomes a concern.

### Scheduler
- **Done:** Option A — documented recovery with dry-run test. See
  `/root/.hermes/references/scheduler-recovery-procedure.md`.
- **Next Step:** Off-host backups active (VPS sync added to backup.sh).
- **Long-Term:** Option B or C — only with multi-Hermes.

**Why this order was correct:** Postgres externalization unblocked everything.
Phases 2-4 were fast (ops only, no code changes) once the shared DB was stable.
The scheduler recovery doc is honest about current scale — 5 cron jobs on a
personal install don't need leader election.

---

## Rollback Plan (current)

To revert to single-host (pre-Phase-1 state):

1. `hermes config set model.base_url http://localhost:2099/v1`
2. `hermes config set providers.manifest-vision.base_url http://localhost:2099/v1`
3. Stop VPS Manifest: `ssh root@178.156.246.115 "docker compose -f /root/manifest/docker-compose.yml stop manifest"`
4. (Optional) Point local Manifest back to Docker postgres if Railway is
   being decomissioned: update `/root/manifest/.env` DATABASE_URL to
   `postgresql://manifest:***@postgres:5432/manifest`, `docker compose up -d`.

Zero data loss — routing changes only. The Railway DB preserves all config
as a snapshot of the multi-host state. Docker volume `manifest_pgdata` on the
local host is never deleted (pre-migration safety net).

### Execution History (June 2-3, 2026)

**Attempt 1 (June 2):** Neon → VPS postgres → dual Manifest. Failed: Neon
dump too large (260MB), VPS scram auth, instances on separate DBs. Rolled back.

**Attempt 2 (June 3):** Railway direct. Used full 297MB dump (session tables
included). Restored successfully. VPS .env had `***` placeholder — fixed.
All 4 phases complete with LB round-robin verified.

**Net improvements from the migration:**
- Multi-host Manifest (local + VPS) with shared Railway DB
- nginx LB on VPS:8080 with health-checked round-robin
- Off-host backups (daily scp to VPS)
- Scheduler recovery procedure documented and dry-run tested
- Claude Opus 4.8 on complex/reasoning/header tiers
- 5 cron jobs preserved: backup (03:00), audit (09:00), heartbeat (06:00),
  KB dedup (Sun 04:00), Honcho bridge (08:00)
