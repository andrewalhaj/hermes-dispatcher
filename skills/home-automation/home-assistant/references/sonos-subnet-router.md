# Sonos (and non-Tailscale appliances) on cloud-hosted HA

Session-derived detail for bridging cloud HA (VPS 178.156.246.115) to LAN-only
appliances that cannot run Tailscale themselves. See SKILL.md Section 5b for the
canonical workflow; this file holds the session specifics and reasoning.

## The architectural gate

HA runs on a cloud VPS, not at home. The Shield works because it runs Tailscale
and has its own `100.x` address. **Sonos speakers are sealed appliances — no
Tailscale.** So cloud HA can only reach them if traffic is *routed* into the home
LAN by a subnet router living on that LAN.

Live diagnosis from this session showed the gate clearly:

```
$ tailscale status --json | ... PrimaryRoutes ...
DESKTOP-L8TL5RN  Routes: None   # Windows laptop — connected but NOT advertising
Andrew's S24     Routes: None   # phone — Android, CAN'T advertise
SHIELD           Routes: None   # TV — Android, CAN'T advertise

$ ping -c2 -W2 10.0.0.45
2 packets transmitted, 0 received, 100% packet loss
```

`Routes: None` on every peer + 100% loss to a LAN IP = no bridge. Until a
desktop-OS subnet router advertises the home subnet and that route is approved,
NOTHING in HA can be configured. Surface this first, every time.

## Why the TV / phone can't be the router

The Android Tailscale client has no `--advertise-routes`. It routes its *own*
traffic (which is why ADB-to-Shield works) but cannot relay to *other* LAN
devices. This is a client capability limit, not a config toggle — don't waste a
round trip proposing it. Only Linux / macOS / Windows clients advertise routes.

## Windows subnet router (this session's laptop: DESKTOP-L8TL5RN, 100.112.89.111)

Windows blocks IP forwarding by default; flipping `IPEnableRouter` + a route
advertise turns the box into a router. PowerShell **as Administrator**:

```powershell
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" -Name "IPEnableRouter" -Value 1
& "C:\Program Files\Tailscale\tailscale.exe" up --advertise-routes=10.0.0.0/24 --unattended
```

Then approve at login.tailscale.com → DESKTOP-L8TL5RN → Edit route settings →
check `10.0.0.0/24`. Re-check from VPS: the peer's `PrimaryRoutes` flips from
`None` to `10.0.0.0/24` and `ping 10.0.0.x` starts succeeding.

No clean SSH-in path on Windows, so the agent verifies from the VPS side and
hands the user copy-paste. (Linux/macOS routers are SSH-able over the tailnet
afterward — prefer them when the user has a choice.)

## Container-side verification (the real test)

HA is `--network host` but Docker still doesn't inherit Tailscale subnet routes
the same way the host does. Always test from INSIDE the container before adding
the integration. The HA image ships `sh`, not `bash` — use `sh`:

```bash
docker exec homeassistant sh -c 'timeout 3 sh -c "echo > /dev/tcp/10.0.0.<ip>/1400" && echo OPEN || echo CLOSED'
```

(During the Shield work, the analogous probe failed with
`can't create /dev/tcp/...: nonexistent directory` because it was run under a
shell without /dev/tcp — confirm the probe shell supports it.)

## Adding Sonos

Multicast/SSDP discovery does NOT cross Tailscale — unicast only. Configure each
speaker by explicit IP in `configuration.yaml`:

```yaml
sonos:
  media_player:
    hosts:
      - 10.0.0.x
      - 10.0.0.y
```

Sonos control port = **1400**. Speaker IPs: Sonos app → Settings → System →
About My System. Restart HA, confirm `media_player.*` entities appear.

## Permanence

A laptop validates the design but is a bad permanent router: sleep / lid-close /
leaving the home network kills the bridge and drops every appliance behind it.
For a stable deployment recommend an always-on Pi / mini-PC / NAS, or a
Tailscale-capable router (GL.iNet, OPNsense, some Ubiquiti / OpenWrt).

## Rollback

Fully reversible: `tailscale down` on the router (or un-approve the route)
removes the bridge; delete the `sonos:` block + restart HA removes the
integration. No HA data touched.
