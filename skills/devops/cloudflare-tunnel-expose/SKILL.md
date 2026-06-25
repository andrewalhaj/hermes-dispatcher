---
name: cloudflare-tunnel-expose
description: "Expose self-hosted services via Cloudflare Tunnel"
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [cloudflare, cloudflared, tunnel, https, dns, selfhost, expose]
    related_skills: [nextjs-prisma-docker-selfhost, infra-incident-triage]
    created_by: agent
load_when:
  - "exposing a self-hosted app/service to the internet over HTTPS"
  - "setting up or debugging cloudflared / Cloudflare Tunnel"
  - "cloudflared errors: control stream failure, 530, 502, invalid tunnel secret"
  - "user wants a domain/subdomain pointed at a local port"
---

# Cloudflare Tunnel — Expose Self-Hosted Services

Proven 2026-06-11 putting Mealio (hil-1:3015) behind `https://mealio.andrewskingdom.com`.
Gives free HTTPS, hides origin IP, no open ports. Preferred over raw `IP:port` sharing
(plaintext logins, no rate limiting, IP exposure).

## Setup path (dashboard-token flow — simplest)

1. User creates tunnel at one.dash.cloudflare.com → Networks → Tunnels → Create. They copy the
   connector token (`eyJ...` blob from the `cloudflared service install eyJ...` command).
2. **Token anatomy:** base64 JSON `{"a":"<accountId>","t":"<tunnelId>","s":"<secret>"}`.
   ALWAYS `base64 -d` it on receipt — compare `t` against any previous token to detect that the
   user recreated the tunnel (new tunnel = old token dead).
3. Install as systemd service (Linux box, not the .exe command the dashboard shows):
   `cat templates/cloudflared.service` — token read from a `chmod 600` file, never inline.
4. User adds Public Hostname in the tunnel's dashboard page: subdomain + domain, type HTTP,
   URL `localhost:<port>`. Config pushes to the connector live — no restart needed.
5. Verify: service logs show `Updated to new configuration config="{\"ingress\":[...]}"` followed by
   `Registered tunnel connection` ×4, then `curl -s -o /dev/null -w "%{http_code}" https://host` → app status.

## Pitfalls (each one cost a debugging round live)

- **QUIC masks auth errors.** `control stream encountered a failure while serving` on repeat is
  USELESS — it's the generic QUIC-side symptom for several distinct causes. Re-run with
  `--protocol http2` and the real error surfaces (live case: `Unauthorized: Invalid tunnel secret`).
  Keep `--protocol http2` in the service unit permanently; nothing of value is lost.
- **`Invalid tunnel secret`** = the token's `s` no longer matches the tunnel (tunnel deleted/recreated,
  token rotated). Decode both tokens; if tunnel IDs differ, it IS a different tunnel. Get a fresh
  token from the current tunnel's install command.
