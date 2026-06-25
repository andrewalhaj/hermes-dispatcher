# Sonos on Cloud-Hosted HA via Tailscale Subnet Router

Session-specific recipe + failure transcript for connecting Sonos speakers to a
Home Assistant instance running on a **cloud VPS** (not on the home LAN).
Builds on SKILL.md Section 5b. Topology: HA in Docker `--network host` on VPS
`178.156.246.115` (tailnet `100.119.118.54`); home LAN `10.0.0.0/24`.

## The hardware chain that actually worked
```
HA container → VPS tailscale0 → Windows laptop (subnet router) → home LAN 10.0.0.x → Sonos
```
- Shield/phone are on the tailnet but CANNOT advertise routes (Android client has
  no `--advertise-routes`) → a Windows laptop was used as the subnet router.

## Step-by-step (this session)

### 1. Diagnose — is a subnet router even up? (read-only, from VPS)
```bash
tailscale status --json | python3 -c "import sys,json; d=json.load(sys.stdin); [print(p.get('HostName'),'Routes:',p.get('PrimaryRoutes')) for p in d.get('Peer',{}).values()]"
```
`Routes: None` on every peer + `ping 10.0.0.45` 100% loss = no bridge yet.

### 2. Bring up the Windows laptop as subnet router (user, elevated PowerShell)
```powershell
# MUST be 'Run as administrator' — non-elevated fails with
#   Set-ItemProperty : Requested registry access is not allowed.
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" -Name "IPEnableRouter" -Value 1
& "C:\Program Files\Tailscale\tailscale.exe" up --advertise-routes=10.0.0.0/24 --unattended
```
**Gotcha hit:** `tailscale up` refused because a non-default flag (exit-node) was
already set:
```
Error: changing settings via 'tailscale up' requires mentioning all non-default flags.
```
Fix = add `--reset` to clear stray flags and set exactly what we want:
```powershell
& "C:\Program Files\Tailscale\tailscale.exe" up --advertise-routes=10.0.0.0/24 --unattended --reset
```

### 3. Approve route + accept it on the VPS
- login.tailscale.com → laptop → Edit route settings → approve `10.0.0.0/24`.
  Confirms when `Routes: ['10.0.0.0/24']` shows in step-1 query.
- **VPS must ACCEPT subnet routes** — Linux Tailscale ignores them by default.
  Symptom: route approved but `ip route get 10.0.0.45` shows `via 172.31.1.1 dev eth0`
  (public gateway), and ping = 100% loss.
  ```bash
  tailscale set --accept-routes=true
  # then: ip route get 10.0.0.45  →  'dev tailscale0'  and ping succeeds
  ```
  `--network host` containers inherit this automatically (no extra step).

### 4. Verify reachability from INSIDE the container (HA image has sh, no bash)
```bash
docker exec homeassistant python3 -c "
import socket
for n,ip in {'Arc':'10.0.0.153','Sub':'10.0.0.43','Era 300':'10.0.0.140','Era':'10.0.0.40'}.items():
    s=socket.socket(); s.settimeout(4)
    print(n, ip, 'OPEN' if s.connect_ex((ip,1400))==0 else 'CLOSED'); s.close()
"
```
All four OPEN on 1400. **This is where it's tempting to declare victory — DON'T.**

### 5. Config (backup first), validate, restart
```bash
docker exec homeassistant cp /config/configuration.yaml /config/configuration.yaml.bak-$(date +%Y%m%d-%H%M%S)
# append sonos: media_player: hosts: [the 4 IPs]
docker exec homeassistant python3 -m homeassistant --script check_config -c /config   # validates clean
docker restart homeassistant
```

## THE FAILURE — bidirectional route required
After restart, despite all four ports OPEN, the integration failed to load:
```
ERROR ... Error setting up entry Sonos for sonos
  File ".../sonos/__init__.py", line 235, in async_subscribe_to_zone_updates
    sub = await soco.zoneGroupTopology.subscribe()
  aiohttp.client_exceptions.ClientResponseError: 412, message='Precondition Failed',
    url='http://10.0.0.40:1400/ZoneGroupTopology/Event'
```
**Root cause:** Sonos UPnP eventing needs the speaker to call BACK into HA. The
subnet route is one-way (VPS→LAN). The Sonos's gateway is the home router, which
has no route to the tailnet `100.64.0.0/10`, so the event callback never reaches
cloud HA → speaker returns 412 → integration aborts → 0 `media_player.*` entities.
(`internal_url`/`external_url` were both `None`, so HA also had no good callback
address to advertise.)

## Resolutions (pick per environment)
- **A — bidirectional route (keep cloud HA):** static route on the home router
  `100.64.0.0/10 → <laptop LAN IP>`. With `IPEnableRouter`/`ip_forward` already on,
  the speaker's callbacks reach HA. Needs router that supports static routes.
  Also set HA `internal_url`/`external_url` to a reachable address.
- **B — run HA on the home LAN:** eliminates the asymmetry; Sonos discovery + eventing
  just work. Architecturally correct for a smart-home controller. The laptop could host it.
- **C — roll back:** restore `configuration.yaml.bak-*` + restart to stop the retry-loop errors.

## Durable lessons
1. A laptop validates the bridge but is a poor permanent router (sleep/lid/roaming kills it).
2. Outbound reachability ≠ working integration for event-driven devices. Verify via
   `docker logs ... | grep -i sonos` + entity presence, never a port probe alone.
3. Connecting to the tailnet ≠ advertising a route ≠ VPS accepting the route — three
   distinct steps, each with its own failure mode (None routes / unapproved / no --accept-routes).
4. Cannot 'take control' of a machine not yet on a reachable network — onboarding the
   user's own laptop is necessarily user-at-keyboard for step 1; Windows stays copy-paste.
