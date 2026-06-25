# Mealio deployment record (2026-06-10)

Concrete instance of the nextjs-prisma-docker-selfhost pattern. Use as the worked example.

## Live endpoints (hil-1 / 5.78.238.81)
- Custom Mealio: :3015 (`/root/projects/mealio/app`, container `mealio`)
- Stock Mealie v3.19.2: :9925 (`/root/projects/mealio/mealie-stock`, container `mealie-stock`, SQLite, data at `./data`)

## Stack
Next.js 14.2.29 (App Router, standalone), TypeScript, Tailwind (custom glass token layer), Prisma 5.22 + SQLite, deepseek-chat extraction via OpenAI-compatible client, Firecrawl REST `/v1/scrape` for URL→markdown.

## Build pipeline that worked
- 6 phases, each delegated to one deepseek subagent with a FULLY-SPECIFIED context (complete file contents in the brief, exact paths, known pitfalls listed). Orchestrator verified each phase against disk (.next/BUILD_ID, route files compiled, DB tables present) before marking its kanban card done.
- Per-phase verify commands: `ls .next/BUILD_ID`, `find .next/server/app -path '*<route>*'`, python sqlite3 table/count checks.
- Import pipeline keys: DEEPSEEK_API_KEY + FIRECRAWL_API_KEY copied from /root/.hermes/.env into app .env / .env.docker. Provider-agnostic via EXTRACTION_MODEL / EXTRACTION_BASE_URL env vars.

## Kanban tracking
Inert tracking cards (blocked+unassigned) per phase, title prefix "Mealio — " routes them to the Mealio board in scripts/kanban_export.py BOARDS list. Completed via `hermes kanban complete <id> "<verified summary>"`; status verified via sqlite, not CLI output.

## Auth model
Single-user: scrypt hash, HMAC cookie session (SESSION_SECRET in .env.docker), 30-day expiry, first-visitor-registers at /login (claim immediately after deploy). Edge middleware checks token shape only.
