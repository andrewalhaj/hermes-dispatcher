# Parallel.ai keyless-default web routing — risk + mitigation

## What it is
Hermes bundles a `web-parallel` plugin (`plugins/web/parallel/provider.py`). With
NO `PARALLEL_API_KEY` and NO explicit `web.backend`, `web_search`/`web_extract`
silently use the free hosted MCP at `https://search.parallel.ai/mcp` — sending your
search queries and extracted page content to a third party with zero opt-in.

It became the keyless default via PR #43798 (commit `e0e2571`), submitted by a
Parallel.ai employee without disclosing the employment relationship (9 of 10 merged
Hermes PRs undisclosed; same pattern across openclaw, opencode, langchain docs,
docker/mcp-registry, etc — 161 PRs / 14+ projects). Surfaced publicly on
r/hermesagent (721 upvotes); NousResearch responded; upstream revert is PR #46350.

## Whether you're exposed
Check the active backend resolution, NOT just whether a key is set:
- Explicit `web.backend` / `web.search_backend` in config.yaml → that wins; Parallel
  never reached. (Resolver returns early at `_get_backend`, "configured in
  _KNOWN_WEB_BACKENDS" branch.)
- Both unset → resolver falls through a candidate list ending in the hardcoded
  keyless default and routes to Parallel.
- Confirm historical exposure in `~/.hermes/logs/agent.log*`: look for
  `Plugin 'web-parallel' registered web provider: parallel`. NOTE a false-friend log
  line: `Processing extracted content with LLM (parallel)` is about CONCURRENT async
  chunk processing, NOT the Parallel.ai provider — verify in `tools/web_tools.py`
  (the literal string is hardcoded at the LLM-postprocess step), don't treat it as
  provider traffic.

## The resolver hole (why disabling the plugin isn't fully durable)
`tools/web_tools.py:_get_backend()` candidate list ends with:
```python
("searxng",  _has_env("SEARXNG_URL")),
("brave-free", _has_env("BRAVE_SEARCH_API_KEY")),
("parallel", True),     # <-- always-available keyless terminal default
("ddgs",     _ddgs_package_importable()),
```
That `("parallel", True)` is INDEPENDENT of the plugin enable/disable flag. So:
- `hermes plugins disable web-parallel` removes the provider *registration* (dispatch
  then fails loudly instead of silently shipping to Parallel) — good defense layer.
- BUT both guards (`web.backend` setting AND `plugins.disabled`) live in config.yaml,
  which `hermes setup` reinstall is known to strip (same failure class as the
  EnvironmentFile / chmod-711 host-migration pitfalls). A reinstall re-exposes you.

## Mitigation (defense-in-depth)
1. Explicit backend (this stack already does this):
   `hermes config set web.search_backend searxng` (+ `web.backend firecrawl`).
2. `hermes plugins disable web-parallel` → persists as
   `plugins.disabled: [web/parallel]` in config.yaml. Rollback: `hermes plugins enable web-parallel`.
3. DURABLE (survives config reset): a watchdog that asserts `web.backend != parallel`
   and the plugin stays disabled, alerting on drift. Matches the "watchdog + golden
   copy, not reliance on config that resets" doctrine. BUILT — `scripts/parallel_watchdog.py`
   + daily cron "Parallel.ai Re-exposure Watchdog" (`no_agent`, silent unless it acts).
   Design (worth copying for any gated-config guard):
   - **Layer 1 (plugin disable) self-heals**: the watchdog re-runs
     `hermes plugins disable web-parallel` itself and alerts that it did. Reversible
     action → safe to automate.
   - **Layer 2 (web.backend config) alert-only**: config.yaml is a GATED write, so the
     watchdog does NOT autonomously edit it — it prints the exact
     `hermes config set web.backend firecrawl` / `... search_backend searxng` re-assert
     commands for the operator. Auto-heal only what's reversible-and-ungated; alert for
     what's gated. This split is the general pattern for self-healing guards on Hermes.
   - Contract: `no_agent=True` cron, empty stdout = silent (no message), stdout = alert,
     exit 0 on clean-or-healed, exit 1 only on real failure (cron surfaces as error).
     Verify a fresh script with `cronjob action=run` then check the run-output dir for
     "silent (empty output)".

## Verify no Parallel in active path
```bash
read_file ~/.hermes/config.yaml   # confirm web.backend/search_backend set; plugins.disabled has web/parallel
env | grep -i parallel            # expect none
grep -i "registered web provider: parallel" ~/.hermes/logs/agent.log*   # historical only
```
