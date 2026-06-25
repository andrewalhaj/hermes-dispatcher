# Nvidia Shield ADB Connectivity Debug Trail

## Context
- Shield local IP: `10.0.0.45`
- Shield Tailscale IP: `100.69.145.58`
- HA on backup VPS: `178.156.246.115`
- Both devices on same Tailnet (Tailscale installed on both)

## Problem
HA cannot reach Shield's ADB port despite both devices on Tailscale.

## Debug Steps

### 1. Initial ADB attempt (failed)
```bash
adb connect 100.69.145.58:5555
# Result: timeout (connection refused)
```
ADB network debugging was OFF on Shield. Android TV auto-disables it after timeout.

### 2. User re-enabled network debugging
Shield Developer Options → Network debugging ON → shows `10.0.0.45:5555`

### 3. Second ADB attempt (failed)
```bash
adb connect 100.69.145.58:5555
# Result: timeout
```

### 4. Port scan from VPS (all closed)
```bash
timeout 5 bash -c 'echo >/dev/tcp/100.69.145.58/5555'
# Result: PORT_5555_CLOSED
timeout 5 bash -c 'echo >/dev/tcp/100.69.145.58/5556'
# Result: PORT_5556_CLOSED
timeout 5 bash -c 'echo >/dev/tcp/100.69.145.58/80'
# Result: PORT_80_CLOSED
```

### 5. Tailscale status (shows active)
```bash
tailscale status | grep shield
# 100.69.145.58  shield  alhajandrew91@  android  active; direct [2601:...]:60199, tx 5856 rx 504
```
Device is active but NO ports accessible. Tailscale control plane shows 504 bytes received.

### 6. Ping test (ICMP blocked)
```bash
ping -c 3 -W 2 100.69.145.58
# 100% packet loss
```
ICMP is blocked but Tailscale VPN is active — ICMP is not required for TCP.

## Root Cause
ADB on Android TV/Nvidia Shield binds ONLY to the **local network interface** (`10.0.0.45`), NOT the Tailscale virtual interface (`100.69.145.58`). The Shield has two IPs but ADB only listens on the physical LAN interface. Tailscale shows the device as "active; direct" but cannot reach services bound exclusively to the local interface.

## Solution
**Tailscale subnet routing** — advertise `10.0.0.0/24` from the Shield so the VPS can route to `10.0.0.45` through Tailscale.

## Key Indicators of This Issue
1. `tailscale status` shows device active/direct
2. `nc`/`ping` to Tailscale IP fails or times out
3. Device's Developer Options shows local IP only (e.g., `10.0.0.45:5555`, not `100.x.x.x:5555`)
4. Port scan of Tailscale IP shows ALL ports closed
5. `tailscale status` non-zero `rx` counter but no port connectivity
