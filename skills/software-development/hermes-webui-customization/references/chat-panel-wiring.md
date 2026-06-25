# Wiring the WebUI Chat panel to the REAL agent

Companion to `standalone-bundle-data-wiring.md`. When the `.standalone.html` design
ships a Chat panel that's a hardcoded `CHAT_AGENTS = [...]` roster (fake workers) and a
`sendChat()` that calls `cannedReply(k)` returning a fixed string per agent, this is how
you make it talk to the actual Hermes agent. Proven 2026-06-19 on the live :8787 WebUI
(`/root/projects/hermes-webui-new/server.py`).

## Architecture: subprocess `hermes chat -Q`, NOT an in-process AIAgent import

In hermes-agent **v0.16** the agent package is `agent/` (the OLD webui's `api/streaming.py`
is v0.15 layout). `import api.streaming` FAILS with `No module named 'api'`. You CAN
`sys.path.insert(0, '/usr/local/lib/hermes-agent'); from run_agent import AIAgent`
(it exposes `session_id`, `prefill_messages`, and a `stream_delta_callback` — the real
streaming hook), but the clean, low-risk path that needs zero import wrangling is to
**shell out**:

```
hermes chat -Q -q "<msg>" --source webui [--resume <sid>] [--profile <p>]
```

- `-Q` (quiet) suppresses the box-drawing TUI and prints only `session_id: <id>` on
  stderr. The agent's reply lands in `state.db` as the latest `role='assistant' active=1`
  row for that session — read it back after the subprocess exits.
- Non-`-Q` / `--cli` wraps the reply in `╭─ ⚕ Hermes ─╮` box-art that's painful to parse.
  Use `-Q` + a state.db read every time.
- `--source webui` tags the session so it's filterable and doesn't pollute Telegram lists.

## THE PITFALL THAT COST A ROUND: do NOT `--resume` the ACTIVE gateway-held session

"Shared with Telegram" tempts you to resume the live Telegram session id
(`SELECT id FROM sessions WHERE source='telegram' AND ended_at IS NULL`). DON'T. A 200+
message active session (a) may be claim-locked by the running gateway, and (b) triggers
a context-compression pass on resume that takes 30–90s → blows the SSE timeout. The tell:
the subprocess prints `↻ Resumed session … (N user messages, 27x total messages)` + the
hook-install banner, then `⚡ Interrupted during API call`, and writes the USER message to
state.db but NO assistant reply. Symptom in the browser: `thinking` event, then silence.

Fresh sessions (`hermes chat -Q -q "say X" --source webui` with no `--resume`) return
correctly in seconds. So: **the webui gets its OWN session (`source=webui`)**, separate
from the Telegram thread. For display continuity, SEED the chat panel from the active
Telegram session's last N user+assistant messages (read-only, for the bubble history) but
do NOT forward that sessionId to the send endpoint — resume only the last *completed*
(`ended_at IS NOT NULL`) webui session, or start fresh. This is a documented
scope-narrowing of "shared": same agent (config/memory/skills/SOUL all load), separate
turn ledger. If true cross-session context is wanted later, pass the Telegram thread as
`prefill_messages` to a fresh AIAgent rather than resuming the locked session.

## The four wiring parts (CHAT_AGENTS lives in template `scripts[-1]`)