- **HTTP 530 OR 502 with all connections registered = stale DNS CNAME** pointing at a DIFFERENT
  (old/deleted) tunnel. Happens when the hostname previously lived on another tunnel: Cloudflare
  won't overwrite the existing CNAME when the new tunnel adds the same Public Hostname. The 502
  variant is the trap — the connector is fully healthy (4× `Registered tunnel connection`, ingress
  pushed) so you chase the connector for ages. **Decisive tell: the request never appears in the
  connector logs at all** — Cloudflare's edge generates the 502 itself because its routing table sends
  the hostname to a dead connector. Confirm origin is fine first (`curl -H "Host: <host>"
  http://127.0.0.1:<port>` → 200), then it's pure DNS. Fix: edit the `<sub>` CNAME in DNS → Records
  to target `<current-tunnel-id>.cfargotunnel.com` (keep Proxied ✓), or delete the record and re-save
  the Public Hostname entry. Recover the *old* tunnel ID from prior token backups
  (`base64 -d` each `token.bak-*` and read `.t`) to prove which dead tunnel the record points at.
  NOTE: the `<tunnel-id>.cfargotunnel.com` CNAME target is NOT visible via public `dig` when the
  record is Proxied (you'll only see Cloudflare Anycast IPs) — you must read it in the dashboard or
  via the CF API.
- **No Public Hostname configured** also presents as control-stream failures/crash-looping — the
  connector registers but has no ingress. Check the dashboard before chasing connector-side causes.
- **Multi-connector routing lottery (one tunnel token on two hosts) = intermittent 502.** A single
  tunnel can have many connectors registered (e.g. the SAME `eyJ...` token deployed on two boxes).
  Cloudflare round-robins each hostname's requests across ALL connectors. If the tunnel's ingress maps
  `hostA→localhost:8787` and `hostB→localhost:3015` but each connector only has ONE of those ports
  locally, then ~half of requests land on the wrong box and 502 with
  `dial tcp 127.0.0.1:<port>: connect: connection refused` in THAT box's connector log. Symptom: the
  same URL returns 200 then 502 then 200 on repeated curls. **Tell from a stale CNAME:** here the
  request DOES reach a connector (you see the refused-dial error in one host's logs); with a stale
  CNAME no connector ever logs the request. **Correct shape: one tunnel per origin host.** Give each
  box its own tunnel (own token), and put each hostname's Public Hostname on the tunnel whose connector
  actually has that local port. Don't share one token across hosts unless every host serves every
  ingress port.
- **VERIFY WHAT'S BEHIND THE PORT BEFORE WIRING THE TUNNEL.** A tunnel to `localhost:<port>` returning
  200 only proves *something* answers — not that it's the app the user wants. Before declaring done,
  curl the local origin and check the page `<title>`/content, and confirm WHICH project/build/service
  serves that port (`ss -tlnp | grep :<port>` → pid → unit → WorkingDirectory/DIST_DIR). Wiring a
  tunnel to the wrong build looks like a tunnel success but ships the wrong UI — a server-side 200 is
  a false-positive for "the right thing is exposed."
- **Long tokens get mangled by shell middleware.** If the platform/sanitizer truncates or rewrites the
  `eyJ...` blob in commands (symptom: `Provided Tunnel token is not valid` with a short byte count),
  do NOT keep pasting it into shell strings. Reconstruct it from decoded JSON fields via a Python
  heredoc writing to a file, verify `wc -c` (~180-190 chars) and `base64 -d` round-trip, then have the
  service read it: `ExecStart=/bin/bash -c '... --token "$(cat /root/.cloudflared/token)"'`.
- **`cloudflared tunnel login`** (cert-based flow) needs an interactive browser and prints its URL to a
  TTY — on a headless server prefer the dashboard-token flow; don't fight the login flow.
- **Local negative DNS cache on the origin server.** Right after the DNS record is created, the origin
  box itself may return `Could not resolve host` (curl exit 6) while the record already resolves
  globally. Verify with `dig @1.1.1.1 <host> +short` (authoritative-ish view), then test the tunnel with
  `curl --resolve <host>:443:<cf-ip> https://<host>` to bypass the stale local resolver. Don't declare
  the setup broken — external clients resolve fine immediately.

## CF API token (account-scoped) — when the user hands you one

A `cfut_...` account API token lets you read/repair without the dashboard. Write it to a file and
read from there — **the platform masks tokens substituted directly into shell command strings** (you
get a literal `***` and the call fails with `Authentication error`/9106). Pattern:
`curl -s -H "Authorization: Bearer $(cat /tmp/cf2.txt)" <url>`.
- Verify: `GET https://api.cloudflare.com/client/v4/user/tokens/verify` → `status: active`.
- List tunnels + health: `GET .../accounts/<acct>/cfd_tunnel?is_deleted=false` → shows each tunnel's
  `name` and `status` (`healthy`/`down`/`degraded`) — fast way to see which tunnel a box is failing on.
- Find/fix DNS: `GET .../zones?name=<domain>` for zone id, then
  `GET .../zones/<zone>/dns_records?type=CNAME` shows each hostname's `<tunnel-id>.cfargotunnel.com`
  target — this is how you read the Proxied CNAME target that `dig` hides.
- Minting a *connector* token (`.../cfd_tunnel/<id>/token`) needs `Cloudflare Tunnel:Edit` scope; a
  read-only token returns 9106 there. If you lack that scope, reuse a connector token the user already
  pasted that you saw register successfully — its secret is proven good.

## Verification gate

1. `systemctl status cloudflared` → active, logs show ≥1 `Registered tunnel connection` and the
   expected ingress hostname in `Updated to new configuration`.
2. **scp tokens between hosts, never heredoc them.** A `ssh host 'bash -s' <<'REMOTE'` heredoc
   truncated a 184-char token to 13 chars mid-session. Write the token to a local file, `scp` it,
   then `sha256sum` BOTH ends to confirm they match before restart. Also: a later restore step can
   silently overwrite a token you just pushed — re-verify the checksum right before `systemctl restart`.
3. Title/content check through the tunnel, not just status code.

Support files: `templates/cloudflared.service` (systemd unit with file-read token + http2).
