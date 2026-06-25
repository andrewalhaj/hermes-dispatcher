---
name: used-network-hardware-sourcing
description: "Recommend and source used networking / home-lab hardware"
---

# Used Network Hardware Sourcing

For helping the user pick and buy used enterprise/lab networking gear — most often Cisco Catalyst switches for CCNA/CCNP study that must ALSO live quietly in a home network. Two jobs: (1) recommend the right MODEL by decoding the part number, (2) find and vet real listings.

## When to use
- "Recommend a layer 3 switch for CCNA" / "what should I buy for a home lab"
- "Is this eBay listing good?" (paste of a listing URL)
- "Find me strong eBay listings for <model>"
- Any used enterprise-gear procurement where feature tier + price + noise/power matter.

## Core principle: the model SUFFIX decides everything

Do NOT recommend or approve a switch by name alone. The part-number suffix encodes the license tier and uplink speed, which determine whether it can even do the task. **Always confirm the exact suffix before approving a listing — the headline model is not enough.**

### Cisco Catalyst suffix decode (3560/3750/3850/3560-CX families)

License tier (last letter of the part number):
- **`-L` = LAN Base** — switching only. NO `ip routing`, NO SVIs for inter-VLAN routing, NO OSPF. **Disqualifies it for CCNA L3 work.** Unlocking requires a separate paid IP Base license. Reject `-L` for any Layer 3 / CCNA routing need.
- **`-S` = IP Base** — full L3: SVIs, inter-VLAN routing, static routes, OSPFv2, ACLs. This is the CCNA minimum. ✅
- (`IP Services` = superset of IP Base; also fine, rarer/pricier.)

Port/uplink type (middle of a 3560-CX part, e.g. `12PC` / `12PD` / `12TC`):
- **`PC`** = PoE+ copper, **2× 1G SFP** uplinks.
- **`PD`** = PoE+ copper, **2× 10G SFP+** uplinks. Meaningful upgrade if the user may ever want a fast inter-host link (e.g. to an inference/NAS node) — needs SFP+ modules (~$15-30 used) + a 10G NIC on the host. CCNA coverage identical to PC.
- **`TC`** = data-only (no PoE), copper + SFP. Cheaper/quieter; fine for pure study.

Worked example from a real session: a listing titled "WS-C3560CX-12PC-S" turned out on inspection to actually be a **12PD-S** (10G uplinks) — a *better* switch than asked for. And a "WS-C3750X-48P-**L**" at $200 was a hard pass: LAN Base = no L3 = wrong for CCNA, plus loud fans and overpriced.

## Recommendation heuristics (CCNA + quiet home network)

- **Default pick: Cisco Catalyst 3560-CX with `-S` suffix** (`WS-C3560CX-8PC-S` / `-12PC-S`). Fanless, silent, ~15-30W, compact, IOS-XE 15.2, full L3. The dual-purpose winner. Fair used price **~$85-180**; above ~$200 walk unless it's a `PD` (10G).
- **8-port vs 12-port:** 8PC-S does everything for CCNA at $20-40 less. Pay up for 12 only if the user wants the extra physical ports for their real network.
- **Budget floor:** 3560-CG (older IOS 15.0, fanless, L3) ~$70-100.
- **AVOID for a quiet home:** 3650 / 3750-X full-width 48-port units. More features (StackWise) but **fans = jet-engine noise, 80-150W+**. Only OK if racked away from living space. Wrong for a desk/shelf.
- **The honest footnote:** CCNA 200-301 needs ZERO physical hardware — Packet Tracer (free) covers the whole blueprint. Recommend real gear because the user wants a silent L3 switch in their network AND tactile practice, not because the cert demands it.

### Pre-purchase checklist to give the user
- Listing/`show version` photo shows **IP Base or IP Services** (not LAN Base).
- Buy a **console cable** (3560-CX has mini-USB console + RJ45 console).
- Confirm IOS version; avoid wiped/password-locked configs you can't recover.
- Seller feedback: prefer **99%+ and high volume** (e.g. 8K-86K feedback). **Reject low-feedback / sub-90% sellers** even if cheapest (saw a 75%/13-review seller — hard no).

## Pulling live eBay listings (antibot workaround — this is the fragile part)

eBay aggressively blocks scraping. **`web_extract` on an `/itm/` URL fails** (`document_antibot`, retry-limit). **Direct `browser_navigate` to a deep `/itm/...` URL with tracking params often returns eBay's "SORRY / something went wrong" 500 page.** Don't trust a single failed nav as "listing gone."

Reliable sequence that works:
1. `browser_navigate` to **`https://www.ebay.com`** first (warms the session).
2. Then `browser_navigate` to a clean search URL:
   `https://www.ebay.com/sch/i.html?_nkw=<MODEL>&_sop=15&LH_BIN=1`
   - `_sop=15` = sort price+shipping lowest first; `LH_BIN=1` = Buy-It-Now only. Drop `LH_BIN` to include auctions.
3. Read results with **`browser_vision`** (ask for title, price, condition, seller name + feedback %, shipping) — the accessibility snapshot only reliably surfaces the "people also viewed" rail, not the main result grid. `browser_scroll` down + repeat `browser_vision` to page through.
4. For a specific listing the user pasted: strip the tracking params to the bare `https://www.ebay.com/itm/<id>`, and navigate AFTER hitting the homepage. If it still 500s, retry; the main-item grid + "people also viewed" rail in the snapshot still reveals the model/title even when vision of the hero card is needed for price.

## Pitfalls
- Approving a switch by headline model without checking the suffix → recommending a LAN Base box for L3 work. **#1 mistake.** Always decode the suffix.
- Trusting one failed `browser_navigate`/`web_extract` as proof a listing is dead — eBay 500s and antibot are transient/structural, not "gone." Hit the homepage first, retry.
- Forgetting noise/power in a HOME context — a feature-rich 3750X is the wrong answer if it screams next to the user's desk.
- Over-paying: used IP Base 3560-CX is an $85-180 part; flag anything materially above that.
