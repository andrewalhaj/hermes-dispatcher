# Honcho store-level deletion: what the v3 REST API actually allows

When premise-negating conclusions + card rewrite aren't enough and the user wants the
poison facts *deleted at the source*, the only remaining lever is the hosted Honcho v3
REST API. This note records what that API exposes (verified against api.honcho.dev,
OpenAPI 3.1.0 / API version 3.0.9) so a future session doesn't re-derive it.

## Discovery (read-only)

- API base is **`https://api.honcho.dev/v3`** — NOT `/v1`. Old bridge scripts may hardcode
  `/v1`; that path 404s for the spec. The honcho-bridge.sh in this repo used `/v1` and was stale.
- Auth: `Authorization: Bearer $HONCHO_API_KEY` (read from `~/.hermes/.env`, line starting
  `HONCHO_API_KEY=`). Even `/openapi.json` returns 401 without it; with the bearer token,
  `GET https://api.honcho.dev/openapi.json` returns the full spec (~84KB).
- Workspace is `hermes`, user peer is `root` (per honcho-bridge.sh constants).
- List sessions (read-only query): `POST /v3/workspaces/hermes/sessions/list` body `{}`.
- List a session's messages: `POST /v3/workspaces/hermes/sessions/{session_id}/messages/list?page=N&size=100`.

## What the API CAN delete

| Route | Deletes |
|---|---|
| `DELETE /v3/workspaces/{ws}/sessions/{session_id}` | a whole session (all its messages) |
| `DELETE /v3/workspaces/{ws}/conclusions/{conclusion_id}` | one conclusion (same as `honcho_conclude delete_id`) |
| `DELETE /v3/workspaces/{ws}` | the entire workspace (nuclear — never for cleanup) |

## What the API CANNOT delete (the crux)

- **No delete-message.** Messages are `GET` / `PUT` only (editable, not individually removable).
- **No delete-observation.** The deductive/inductive observations that the dialectic
  re-derives the poison facts from are **not stored objects with delete routes** — they are
  computed. Confirms the SKILL.md claim: you cannot hard-delete derived observations via API.

So "delete at the source" collapses to exactly one blunt instrument: **delete whole sessions**.

## The keyword-scan trap (why bulk session deletion is the WRONG fix)

Tempting plan: scan every session's messages for poison terms (e.g. `3ds max`, `sanja`,
`railway`, `lancedb`), then delete the sessions that hit. This FAILS for two reasons, both
observed this session (47 sessions, 37 contained ≥1 poison keyword):

1. **The correction conversations score HIGHEST.** The sessions where you *debugged and
   negated* the dummy data are dense with the very terms you're scanning for — they top the
   hit ranking as false positives. Deleting by keyword preferentially destroys the sessions
   that hold the *fixes*, making the problem worse.
2. **Contamination is interleaved, not isolated.** Poison facts are spread across ~80% of
   sessions, threaded message-by-message alongside legitimate work history. With no
   delete-message route, you cannot excise the bad turns without deleting the whole session
   (and its real history with it).

**Verdict:** session deletion is *available* but the *wrong tool* — high collateral, uncertain
payoff (already-derived observations/representation may persist even after source messages go).
Stay with the intended mechanism: **premise-negating conclusions** (correction, not deletion),
let the representation converge on the dialectic cadence, and verify next session. If the
injected block must stop carrying the dirty derivation *immediately*, the surgical config lever
is narrowing injection to **card-only** (`recallMode: context` won't do it; this is the
`injectionFrequency` / context-composition path) rather than deleting history.
