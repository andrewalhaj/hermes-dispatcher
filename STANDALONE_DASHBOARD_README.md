# Standalone DC Dashboard (legacy / offline build)

These three files at the repo root are a **standalone, server-independent** version of the
Hermes dispatcher board, built with the DC framework:

| File | Description |
|---|---|
| `Hermes Task Dispatcher.dc.html` | Open in a browser — no server needed |
| `support.js` | Generated dc-runtime bundle (`dc-runtime/src/*.ts`). Do not edit directly; rebuild with `cd dc-runtime && bun run build` |
| `hermes-board-v2-inline.js` | Auto-generated DC import shim for the single-file standalone bundle |

## Relationship to the React SPA

The FastAPI server (`server.py`) serves **only** `app/dist/` — the React/Vite SPA.
These files are **not served by the server** and have zero references in `server.py` or `routes/`.

They exist as an offline/standalone alternative that can be opened directly in a browser
without the backend running. This is useful for read-only board inspection when the server
is unreachable.

## Status

Confirmed git-tracked, confirmed not served by the live backend. Kept for offline use.
If this build is no longer maintained, open a PR to remove these three files and this README.
