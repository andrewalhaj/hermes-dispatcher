# Apify Instagram fetcher — verified working call + diagnosis (2026-06-13)

Replaces the dead Firecrawl IG path. Verified live against the Apify API on hil-1.
Key lives in hil-1 `.env.docker` as `APIFY_API_KEY` (free tier — gives RESIDENTIAL proxy access).

## The actor that works
- **Actor:** `apify/instagram-scraper`, actor ID `shu8hvrXbJbY3Eb9W` (the generic one — handles post/reel URLs via `directUrls`).
- Avoid these for single-URL caption fetch:
  - `apify/instagram-reel-scraper` and `apify/instagram-post-scraper` → require a `username` input field, not a direct URL.
  - `hpix/ig-reels-scraper` → **paid rental required** (`actor-is-not-rented` after free trial).

## The call that actually returns a caption
RESIDENTIAL proxy is **mandatory** — without `apifyProxyGroups:['RESIDENTIAL']` even public posts come back `not_found`/BLOCKED, because Instagram blocks datacenter IPs at the GraphQL endpoint on the first request.

```bash
KEY="$APIFY_API_KEY"
# Start run + wait (waitForFinish caps at 120s server-side)
RUN=$(curl -s -X POST \
  "https://api.apify.com/v2/acts/shu8hvrXbJbY3Eb9W/runs?token=$KEY&waitForFinish=120" \
  -H "Content-Type: application/json" \
  -d '{"directUrls":["https://www.instagram.com/<shortcode>/"],"resultsType":"posts","resultsLimit":1,"proxy":{"useApifyProxy":true,"apifyProxyGroups":["RESIDENTIAL"]}}')
# Pull dataset
DS=$(echo "$RUN" | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"]["defaultDatasetId"])')
curl -s "https://api.apify.com/v2/datasets/$DS/items?token=$KEY"
```

Success item shape (relevant fields): `caption`, `ownerUsername`, `displayUrl` (hero), `type` (`"Video"` for reels).
Verified working public account: `minimalistbaker` returned a full clean caption.

## Diagnosing failures — `not_found` is NOT always "scraper broken"
The run can `SUCCEEDED` while the single dataset item carries `error`. Branch on it:
- `error: "not_found"` + `errorDescription: "Post does not exist"` → almost always a **private / login-walled / geo-restricted account**, NOT a scraper bug. Confirm independently: a plain GraphQL hit returns `{"require_login":true}` for these:
  ```bash
  curl -s "https://www.instagram.com/graphql/query/?query_hash=2b0673e0dc4580674a88d426fe00ea90&variables=%7B%22shortcode%22%3A%22<SHORTCODE>%22%7D" -H "User-Agent: Mozilla/5.0"
  # require_login:true  → the post itself needs auth; no sessionless scraper can get it
  ```
  A raw `curl` of the reel URL returning HTTP 200 is misleading — that 200 is the login-wall shell, not the content.
- `error: "no_items"` → run hit the account but extracted nothing (often the same login wall on a profile fetch).
- Run log shows `WARN ... BLOCKED ... handleRestrictedPost` retried 4× then `This content is not available` → Instagram blocked the session; with RESIDENTIAL already set, this means the content needs login (private), not a proxy-quality issue.

Pull the run log to see the real reason:
```bash
curl -s "https://api.apify.com/v2/actor-runs/<RUN_ID>/log?token=$KEY" | tail -30
```

## Verifying the key
```bash
curl -s "https://api.apify.com/v2/users/me?token=$KEY" | python3 -c 'import json,sys;d=json.load(sys.stdin)["data"];print(d["username"],d["plan"]["id"])'
# valid key → prints username + plan (e.g. FREE)
```

## Fetcher contract (what `instagramFetcher.ts` returns)
Returns a `FetchResult`: `{ platform:'instagram', rawText: caption, thumbnailUrl: displayUrl, sourceAttr: 'Imported from @<owner> on Instagram' }`.
Caption flows into the existing DeepSeek `extractor`; hero re-resolved through existing `searchFoodWeb` (social thumbnails are the creator's face, not food).
On `not_found`/empty-caption, throw a user-facing message pointing at the screenshot/📎 path rather than a raw API error — that path is the no-auth fallback for private posts.

## Wiring point
`fetchFromUrl` in `src/lib/import/fetcher.ts`: add `if (platform === 'instagram') return await fetchInstagram(url)` BEFORE the Firecrawl fallback block, and drop `instagram` from the Firecrawl-path creator-extraction conditional (instagramFetcher owns IG attribution now).
