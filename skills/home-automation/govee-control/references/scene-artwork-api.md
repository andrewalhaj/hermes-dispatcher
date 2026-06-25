# Govee Scene Lists + Artwork (undocumented app endpoint)

The **official** OpenAPI (`openapi.api.govee.com`) returns scene control data only —
`name → paramId → id` mappings, no artwork, no thumbnails. Verified: grep a cached
scene response for any `http(s)://` or image/url/thumb key → empty.

The colorful scene previews shown in the Govee phone app come from a **separate,
undocumented app API**. The key win: the scene-library endpoint is **AUTH-FREE** —
no Govee login/email/password needed, only the device SKU (which the official API
already gives you via `govee.py list`).

## The endpoint

```
GET https://app2.govee.com/appsku/v1/light-effect-libraries?sku=<SKU>
Headers:
  AppVersion: 6.5.02
  User-Agent: GoveeHome/6.5.02 (com.ihoment.GoVeeSensor; build:2; iOS 16.5.0) Alamofire/5.6.4
```

No `Authorization` header required for this path. Returns
`data.categories[].scenes[]`, each scene with:
- `sceneName`, `sceneId`, `lightEffects[].sceneCode` (a.k.a. paramId)
- `iconUrls`: **3 PNG variants** — `[normal, pressed, dark]`. Prefer the `_dark`
  variant for a dark dashboard UI.

The icon images live on a **public CloudFront CDN** (`d1f2504ijhdyjw.cloudfront.net`)
— fetch them with no auth at all (plain GET → HTTP 200, valid PNG).

## Source of truth

Reverse-engineered from `wez/govee2mqtt` (`src/undoc_api.rs`). That repo also has a
captured sample response at `test-data/light-effect-library-h6072.json`. The
`APP_VERSION`/`User-Agent` constants above are copied from there; bump them if Govee
starts rejecting the call.

## Fetch-all-art recipe

For a set of SKUs, pull every scene library, pick the `_dark` icon, dedup by scene
name (Govee art is shared across SKUs), and download to a local dir. ~260 unique
thumbnails covered ~96% of all scene names across 5 devices (H1401/H1630/H6604/
H6006/H1310). The remaining misses are `-D`/`-F` numeric variants — fall back to the
base-name art (strip a trailing `-A`/`-B`/`-C`/`-D` suffix).

A ready-to-run fetcher lives at `scripts/fetch_scene_art.py` in this skill.

## Caveats / risk

- Undocumented + private = **fragile**. Govee can change or gate it any time. If it
  starts 401/403-ing, the auth-free property is gone — that's the canary.
- ToS-gray. Fine for personal dashboards; do not redistribute the artwork.
- The official scene-control path (paramId/id via shell_command/input_select) is the
  stable one — use the app endpoint only for the *visual* layer, never as the control
  mechanism.