1. **Backend `_chat_data_for_ui()`** → `{agents: [...], sessionId: "", thread: [...]}`.
   - `agents` = the IMPORTANT real profiles mapped to the CHAT_AGENTS shape
     (`key/name/role/platform/icon/color/status/running`). NOT every swarm worker —
     here: `default`→"Hermes" (the user's Jarvis), `ha-bot`→"HAJarvis", `executor`→"Executor".
     `running` from `tasks WHERE status='running'` assignees.
   - `thread` = last ~40 user+assistant rows from the active Telegram session. Skip
     assistant rows that are pure tool-dispatch (`tool_calls` set, empty content) and skip
     canned test messages. `LIMIT limit*2` to account for skipped rows, then trim.
   - `sessionId: ""` deliberately (see pitfall).
2. **Inject** `"__RD_CHAT__": _get_chat_data()` into `_build_global_data` with a short
   (~10s) TTL cache; bust it after a send so the next paint shows the new turn.
3. **Patch CHAT_AGENTS + chatThreads** (both in template `scripts[-1]`) to seed from the
   global with the mock as fallback. Both are large multi-line array/object literals — use
   the **find-start + find-`];`/`},`-close + splice** pattern, NOT a full-text `str.replace`
   of the whole mock block. CHAT_AGENTS drives BOTH the chat roster AND the agents sidebar,
   so this one patch satisfies "point the agents sidebar at real profiles" too.
   ```js
   // seed form (mock kept as the else-branch fallback):
   CHAT_AGENTS = (window.__RD_CHAT__ && window.__RD_CHAT__.agents && window.__RD_CHAT__.agents.length
     ? window.__RD_CHAT__.agents
     : [ <original mock array> ]);
   chatThreads: (window.__RD_CHAT__ && window.__RD_CHAT__.thread && window.__RD_CHAT__.thread.length
     ? { hermes: window.__RD_CHAT__.thread }
     : { <original mock object> }),
   ```

   ### PITFALL — UNCLOSED TERNARY `(` → `Unexpected token ':'` (cost a round, 2026-06-19)
   When you wrap an existing JS literal in `(cond ? real : <spliced mock>)`, the spliced
   mock you grabbed via find-start + find-close ENDS with its OWN terminator — `];` for the
   array, `},` for the object — and you appended `js[close:]` after it. So the naive splice
   produces `CHAT_AGENTS = (… : [ … ];` and `chatThreads: (… : { … },` — the opening `(`
   is **never closed**. The bundled minified JS then hits the next token (`chatHistOpen:`)
   inside the unbalanced paren and the DC runtime throws **`Root: Unexpected token ':'`**:
   a red banner top-left, sidebar renders, main panel is BLANK. (Note: that same error
   string can ALSO appear harmlessly as chat-history *text* seeded from a prior session —
   grep the SERVED bytes and confirm it's in the JS class body, not inside a JSON thread
   value, before chasing it.)

   **The fix when splicing the mock as the else-branch:** strip the prefix with a real
   prefix-cut (NOT `str.lstrip("CHAT_AGENTS = ")` — `lstrip` is a CHARACTER SET strip and
   will gnaw real leading chars off the body), then rewrite the trailing terminator to
   CLOSE the paren:
   ```python
   mock = js[start:close]
   mock = mock[len("CHAT_AGENTS = "):] if mock.startswith("CHAT_AGENTS = ") else mock
   s = mock.rstrip("\n")
   if   s.endswith("];"): mock = s[:-1] + ");\n"   # ] ;  →  ] ) ;
   elif s.endswith("]"):  mock = s + ");\n"
   # chatThreads object: "},"  →  "}),"
   s = mock.rstrip("\n")
   if   s.endswith("},"): mock = s[:-1] + "),\n"
   elif s.endswith("}"):  mock = s + "),\n"
   ```
   **Validate offline before the gated restart** — simulate just these two patches against
   `standalone.html` and assert `patched.count("(") - patched.count(")") == 0` for each
   spliced region. Net-zero parens is the cheap proof the ternary is balanced; you don't
   need a full restart to catch this class of break. General rule: any time a string-patch
   wraps an existing literal in `( … )`, the closing `)` must be injected by REWRITING the
   literal's own terminator, never assumed.

   ### PITFALL — TWO ESCAPE-LEVEL BUGS that make the fix LOOK applied but silently no-op (2026-06-19, second pass)
   The same patch hit two MORE escape bugs after the unclosed-ternary fix above. Both are
   insidious because the Python source reads correct and lint=ok, but the LIVE served JS is
   still broken. Net-zero-parens does NOT catch either — only node --check on the DECODED
   component JS does.

   1. rstrip with a DOUBLE-backslash-n argument strips the WRONG characters, so the
      endswith check never fires and no fix is applied. In Python source, a double-backslash
      n is the 2-char string backslash + n; str.rstrip treats its argument as a CHARACTER
      SET, so it strips trailing backslash and n chars — it does NOT strip the actual
      newline (one char, ASCII 10). Result: the stripped mock still ends with the real
      newline, so endswith("},") / endswith("];") returns False, the terminator rewrite is
      skipped, and the ternary stays unclosed. USE rstrip with a single-backslash n (a real
      newline char) — one backslash in Python source.

   2. A replacement terminator written with a DOUBLE-backslash n embeds a LITERAL
      backslash-n into the JS code body, causing a DIFFERENT Unexpected token. The
      replacement strings that close the ternary must use a REAL newline (single backslash
      in Python source). If you write a double backslash, the JS that runs in the browser
      literally contains the two characters backslash-n in code position (not a newline) and
      the parser chokes. The original mock body has REAL newlines (it was read from the
      decoded js), so your injected ternary header/footer must match — real newline, never a
      literal backslash-n. Audit ALL replacement string literals: grep the patch block for
      double-backslash-n and confirm every hit is genuinely a JS string-literal escape (e.g.
      split on newline), not code-body text.

   ### THE DEFINITIVE VERIFY: node --check on the DECODED component JS, not the served HTML
   The served page is JSON-encoded (json.dumps re-escapes everything), so grepping the raw
   served bytes shows DOUBLE-escaped sequences and you will chase ghosts. The only reliable
   check: re-extract the __bundler/template from the served HTML, byte-walk to the JSON
   string, json.loads it, pull scripts[-1], write the decoded JS to a file, and run
   node --check on it. Exit 0 = clean. A non-zero exit prints the EXACT line + token
   (SyntaxError: Unexpected token ':' at the chatHistOpen: line), pointing straight at the
   unclosed/mis-escaped construct. Do this on the live :8787 AND on the offline simulation
   before the gated restart — it catches all three bug classes (unclosed paren, wrong-rstrip
   no-op, literal-backslash-n-in-code) that a parens count or a 200 response happily passes.
4. **Replace `sendChat()`** (template `scripts[-1]`) to `fetch('/api/chat/send')` and stream
   the SSE: `resp.body.getReader()`, split on `\n`, track `event:`/`data:` lines; on `delta`
   append the chunk to a `_streaming` agent bubble (create-or-update the LAST bubble), on
   `done` freeze it (`_streaming:false`, swap in the final text), on `error` show `⚠️ <msg>`.
   Keep `cannedReply()` in place as a dead fallback — don't delete it, just stop calling it.

## Backend `/api/chat/send` = SSE over an asyncio subprocess

```python
@app.post("/api/chat/send")
async def chat_send(request, _=Depends(requires_auth)):
    body = await request.json()
    message = body["message"].strip(); profile_key = body.get("profile","hermes")
    prof = _CHAT_PROFILE_MAP.get(profile_key, _CHAT_PROFILE_MAP["hermes"])
    # resolve session: prefer last COMPLETED webui session, else fresh (NEVER active telegram)
    session_id = body.get("sessionId") or _last_completed_webui_session()  # may be ""
    async def generate():
        yield f"event: thinking\ndata: {json.dumps({'at': int(time.time()*1000)})}\n\n"
        cmd = ["/root/.local/bin/hermes","chat","-Q","-q",message,"--source","webui"]
        if session_id: cmd += ["--resume", session_id]
        cmd += prof["profile_flag"]   # [] for default, ["--profile","ha-bot"] etc.
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), timeout=120)  # NOT the SSE default
        # parse "session_id: <id>" from err/out, then read the reply:
        #   SELECT content FROM messages WHERE session_id=? AND role='assistant' AND active=1
        #   ORDER BY id DESC LIMIT 1
        reply = ... ; _bust_chat_cache()
        for i in range(0, len(reply), 40):           # chunk for a typing feel
            yield f"event: delta\ndata: {json.dumps({'text': reply[i:i+40]})}\n\n"
            await asyncio.sleep(0.03)
        yield f"event: done\ndata: {json.dumps({'text': reply, 'sessionId': new_sid})}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","Connection":"keep-alive"})
```
- The `thinking` event fires IMMEDIATELY so the UI shows the indicator before the slow
  agent turn (15–60s with tools). The **120s `communicate()` timeout** matters — the SSE
  default is far too short for a real turn.
- `_CHAT_PROFILE_MAP[key]["profile_flag"]` is `[]` for the default profile (no `--profile`)
  and `["--profile","<name>"]` for the others.

## Verify on the parallel :8788 instance before the gated cutover

A real `done` event with NON-EMPTY `text` from the live agent is the proof — not a 200.
```
curl -s -N -b cookies.txt -X POST :8788/api/chat/send -H 'Content-Type: application/json' \
  -d '{"message":"Reply with exactly three words: hermes chat live","profile":"hermes"}'
# expect: event: thinking → event: delta {"text":"..."} → event: done {"text":"Hermes chat live.", "sessionId":"..."}
```
If you get `thinking` then nothing, you almost certainly resumed a locked/large session —
re-check the session-resolution branch (pitfall above). `/api/chat` (GET) should return the
3 real agent names + a non-empty `thread` + `sessionId:""`.
