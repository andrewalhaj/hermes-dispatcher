#!/usr/bin/env python3
"""Fetch Govee scene artwork from the auth-free undocumented app endpoint.

Downloads the 'dark' icon variant per scene, dedups by name, writes a
name->local-path map. No Govee login required — only device SKUs.

Usage:
    python3 fetch_scene_art.py H1401 H1630 H6604 [--out /tmp/scene_art_build]

SKUs come from `python3 govee.py list` (the official OpenAPI). See
references/scene-artwork-api.md for endpoint details and caveats.
"""
import json, os, sys, urllib.request, hashlib

HDR = {
    "AppVersion": "6.5.02",
    "User-Agent": "GoveeHome/6.5.02 (com.ihoment.GoVeeSensor; build:2; iOS 16.5.0) Alamofire/5.6.4",
}


def fetch_lib(sku):
    url = f"https://app2.govee.com/appsku/v1/light-effect-libraries?sku={sku}"
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def pick_icon(icon_urls):
    """Prefer the '_dark' variant for dark UIs; fallback to first."""
    if not icon_urls:
        return None
    for u in icon_urls:
        if "_dark" in u:
            return u
    return icon_urls[0]


def main(argv):
    skus = [a for a in argv if not a.startswith("--")]
    out_dir = "/tmp/scene_art_build"
    if "--out" in argv:
        out_dir = argv[argv.index("--out") + 1]
    if not skus:
        print("usage: fetch_scene_art.py SKU [SKU...] [--out DIR]")
        return 1

    img_dir = os.path.join(out_dir, "scene_art")
    os.makedirs(img_dir, exist_ok=True)

    name_to_img, downloaded, stats = {}, {}, {}
    for sku in skus:
        try:
            d = fetch_lib(sku)
        except Exception as e:
            stats[sku] = f"ERROR {e}"
            continue
        cats = d.get("data", {}).get("categories", [])
        n = 0
        for c in cats:
            for s in c.get("scenes", []):
                name = (s.get("sceneName") or "").strip()
                if not name:
                    continue
                icon = pick_icon(s.get("iconUrls", []))
                if not icon:
                    continue
                if name in name_to_img:
                    n += 1
                    continue
                if icon in downloaded:
                    name_to_img[name] = downloaded[icon]
                    n += 1
                    continue
                h = hashlib.md5(icon.encode()).hexdigest()[:12]
                safe = "".join(ch if ch.isalnum() else "_" for ch in name)[:40]
                fname = f"{safe}_{h}.png"
                fpath = os.path.join(img_dir, fname)
                try:
                    req = urllib.request.Request(icon, headers={"User-Agent": HDR["User-Agent"]})
                    with urllib.request.urlopen(req, timeout=20) as r:
                        data = r.read()
                    with open(fpath, "wb") as f:
                        f.write(data)
                    rel = f"/scene_art/{fname}"
                    downloaded[icon] = rel
                    name_to_img[name] = rel
                    n += 1
                except Exception as e:
                    stats.setdefault("img_err", []).append(f"{name}: {e}")
        stats[sku] = f"{n} scenes, {len(cats)} cats"

    with open(os.path.join(out_dir, "scene_art_map.json"), "w") as f:
        json.dump(name_to_img, f, indent=2)

    print(json.dumps(stats, indent=2))
    print(f"\nUnique scene names mapped: {len(name_to_img)}")
    print(f"Images downloaded: {len(set(name_to_img.values()))}")
    print(f"Out: {img_dir}  |  Map: {os.path.join(out_dir, 'scene_art_map.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
