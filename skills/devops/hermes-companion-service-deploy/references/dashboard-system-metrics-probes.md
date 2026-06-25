# Dashboard System Monitor — live CPU/GPU/VRAM/network probes across heterogeneous hosts

How to source live system metrics for a dashboard backend (`routes/system.py` style)
when the hosts are a mix of **Linux + Intel iGPU**, **Apple Silicon (macOS)**, and
(potentially) **nvidia**. Verified end-to-end 2026-06-23 wiring the hermes-dispatcher
dashboard System Monitor tile (Mac Mini = Linux/Intel UHD 630 server, Mac Studio =
Apple Silicon remote probed over Tailscale SSH).

The hard part is NOT CPU/mem (psutil is uniform). It's GPU/VRAM, which has a totally
different interface per platform, and **`nvidia-smi` exists on NONE of these boxes** —
so the naive `nvidia-smi`-only probe returns `null` forever and the tile shows N/A.

## The platform dispatch (probe `_gpu_stats()` should try in order)

```python
def _gpu_stats() -> dict:
    # 1. nvidia (real discrete GPU)
    if shutil.which("nvidia-smi"):
        # nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits
        ...
    # 2. Apple Silicon (macOS) — ioreg, no sudo
    #    (only reached when running ON the mac; for a REMOTE mac use the SSH probe below)
    # 3. Linux Intel iGPU — /proc fdinfo + i915 sysfs
    if Path("/sys/kernel/debug/dri/0000:00:02.0/i915_gem_objects").exists():
        return {"gpu_pct": _intel_gpu_pct(), "vram_pct": _intel_vram_pct()}
    # 4. nothing → degrade gracefully
    return {"gpu_pct": None, "vram_pct": None}
```

### Apple Silicon GPU/VRAM — `ioreg` (no sudo, no install)
`nvidia-smi` absent; `powermetrics` needs sudo (interactive). The keyless path is `ioreg`:
```bash
ioreg -l -c IOAccelerator        # or: ioreg -r -d 1 -k "PerformanceStatistics"
```
Parse from stdout:
- **GPU%**  → `"Device Utilization %" = 63`
- **VRAM bytes in use** → `"In use system memory" = 295780352`

Unified memory ⇒ no separate VRAM pool; compute `vram_pct = in_use_bytes / total_ram * 100`
(total from `psutil.virtual_memory().total`). Regex:
```python
m_util = re.search(r'"Device Utilization %"\s*=\s*(\d+)', ioreg_stdout)
m_mem  = re.search(r'"In use system memory"\s*=\s*(\d+)', ioreg_stdout)
```

### Linux Intel iGPU (UHD 630 etc.) — `/proc/*/fdinfo` + `i915_gem_objects`
No `nvidia-smi`, no `intel_gpu_top` (needs install + root), **no `gpu_busy_percent` sysfs**
on i915 (that's an amdgpu/xe file). The working keyless approach:

- **GPU%** = delta of cumulative `drm-engine-render` nanoseconds across ALL `/proc/*/fdinfo/*`,
  sampled twice ~250ms apart, over elapsed wall-ns:
  ```python
  def _read_render_ns():
      total = 0
      for path in glob.glob('/proc/*/fdinfo/*'):
          try:
              for m in re.finditer(r'drm-engine-render:\s+(\d+) ns', open(path).read()):
                  total += int(m.group(1))
          except Exception:
              pass
      return total
  ns0=_read_render_ns(); t0=time.monotonic(); time.sleep(0.25)
  ns1=_read_render_ns(); t1=time.monotonic()
  gpu_pct = round((ns1-ns0)/((t1-t0)*1e9)*100, 1)
  ```
  (Requires kernel ≥5.19 fdinfo DRM stats — present on the t2-noble Mini.)
- **VRAM%** = i915 "stolen-system" bytes / total RAM:
  ```python
  txt = open('/sys/kernel/debug/dri/0000:00:02.0/i915_gem_objects').read()
  stolen = int(re.search(r'stolen.*?total:(0x[0-9a-f]+)', txt).group(1), 16)
  vram_pct = round(stolen / psutil.virtual_memory().total * 100, 1)
  ```
  The PCI path `0000:00:02.0` is the integrated GPU's BDF — confirm with
  `ls /sys/kernel/debug/dri/`. Intel iGPU GPU% is legitimately near-zero at idle
  (no compositing/video) — that's accurate, not a bug; say so to the user.

The Intel GPU% probe sleeps 250ms — fine when the route already runs in
`run_in_executor`; do NOT nest another executor inside it.

## Remote-host probe (Mac Studio over Tailscale SSH) — two recurring traps

The backend runs a tiny Python probe on the remote via `ssh ... python3 -` and parses the
last stdout line as JSON. Failure → return an `error="unreachable"` snapshot (all metrics
None) rather than 500ing.

1. **`run_in_executor`/uvicorn subprocess can't find the SSH key from `~/.ssh` discovery.**
   SSH works fine from an interactive terminal but the daemon's subprocess env differs →
   `unreachable`. **Always pass the key explicitly**: add `-i /root/.ssh/id_ed25519` to the
   `ssh` argv alongside `-o StrictHostKeyChecking=no -o ConnectTimeout=3 -o BatchMode=yes`.
   Symptom that pins it: `ssh ... localadmin@host` returns 0 in a shell, but the dashboard
   tile says unreachable.

2. **The remote probe's deps must exist on the REMOTE.** A probe that `import psutil`
   fails with `ModuleNotFoundError` on a fresh Mac → SSH exits non-zero → `unreachable`.
   Either `pip3 install psutil` on the remote (gated: remote state change) OR write the
   probe in pure stdlib. psutil is the cleaner path once installed (it's read-only).
   Verify the WHOLE probe end-to-end after install, not just that SSH connects:
   ```python
   # on the dashboard host:
   from routes.system import _fetch_studio_metrics; print(_fetch_studio_metrics())
   ```

## Auth-gate cookie trap (why the tile is empty behind a login)

The dashboard auth middleware (`auth_gate` in `server.py`) requires an `hd_session` cookie;
`/api/system` is NOT in `_AUTH_EXEMPT`. Two failure modes seen this session:

- **Frontend fetch omits credentials.** `fetch('/api/system')` does NOT send cookies by
  default in this setup → 401 → empty tile. Fix: `fetch(url, { credentials: 'include' })`
  in the polling hook (`useSystemStats.ts`). Verify the built bundle actually contains it:
  `grep -o "credentials.*include" app/dist/assets/index-*.js`.
- **Cookie is host-scoped, breaks across domains.** The login cookie is set with
  `samesite="strict", path="/"` and NO explicit `domain`, so it's bound to the host you
  logged in on. Logging in at `http://<tailnet-ip>:8787` then visiting via
  `https://<public-domain>` (Cloudflare tunnel) sends NO cookie → 401 → empty. This is
  NOT a code bug — log in directly at the domain you intend to use. (If you genuinely need
  one session across both, that's a `domain=` cookie change, a deliberate decision.)

## Verify GPU/VRAM live before claiming fixed
Call the route function directly on the host and read the actual fields — server-side
200/clean-logs is a false positive for a tile that's still N/A in the DOM:
```python
import asyncio, json
from routes.system import get_system
print(json.dumps(asyncio.run(get_system('mini')), indent=2))   # gpu_pct / vram_pct non-null?
```
Then restart the dashboard service (route changes don't take effect until uvicorn re-imports
the module — see the `dashboard-restart-via-cron.md` reference for the gateway-self-protection
workaround) and confirm in a real browser session with auth.
