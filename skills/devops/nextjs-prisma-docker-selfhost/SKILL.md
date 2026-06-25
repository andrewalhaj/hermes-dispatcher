---
name: nextjs-prisma-docker-selfhost
description: "Self-host Next.js+Prisma+SQLite apps in Docker"
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [nextjs, prisma, sqlite, docker, deploy, selfhost, alpine]
    related_skills: [subagent-driven-development, verification-before-completion, cloudflare-tunnel-expose]
    created_by: agent
load_when:
  - "building or deploying a Next.js app in Docker"
  - "Prisma + SQLite in a container or self-hosted app"
  - "Next.js standalone output / Dockerfile for a Node web app"
  - "Prisma engine errors (libssl, linux-musl) inside a container"
---

# Next.js + Prisma + SQLite — Docker Self-Host

Proven 2026-06-10 building Mealio (`/root/projects/mealio/app`, live on hil-1:3015).
Every pitfall below was hit live; this ordering avoids ~5 rebuild cycles.
Worked example with live endpoints + phase pipeline: `references/mealio-deployment.md`.
LLM import/extraction wiring + vision-provider capability map (DeepSeek/Nous/Anthropic/OpenAI): `references/llm-import-pipeline-providers.md`.

## Project setup (Next 14.2, App Router, TS)

