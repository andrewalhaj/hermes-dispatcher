# ha-fusion: source-patch + custom Docker rebuild

When a feature isn't config-expressible (the shipped image is a compiled SvelteKit
build under `/app/build`), you must patch the Svelte source and rebuild the image.
This recipe is proven end-to-end on the **amedello fork** (`ghcr.io/amedello/ha-fusion`,
tag `v2026.5.3`). Two features were added in one rebuild: real Govee scene-art
thumbnails in the scene picker, and a circular climate dial.

## Golden rule: investigate the shipped source BEFORE promising a feature
Clone the EXACT fork + tag the user runs — NOT upstream matt8707 (the fork adds
`custom_panel` and other types upstream lacks):
```bash
git clone --depth 1 --branch v2026.5.3 https://github.com/amedello/ha-fusion.git
```
Read the relevant component to confirm the capability path exists. Key files:
- `src/lib/Main/Content.svelte` — main-grid item-type dispatcher. ONLY renders
  `configure|button|conditional_media|picture_elements|camera|empty|custom_panel`.
  Anything else (e.g. `template`) → silent empty fallback. `template` is sidebar-only.
- `src/lib/Modal/InputSelectModal.svelte` — scene/option picker; maps options to
  `{id, label}` (text only).
- `src/lib/Components/Select.svelte` — renders the option list; supports a per-option
  `icon` via iconify `<Icon icon={name}>` (named vectors, NOT arbitrary image URLs).
  List is virtualized (`svelte-tiny-virtual-list`), no per-row CSS hook.
- `src/lib/Main/CustomPanel.svelte` — fork's tile component (icon+name+state, opens modal).
- `src/lib/Types.ts` — `CustomPanelItem`, `ModalRow*` interfaces.
- `static/` — files here are served at web root by the built client (`/app/build/client/<path>`).

## Patch set 1 — scene-art thumbnails in the picker
1. Fetch art + build a name→path map (auth-free — see govee-control skill's
   `scripts/fetch_scene_art.py`). Drop PNGs in `static/scene_art/` and generate
   `src/lib/sceneArt.ts` exporting `sceneArt: Record<string,string>` plus a
   `sceneImage(name)` helper with a base-name fallback (strip trailing `-A/-B/-C`).
2. `InputSelectModal.svelte`: `import { sceneImage } from '$lib/sceneArt'` and add
   `image: sceneImage(option)` to each mapped option object.
3. `Select.svelte`: add `image?: string` to the `options` type; in the item render
   block add a branch BEFORE the icon branch:
   ```svelte
   {#if filter?.[index]?.image}
       <div class="item-image"><img src={filter?.[index]?.image} alt="" loading="lazy" /></div>
   {:else if filter?.[index]?.icon || computeIcons}
       ...existing icon block...
   {/if}
   ```
   Add `.item-image { width:2rem;height:2rem;border-radius:.4rem;overflow:hidden } .item-image img { width:100%;height:100%;object-fit:cover }`.

## Patch set 2 — climate dial (main-grid)
A dial in the main grid CANNOT be a `template` item (see golden rule). Extend the
proven `custom_panel` type instead:
1. `Types.ts` `CustomPanelItem`: add `display?: 'tile'|'dial'; climate_entity?: string; humidity_entity?: string;`.
2. `CustomPanel.svelte`: read `(item as any).display === 'dial'`, pull
   `$states[climate_entity]` attributes (`temperature` = target, `current_temperature`,
   `hvac_action`, `fan_mode`, `current_humidity`). Render a CSS circular ring when
   `isDial`, else the existing tile. Live clock = local `setInterval(fmtTime,15000)`
   in `onMount`/`onDestroy` (NO `$clock` store exists). Ring `border-color` from
   `hvac_action` (cooling `#3b9dff`, heating `#ff7a3b`, else translucent white).
3. dashboard.yaml: replace the multi-button Climate tile with one
   `type: custom_panel` item carrying `display: dial`, `climate_entity:`,
   `humidity_entity:`, and `rows:` (sensor/buttons) for the tap-through modal.

## Build → ship → swap (do local first, gate prod on greenlight)
`npm run build` (SvelteKit/Vite) needs ~2GB+ RAM — it OOMs on a small HA host.
Build on a beefier box (Node 22 + Docker), then transfer the image:
```bash
# 1. Build locally
docker build -t ha-fusion:custom .
# 2. Self-test locally (zero prod impact): run on a temp port, curl HTTP 200,
#    curl a /scene_art/X.png (200 + image/png), grep compiled chunks to confirm
#    your code is in the bundle (server chunk Index2-*.js AND client
#    _app/immutable/chunks/*.js + the Select/Index CSS asset — NOT just .map files).
# 3. Ship (save+gzip is faster than registry push for a one-off)
docker save ha-fusion:custom | gzip -1 > /tmp/img.tar.gz
scp /tmp/img.tar.gz root@HOST:/tmp/
ssh root@HOST 'gunzip -c /tmp/img.tar.gz | docker load'
# 4. Snapshot current container config for rollback, back up data dir, then swap
ssh root@HOST 'docker inspect ha-fusion --format "{{json .HostConfig.PortBindings}}"; \
  cd /root/ha-fusion/data && cp dashboard.yaml dashboard.yaml.bak && cp custom_style.css custom_style.css.bak'
ssh root@HOST 'docker stop ha-fusion && docker rm ha-fusion && \
  docker run -d --name ha-fusion --restart unless-stopped \
    -p 100.119.118.54:5050:5050 \   # PRESERVE the Tailscale-only bind, NOT 0.0.0.0
    -e TZ=UTC -e HASS_URL=http://HOST:8123 -e PORT=5050 -e NODE_ENV=production -e ADDON=false \
    -v /root/ha-fusion/data:/app/data \
    ha-fusion:custom'
```
**Rollback is instant**: the original `ghcr.io/amedello/ha-fusion:v2026.5.3` image is
untouched on the host — one `docker run` with the old tag + restore the `.bak` data
files reverts everything.

## Verification (server-side; user confirms visually — Tailscale-only is unreachable from cloud)
- `curl -o /dev/null -w "%{http_code}" http://100.119.118.54:5050/` → 200
- `curl .../scene_art/<one>.png` → 200, `image/png`, non-trivial size
- `ss -tlnp | grep 5050` → bound to `100.119.118.54:5050`, NOT `0.0.0.0` (security)
- `docker logs ha-fusion | tail` → no errors (a Node `util._extend` DeprecationWarning is harmless)
- Deploy dashboard.yaml + custom_style.css to `/root/ha-fusion/data/` (these hot-reload);
  validate YAML with `python3 -c "import yaml; yaml.safe_load(open(...))"` before shipping.

## Pitfalls
- Build OOMs on the HA host → build elsewhere, ship the image.
- LSP "Cannot find module '$lib/sceneArt'" right after writing it is just an un-indexed
  new file; the Vite build resolves it fine. Trust the `docker build` exit code.
- Grep the COMPILED bundle (not source, not `.map`) to prove your patch shipped —
  Svelte scopes CSS and minifies, so search both server chunks and
  `client/_app/immutable/{chunks,assets}`.
- Always do the full local build + self-test before touching prod; pause for explicit
  greenlight before the container swap (Andrew's standing infra-change rule).
