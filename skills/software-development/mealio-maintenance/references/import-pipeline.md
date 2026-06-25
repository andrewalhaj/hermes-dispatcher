# Mealio Import Pipeline — Detail

## Flow
`POST /api/import {url}` (auth-gated) →
1. `platformDetect(url)` → youtube | instagram | tiktok | generic
2. `fetchFromUrl(url, platform)` in `src/lib/import/fetcher.ts`:
   - **youtube** → `fetchYouTube()` in `youtubeFetcher.ts` (youtubei.js Innertube, no API key); on throw, falls back to Firecrawl with console.error
   - others → Firecrawl `POST https://api.firecrawl.dev/v1/scrape` with `formats:['markdown']`, Bearer `FIRECRAWL_API_KEY`
3. `extractRecipe(rawText)` in `extractor.ts` — DeepSeek via OpenAI client, `response_format: json_object`, temp 0.1, input truncated to 8000 chars. Env: `DEEPSEEK_API_KEY`, `EXTRACTION_BASE_URL` (default api.deepseek.com/v1), `EXTRACTION_MODEL` (default deepseek-chat)
4. ImportHistory status progression: fetching → reading → structuring → `done` (or `partial` + errorMsg when title AND ingredients AND steps are all empty)
4b. **Hero image upgrade + page capture** — `searchFoodWeb(extracted.title)` in `foodImageSearch.ts` runs for non-generic platforms when a title was extracted: Firecrawl `POST /v1/search` with `{query: "<title> recipe", limit: 3, scrapeOptions: {formats:['markdown'], onlyMainContent:true}}`. WITHOUT scrapeOptions, search results carry only url/title/description — no images. With it, each result has `metadata.ogImage` (fallback key `metadata['og:image']`); iterate results until a valid `https?://` image. Returns `{imageUrl, pageMarkdown, pageUrl}` — pageMarkdown is the first result whose markdown is >500 chars (`findFoodImage` remains as a thin compat wrapper). Recipe-site og-images are professional photos of the dish. Never throws; priority: food photo > `fetched.thumbnailUrl` > none. Rationale: YouTube `basic_info.thumbnail` often resolves to the channel avatar (yt3.ggpht.com = creator's face), not food.
4c. **Supplemental step extraction** — if `extracted.steps.length === 0` and `pageMarkdown` exists: run `extractRecipe(pageMarkdown)` a second time; if it yields steps, merge them in, and fill ingredients/prepTime/cookTime/servings ONLY where the primary extraction was empty (video-description ingredients stay authoritative). Prepend provenance to `extracted.notes`: `Steps sourced from <pageUrl> (video description had no instructions).` The notes field flows through the review page into the saved recipe (recipeSchema accepts notes ≤5000 chars). The `partial`/`done` status check MUST run after this merge. Route has `maxDuration = 180` (fetch + 2 LLM calls + search can exceed the old 60s).
5. Response: `{importId, platform, sourceUrl, sourceAttr, extracted}` — user reviews, then saves via normal `POST /api/recipes` (which stamps authorId from session)

## Screenshot import path (parallel route, built 2026-06-10)

`POST /api/import/image` (multipart `image` field; paperclip button in Nav triggers hidden file input):
1. Validate: file present, `type.startsWith('image/')`, ≤8MB → 400 with specific message otherwise
2. **Vision-key guard runs BEFORE the importHistory create** — `!process.env.VISION_API_KEY` → 503 "Screenshot import requires a vision model — set VISION_API_KEY, VISION_BASE_URL and VISION_MODEL in .env.docker" and NO orphan history row
3. History record: `{url: 'screenshot:<filename>', platform: 'screenshot', status: 'structuring'}` (platform column is plain String — no enum to widen)
4. `extractRecipeFromImage(base64, mimeType)` in `visionExtractor.ts`: OpenAI-compatible client, same EXTRACTION_PROMPT as text extractor, user content = `[{type:'text',...},{type:'image_url', image_url:{url: 'data:<mime>;base64,<b64>'}}]`. Env: `VISION_API_KEY` / `VISION_BASE_URL` (default api.openai.com/v1) / `VISION_MODEL` (default gpt-4o-mini). Throws literal `'VISION_NOT_CONFIGURED'` when keyless.
5. Reuses steps 4b/4c above (hero image search + supplemental steps), same done/partial logic
6. Response shape identical to URL route but `platform:'screenshot'`, `sourceUrl:''`, `sourceAttr:'Imported from screenshot'` — review screen needs zero changes (sourceUrl `''` passes `z.string().url().nullish().or(z.literal(''))`)

Nav flow mirrors URL import: FormData POST → progress toast states → sessionStorage `mealio-import` → router.push review. E2E without a key: tiny base64 PNG → expect 503; non-image → 400; history count for platform screenshot stays 0.

## Review-screen save path (validation coupling)
The review page (`src/app/import/review/page.tsx`) seeds one empty placeholder row for ingredients/steps when extraction returned none, filters empties on save, then POSTs to `/api/recipes`. Consequence: a 0-step extraction sends `steps: []`. `recipeSchema` (src/lib/validation.ts) must therefore keep `steps` without `.min(1)` (ingredients keep `.min(1)`). The 2026-06-10 \"Validation error\" bug was exactly this coupling, made worse by the API returning a detail-free error string — now it joins Zod `errors[].path + message` into the response.

## YouTube fetcher (youtubei.js v17)
```ts
const yt = await Innertube.create({ generate_session_locally: true })
const info = await yt.getInfo(videoId)   // videoId from /(?:v=|youtu\.be\/|shorts\/|embed\/)([A-Za-z0-9_-]{11})/
// v17: NOT basic_info for these —
title:       info.primary_info.title.text
description: info.secondary_info.description.text
channel:     info.secondary_info.owner.author.name
// transcript — often 400s from datacenter IPs; wrap in try/catch:
const t = await info.getTranscript()
segs = t?.transcript?.content?.body?.initial_segments  // each: s.snippet.text
```
rawText format fed to LLM: `VIDEO TITLE: ...\n\nDESCRIPTION:\n...\n\nTRANSCRIPT:\n...`

## Why Firecrawl failed for YouTube (2026-06-10 incident)
Scrape of a recipe video returned 8.6KB markdown: Google 403 boilerplate, "Shorts remixing this video", comment headers — `success: true`, metadata title correct, but keyword scan (cup/tbsp/garlic/butter/ingredient) all ABSENT. Description/transcript are JS lazy-loaded; Firecrawl's render doesn't capture them. LLM correctly extracted nothing; old code still marked history `done` with recipeId null — that combination (done + null recipeId, repeated) is the diagnostic signature of this failure.

## Verified working result (same URL after all fixes)
youtube.com/watch?v=LPPcNPdq_j4 (Natasha's Kitchen alfredo) → title + 11 structured ingredients + cuisine/tags from description; **7 steps via supplemental extraction** from a framedcooks.com page (provenance note attached); hero = framedcooks.com plated-dish photo. Channel attribution: "Imported from Natashas Kitchen on YouTube".

## Build note
youtubei.js sits in `dependencies` and is bundled by Next standalone — no `serverComponentsExternalPackages` needed (build passed without config change). Its .d.ts `#private` fields emit TS18028 lint noise; harmless, ignore.
