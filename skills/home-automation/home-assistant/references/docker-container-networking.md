# Docker Container vs VPS Host Networking with Tailscale

## Key Finding
The VPS host CAN reach `10.0.0.45` (Shield local IP) when Tailscale subnet routing is enabled. But HA runs in a Docker container (`--network host`), and Docker's network stack does NOT propagate Tailscale subnet routes. From inside the container, `10.0.0.45` is unreachable.

## Working Configuration
- **HA config entry host:** `100.69.145.58` (Tailscale IP, works from container)
- **PORT TEST from container:** `docker exec homeassistant bash -c 'echo >/dev/tcp/100.69.145.58/5555'` → PORT_OPEN
- **PORT TEST from container to local IP:** `docker exec homeassistant bash -c 'echo >/dev/tcp/10.0.0.45/5555'` → PORT_CLOSED

## Verify Before Configuring
Always test connectivity FROM INSIDE the container, not from the VPS host:
```bash
docker exec homeassistant bash -c 'timeout 3 bash -c "echo >/dev/tcp/DEVICE_IP/PORT" 2>&1 && echo PORT_OPEN || echo PORT_CLOSED'
```

## Why `--network host` Doesn't Help
`--network host` gives the container the host's network NAMESPACE, but Tailscale routes are injected at the kernel routing table level and may not be visible inside the container's view of the routing table. The Tailscale TUN device (tailscale0) is shared, but Docker's network isolation can still block subnet-routed traffic.
