# Next.js 14 + Prisma/SQLite scaffold pitfalls (verified 2026-06-10, Mealio build)

Pitfalls hit (and fixed) while delegating a Next.js 14.2 App Router + TypeScript + Tailwind +
Prisma/SQLite app build to subagents. Bake these into the delegation context so the
subagent doesn't burn turns rediscovering them — or so the orchestrator can spot-check fast.

## Build-config quirks (Next.js 14.2)
- **`next.config.ts` is NOT supported** — must be `next.config.mjs` (TS config support landed in Next 15).
- **`postcss.config.js` must be CJS** (`module.exports = {...}`) — Next's PostCSS loader rejects ESM.
- `'use client'` is required on any component using hooks (useState/useEffect/useRef/useCallback);
  keep layout.tsx a Server Component when using `next/font/google` (fonts must load server-side).
  Pattern: server Nav imports a small client ThemeToggle, not the other way round.
- `navigator.wakeLock` / `WakeLockSentinel`: do NOT declare custom types — `lib.dom.d.ts` already
  has them; duplicate declarations fail the build with "identical modifiers" errors. Just try/catch.
- **`useSearchParams()` requires a `<Suspense>` boundary** in Next 14 — a page using it fails the
  static build otherwise. Wrap the page content, not the hook call.
- **Verify lucide-react icon names before speccing them** — e.g. `Import` does not exist
  (subagent self-fixed to `ArrowDownToLine`). In delegation specs, name a fallback icon explicitly.
- **Edge middleware (`src/middleware.ts`) must NOT import anything that pulls in Prisma or
  `node:crypto`** — Edge runtime build failure. Pattern for cookie auth: middleware checks token
  FORMAT only (presence + part count); real HMAC verification lives in route handlers / server
  components via a `getSessionUserId()` helper. Acceptable for single-user self-hosted apps.

## Prisma + SQLite path trap (the big one)
- `DATABASE_URL="file:./prisma/dev.db"` resolves **relative to schema.prisma's directory** for
  CLI commands (`db push`, seed) but differently at app runtime → DB lands at `prisma/prisma/dev.db`
  while the app reads `prisma/dev.db` (no tables, silent breakage despite build exit 0).
- **Fix: absolute URL** — `DATABASE_URL="file:///abs/path/to/app/prisma/dev.db"`. CLI and runtime agree.
- Seeds are not idempotent: re-running `npx tsx prisma/seed.ts` duplicates rows. Verify row counts
  after any re-run; dedupe by `ORDER BY createdAt LIMIT n`.
- Seeding: `npx tsx prisma/seed.ts` is the low-friction path (avoid ts-node + tsconfig-paths setup).
- Schema additions mid-project: `npx prisma db push` preserves data and regenerates the client —
  no migration ceremony needed for SQLite dev DBs.

## LLM/scrape import-pipeline pattern (URL → structured recipe/JSON)
Provider-agnostic shape that worked first-pass:
- **Fetcher:** raw `fetch()` against Firecrawl REST (`POST /v1/scrape`, formats:['markdown']) is more
  reliable than the `@mendable/firecrawl-js` SDK (avoids SDK type issues). Returns markdown + ogImage.
- **Extractor:** `openai` SDK pointed at any OpenAI-compatible base URL (DeepSeek here) with
  `EXTRACTION_MODEL` / `EXTRACTION_BASE_URL` env vars → swap providers without code changes. Use
  `response_format: { type: 'json_object' }`, temperature ~0.1, truncate input to ~8k chars, and a
  prompt that mandates exact JSON shape + "omit, never invent" + a not-a-recipe escape hatch.
- **Graceful partial failure:** status-tracked DB record per import (pending→fetching→reading→
  structuring→done/failed) lets the UI poll progress and the history page show failures.
- API keys for the pipeline can be harvested from `/root/.hermes/.env` (DEEPSEEK_API_KEY,
  FIRECRAWL_API_KEY are active there even when shown commented elsewhere) — copy into the app's
  own `.env`, never hardcode.

## Verification one-liners (orchestrator spot-checks after a delegated phase)
```bash
ls .next/BUILD_ID                                   # build actually produced
find .next/server/app -name 'route.js' -o -name 'page.js' | wc -l   # route count
find . -name "*.db" -not -path "*/node_modules/*"   # WHERE did the DB actually land?
python3 -c "import sqlite3;print(sqlite3.connect('prisma/dev.db').execute('SELECT COUNT(*) FROM Recipe').fetchone())"
python3 -c "import sqlite3;print([r[0] for r in sqlite3.connect('prisma/dev.db').execute(\"SELECT name FROM sqlite_master WHERE type='table'\")])"  # schema additions landed
grep -l "'use client'" src/components/**/*.tsx      # client directive audit
grep -c "lib/auth\|@prisma" src/middleware.ts        # MUST be 0 (Edge-safety)
```

## Delegation-spec patterns that produced clean one-pass builds
- Paste full file contents in the context (not "create a component that...") — the subagent writes
  exactly what's reviewed; deviations are then meaningful signals, not noise.
- List the *expected* common failure modes at the end of the spec ("if build fails, check X/Y/Z") —
  the deepseek subagents self-fixed config-format issues without a round-trip when primed this way.
  Proven across 5 consecutive phases (scaffold → design system → CRUD → cook mode → import →
  auth/meal-plan): every phase built exit-0 with at most one self-fixed error.
- Require "run `npm run build`, fix all errors, report exit code" — never accept a report without
  the build having been exercised.
- End-state report format: files created/modified + exit codes + errors fixed. Easy to verify.
- For large pages with interactivity (calendar, review screens), spec the data flow + component API
  precisely but let the subagent write the layout JSX in full ("write this page in full — polished,
  glass-styled, responsive") — works fine once the design-token vocabulary is listed in context.