- **`next.config.mjs`, NOT `.ts`** — Next 14.2 does not support TypeScript config. `postcss.config.js` must be CJS (`module.exports`).
- **`output: 'standalone'`** in next.config — required for the slim Docker runner (`.next/standalone/server.js`).
- **DATABASE_URL must be an ABSOLUTE `file:///` URL** (e.g. `file:///app/data/app.db`). A relative `file:./prisma/dev.db` resolves against the schema dir for the CLI but the CWD at runtime → you get TWO databases (`prisma/dev.db` AND `prisma/prisma/dev.db`) and "no such table" at runtime while the seed reports success. Check with `find . -name "*.db" -not -path "*/node_modules/*"` if tables seem missing.
- **API routes that hit the DB at module/GET scope need `export const dynamic = 'force-dynamic'`** — otherwise `next build` tries to statically export them, executes the DB call at build time, and the Docker build fails on paths like `/api/tags` even though the host build passed (host has the dev DB; the image doesn't).
- **Seed via `npx tsx prisma/seed.ts`** (avoid the ts-node prisma.seed config dance). Re-running the seed against an already-seeded DB duplicates rows — make seeds idempotent or dedupe by createdAt after.

## Dockerfile (multi-stage, Alpine)

```dockerfile
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --ignore-scripts

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npx prisma generate
ENV DATABASE_URL="file:///tmp/build.db"   # placeholder; force-dynamic routes don't touch it
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN apk add --no-cache openssl libc6-compat   # Prisma engine needs these on Alpine
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public      # dir MUST exist on host (mkdir -p public) or COPY fails
COPY --from=builder /app/prisma ./prisma
COPY --from=builder /app/node_modules/.prisma ./node_modules/.prisma
COPY --from=builder /app/node_modules/@prisma ./node_modules/@prisma
RUN mkdir -p /app/data
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh
EXPOSE 3015
CMD ["./docker-entrypoint.sh"]
```

### Prisma-on-Alpine engine fix (the libssl crash)

Runtime error `Error loading shared library libssl.so.1.1 … libquery_engine-linux-musl.so.node` means the generated client carries the OpenSSL-1.1 musl engine but Alpine ships OpenSSL 3. Fix BOTH sides:
1. schema.prisma generator: `binaryTargets = ["native", "linux-musl-openssl-3.0.x"]`
2. runner stage: `apk add --no-cache openssl libc6-compat`
Then full `--no-cache` rebuild.

### Schema sync: two working patterns (in-container preferred as of 2026-06-10)

**Naive `npx prisma db push` in the standalone runner FAILS two ways:** (a) without the prisma package present, npx prints help text and crash-loops the container; (b) worse, npx may download the LATEST prisma major (hit live: fetched Prisma 7.x against a v5 schema → incompatible). Never bare-`npx prisma` inside the runner.

**Pattern A — in-container db push at startup (proven, self-healing on every deploy):**
1. Runner stage additionally copies the real prisma package: `COPY --from=builder /app/node_modules/prisma ./node_modules/prisma`
2. Entrypoint invokes the build entry DIRECTLY (avoids `.bin` symlink/WASM resolution issues in standalone):
```sh
#!/bin/sh
set -e
node ./node_modules/prisma/build/index.js db push --schema /app/prisma/schema.prisma --accept-data-loss
exec node server.js
```
Result: every container start syncs schema against the volume DB, then serves. Verified live (Mealio: "Your database is now in sync" → "Ready in 53ms"). Removes the "forgot to push after schema change" failure class entirely.

**Pattern B — host-side push against the mounted volume (no image change needed):**
```bash
DATABASE_URL="file://$PWD/data/app.db" npx prisma db push --skip-generate
```
Use when you can't rebuild. Symptom that a push was missed either way: P2021 `table does not exist` at runtime while the health endpoint is 200.

## docker-compose

```yaml
services:
  app:
    build: .
    ports: ["3015:3015"]
    volumes: ["./data:/app/data"]
    env_file: [.env.docker]           # runtime secrets — never baked into image
    environment:
      NODE_ENV: production
      PORT: "3015"                    # standalone server defaults to 3000
      HOSTNAME: "0.0.0.0"             # else binds localhost only inside container
      DATABASE_URL: "file:///app/data/app.db"
```

- **Image-tag trap:** `docker build -t myapp:latest .` then `docker compose up -d` does NOT use your image — compose builds/uses its own `<dir>-<service>:latest` tag and may serve a STALE cached entrypoint even after you edited files. Either set `image:` in compose to your tag, or always rebuild through compose, or `docker rmi` BOTH tags + `--no-cache` when an entrypoint/script change doesn't seem to land.
- Secrets (API keys, SESSION_SECRET) go in `.env.docker` via `env_file` — generate SESSION_SECRET with `secrets.token_hex(32)`.
- **Hermes terminal quirk:** `cd <dir> && docker compose up -d` (or chaining it with sleep/curl) can trip the long-lived-server foreground guard even though `up -d` detaches. Workaround that passes: `docker compose -f /abs/path/docker-compose.yml up -d` as a standalone command, then verify with separate calls.

## Verification gate (before claiming live)

1. `docker ps` → `Up`, not `Restarting (1)` (restart loop = entrypoint failing; `docker logs` it).
2. `curl -sf localhost:PORT/api/health` → 200 JSON.
3. Auth endpoints return real JSON (a 500 here with healthy `/api/health` usually = Prisma engine or missing-table issue — check `docker logs` for P2021/libssl).
4. Unauthenticated `/` → 307 to /login if middleware-gated.
5. **Exercise one DB-touching POST end-to-end** — health 200 alone missed a P2021 schema-drift 500 on Mealio. Pattern: `curl -c /tmp/cookies -X POST .../api/auth/signup` with throwaway creds → `curl -b /tmp/cookies /` expecting authenticated 200 → duplicate POST expecting 409 → then DELETE the test row from the DB and rm the cookie jar. A new ROUTE that 404s after a successful rebuild = the compose image-tag trap above, not a code bug.
6. Remind the user to claim the first-run account immediately — setup endpoint is open until first registration.

## Retrofit pattern: attributing existing data to users

Adding ownership/attribution to a live app with existing rows: make the FK **nullable** with `onDelete: SetNull` (`authorId String?` + `author User? @relation(...)`) so `db push` succeeds without data loss and pre-feature rows simply show `author: null` — render that as "no attribution", don't backfill blindly. Stamp the FK in the route handler from the session (`getSessionUserId()`), not from client-submitted JSON. Import/review flows that finalize via the normal create endpoint inherit the stamping for free — check the flow before adding redundant stamping in the import route.

## Verifying DB behavior when auth middleware blocks curl

When every API route 401s and you don't hold valid creds, don't park verification — probe Prisma directly inside the container:
```bash
docker exec <container> sh -c 'node -e "
const {PrismaClient}=require(\"@prisma/client\");
const db=new PrismaClient();
db.recipe.findMany({include:{author:true},orderBy:{author:{email:\"asc\"}},take:3})
  .then(r=>console.log(r.length, JSON.stringify(r[0]?.author)))
  .finally(()=>db.\$disconnect())"'
```
This exercises the exact include/orderBy the route uses, proving schema + query without a session cookie. (Listing user emails the same way also tells you which account exists before guessing logins.)

## Multi-account signup (retrofit pattern)

Adding open registration to the single-user design later is one route + a login-page toggle: `POST /api/auth/signup` (validate email + min-8 pw, 409 on existing email, set the same session cookie) and a `signin|signup` mode state on the login page (toggle button must be `type="button"`; clear errors on mode switch; first-run `setupNeeded` just picks the initial mode). **Flag to the user:** without per-user scoping (userId FK on the data models + query filtering), all accounts share one library — fine for household use, say so explicitly when shipping it.

## Zod validation for LLM-generated payloads

When request bodies originate from an LLM extraction step (import pipelines, AI form-fill), the model emits JSON `null` for absent values — especially if its own prompt says "X or null". Zod `.optional()` accepts only `undefined` and rejects every one of those nulls at save time, often long after the extraction "worked".
- Use `.nullish()` (null | undefined) for every optional field whose value can come from an LLM; keep `.optional()` only for fields that are non-nullable in Prisma (e.g. `Boolean @default(false)` — passing null to create() breaks).
- Derive the TS types from the schemas (`export type FormData = z.infer<typeof schema>`) instead of maintaining a parallel hand-written interface — the duplicates WILL drift and the drift surfaces as a Docker-build-only type error.
- Return field-level Zod errors in the API response (`errors.map(e => e.path.join('.') + ': ' + e.message).join('; ')`), never a bare "Validation error" — opaque errors cost a full debugging round-trip; detailed ones let a screenshot diagnose the bug.
- Beware review/edit UIs that seed empty placeholder rows then filter them on save: a `.min(1)` array constraint rejects the legitimately-empty result. Validate against what the UI can actually send.

## Browser-API + mobile UX pitfalls (HTTP self-host reality)

These bite specifically because self-hosted apps run on plain HTTP and get used from phones:

- **`getUserMedia` (camera/mic) is dead on HTTP** — browsers hard-block it outside secure contexts
  (HTTPS or localhost). Any live-camera feature WILL throw "could not access camera" for every remote
  user no matter the permissions. Pattern: gate on `window.isSecureContext && navigator.mediaDevices?.getUserMedia`,
  fall back to `<input type="file" accept="image/*" capture="environment">` which opens the native
  camera app with no secure-context requirement, then process the captured still (e.g. jsQR on a canvas).
  Note `capture` is a hint: Android/Chrome opens camera directly; iOS shows camera/library sheet;
  desktop ignores it → file picker. Tell the user this, don't promise "opens the camera" universally.
  Real fix is HTTPS via tunnel → see `cloudflare-tunnel-expose` skill.
- **`opacity-0 group-hover:opacity-100` controls are INVISIBLE and untappable on touch devices** —
  no hover state exists. Any delete/edit affordance styled this way is a "feature missing" bug report
  from mobile users. Pattern: visible-but-dim default, hover-reveal only at desktop breakpoints:
  `text-white/30 md:opacity-0 md:group-hover:opacity-100`.
- **API response shape drift between pages:** one page consuming `/api/x` as a flat array while another
  unwraps `data.items ?? []` silently renders an empty list — no error anywhere. When a list UI shows
  nothing but the endpoint curls fine, diff how each consumer parses the response before touching the backend.
- **Verify backend-vs-frontend FIRST on "tab is broken" reports:** curl the API endpoints end-to-end with
  a session cookie (signup throwaway user → exercise → delete). If the API round-trips, the bug is in the
  client parse/render layer — saves rebuilding working backend code.

## Domain-output formatting: think like the end artifact

When generating user-facing lists from structured data (shopping list from recipe ingredients), users
want the OUTPUT domain's conventions, not the input's. Cooking measurements ("6 ounce carrots",
"1 cup shrimp") are wrong on a shopping list — shoppers buy "3 carrots" / "250g shrimp". Pattern that
worked: classify each item (count-item / weight-item / pantry-staple) via keyword lookup, convert
units→grams via per-item average weights and densities, ceil counts, drop amounts entirely for pantry
staples you buy packaged. Expect iteration: the user corrected this twice (abbreviating units wasn't
enough; they wanted full re-expression). Ask or default to the consumption-domain format up front.

## Middleware note (Edge runtime)

`src/middleware.ts` CANNOT import anything pulling node:crypto or Prisma (Edge build failure). Pattern: middleware checks token FORMAT only (cookie present + structure); real HMAC verification lives in server routes/components. Fine for single-user self-hosted.
