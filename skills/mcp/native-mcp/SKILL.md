---
name: native-mcp
description: "MCP client: connect servers, register tools (stdio/HTTP)."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [MCP, Tools, Integrations]
    related_skills: [mcporter]
---

# Native MCP Client

Hermes Agent has a built-in MCP client that connects to MCP servers at startup, discovers their tools, and makes them available as first-class tools the agent can call directly. No bridge CLI needed -- tools from MCP servers appear alongside built-in tools like `terminal`, `read_file`, etc.

## When to Use

Use this whenever you want to:
- Connect to MCP servers and use their tools from within Hermes Agent
- Add external capabilities (filesystem access, GitHub, databases, APIs) via MCP
- Run local stdio-based MCP servers (npx, uvx, or any command)
- Connect to remote HTTP/StreamableHTTP MCP servers
- Have MCP tools auto-discovered and available in every conversation

For ad-hoc, one-off MCP tool calls from the terminal without configuring anything, see the `mcporter` skill instead.

## Prerequisites

- **mcp Python package** -- optional dependency; install with `pip install mcp`. If not installed, MCP support is silently disabled.
- **Node.js** -- required for `npx`-based MCP servers (most community servers)
- **uv** -- required for `uvx`-based MCP servers (Python-based servers)

Install the MCP SDK:

```bash
pip install mcp
# or, if using uv:
uv pip install mcp
```

## Adding a server: prefer the CLI, drive its prompts

`hermes mcp add <name> --url <endpoint> [--auth header|oauth]` is the clean path — it connects, lists tools, and writes the `mcp_servers` block for you (no hand-editing YAML, no malformed-config risk). Subcommands: `add`, `remove/rm`, `list/ls`, `test <name>`, `configure`, `login`.

**PITFALL — `hermes mcp add` is INTERACTIVE and will hang a normal foreground call.** It prompts twice: (1) "Does this server require authentication? [Y/n]" then a token entry, and (2) "Enable all N tools? [Y/n/select]". A plain `terminal()` call (even with `pty=true`) does NOT relay answers — the prompts sit unanswered and the command **cancels itself, writing nothing** (clean: no partial state, but also no server added). Verify with `hermes mcp list` → "No MCP servers configured."

**Working pattern — background PTY process + submit answers per prompt:**
1. `terminal(background=true, pty=true, command='cd /root && hermes mcp add <name> --url "<url>"')` → get `session_id`.
2. `process(action=poll, session_id=...)` until you see the auth prompt.
3. `process(action=submit, data="n", session_id=...)` — answer **n** if the token is already embedded in the URL (e.g. Zapier `?token=...`); answer **Y** + submit the token if auth is a separate header.
4. `process(action=poll)` until "Enable all N tools?" → `process(action=submit, data="Y")`.
5. `process(action=wait, timeout=30)` → expect `✓ Saved '<name>' to ~/.hermes/config.yaml (N/N tools enabled)`.
6. Verify: `hermes mcp list` (status ✓ enabled) and `hermes mcp test <name>` (re-lists tools live).

**`config.yaml` is gated** — back it up (`.bak-<ts>`) before the add even when using the CLI, since the write lands there.

**Tools register only after a gateway restart.** The CLI prints "Start a new session to use these tools." MCP discovery runs at agent startup, so `mcp_<server>_*` tools are NOT available in the current live session until `systemctl --user restart hermes-gateway` (itself gated — ~5-10s unresponsive, session resumes from DB). Don't claim the tools are usable in-chat before the restart.

For Zapier MCP specifically (meta-tool architecture, app OAuth on Zapier's side, what each tool does), see `references/zapier-mcp.md`.

For Figma MCP (OAuth-not-PAT trap, correct `/mcp` StreamableHTTP endpoint, approved-client allowlist, why it can't run on headless Hermes, Claude Code plugin install), see `references/figma-mcp.md`.

For **Playwright MCP remote setup** (SSH tunnel pattern when the browser runs on a different machine than Hermes — Playwright only accepts localhost connections even with `--host 0.0.0.0`, so you tunnel through SSH to make the connection appear local), see `references/playwright-mcp-remote.md`.

## Remote MCP auth: OAuth vs token — check BEFORE wiring

Not every "remote MCP" takes a header token. Two distinct auth models, and guessing wrong wastes a gated config write:

- **Token/header auth** (Zapier embedded-URL token, many community servers): a `Bearer`/header credential authenticates the session. Wire it via `headers:` in `config.yaml` or `-H` in `claude mcp add`. Probe works with a plain curl `initialize` POST.
- **OAuth auth** (Figma, Google Drive, Sentry, most first-party SaaS MCPs): requires a browser consent flow. **A REST-API personal access token is NOT an OAuth credential** — pasting it as a Bearer header returns `Unauthorized`. These servers also frequently restrict to an **approved-client allowlist** (only VS Code/Cursor/Claude Code/etc. may connect).

Consequence for headless Hermes: **OAuth-only MCP servers cannot be wired into Hermes** — no browser to complete consent, and Hermes is usually not on the allowlist. Don't leave a dead `enabled: true` entry; explain both blockers. Verify the auth model with a curl `initialize` probe (success = valid MCP response; `Unauthorized` with a token-you-think-is-valid = it's OAuth-gated) before touching gated config.

## Wiring an MCP server into BOTH Hermes and Claude Code

When the user wants a server available to Hermes *and* to Claude Code coding sessions, they are two independent registrations:

- **Claude Code** (no gated write — `claude mcp add` is safe): `claude mcp add --scope user --transport <stdio|http|sse> <name> <url-or-cmd> [-H "Authorization: Bearer *** ...]`. Use `--scope user` so it persists across all projects. Config lands in `~/.claude.json`; verify with `claude mcp list` (shows `✔ Connected` / `✘ Failed to connect`).
- **Hermes** (GATED — `config.yaml` + `.env`): store the secret in `~/.hermes/.env` as `FOO_API_KEY=...`, reference it in `config.yaml` as `headers: { Authorization: "Bearer ${FOO_API_KEY}" }`, then restart the gateway. The `patch` tool REFUSES to edit `config.yaml` ("Refusing to write to Hermes config file") — edit it with a `python3 -c "import yaml; ..."` round-trip after arming the write gate (`python3 ~/.hermes/patches/write_gate.py arm "<note>" --ttl 600`) and backing up.
- **Transport mismatch is a common first-try failure.** Confirm the server's real endpoint + transport before writing both configs — e.g. Figma is `/mcp` StreamableHTTP, not `/v1/sse`. Fixing it means redoing both registrations.

For the **Docker MCP Toolkit** (`docker mcp` CLI — Desktop-only plugin with catalog/profiles/keychain-secrets/gateway), including the headless-keychain unlock fix (`gnome-keyring-daemon` + gdbus CreateCollection) AND why it does NOT persist across a daemon restart on a headless box (→ use the **PAT-file + wrapper-script** fallback instead), the secret-key-name-must-match-profile pitfall, the "inline-written secret gets redacted to `***` by the security scanner" pitfall, and the "pasted PAT is auto-revoked → curl-check first" lesson, see `references/docker-mcp-toolkit.md`. Note: this is distinct from the `docker exec -i` single-server stdio bridge above — reach for the Toolkit only when the user explicitly wants it (it requires Docker Desktop, not plain Engine).

## Quick Start

Add MCP servers to `~/.hermes/config.yaml` under the `mcp_servers` key:

```yaml
mcp_servers:
  time:
    command: "uvx"
    args: ["mcp-server-time"]
```

Restart Hermes Agent. On startup it will:
1. Connect to the server
2. Discover available tools
3. Register them with the prefix `mcp_time_*`
4. Inject them into all platform toolsets

You can then use the tools naturally -- just ask the agent to get the current time.

## Configuration Reference

Each entry under `mcp_servers` is a server name mapped to its config. There are two transport types: **stdio** (command-based) and **HTTP** (url-based).

### Stdio Transport (command + args)

```yaml
mcp_servers:
  server_name:
    command: "npx"             # (required) executable to run
    args: ["-y", "pkg-name"]   # (optional) command arguments, default: []
    env:                       # (optional) environment variables for the subprocess
      SOME_API_KEY: "value"
    timeout: 120               # (optional) per-tool-call timeout in seconds, default: 120
    connect_timeout: 60        # (optional) initial connection timeout in seconds, default: 60
```

### HTTP Transport (url)

```yaml
mcp_servers:
  server_name:
    url: "https://my-server.example.com/mcp"   # (required) server URL
    headers:                                     # (optional) HTTP headers
      Authorization: "Bearer sk-..."
    timeout: 180               # (optional) per-tool-call timeout in seconds, default: 120
    connect_timeout: 60        # (optional) initial connection timeout in seconds, default: 60
```

### All Config Options

| Option            | Type   | Default | Description                                       |
|-------------------|--------|---------|---------------------------------------------------|
| `command`         | string | --      | Executable to run (stdio transport, required)     |
| `args`            | list   | `[]`    | Arguments passed to the command                   |
| `env`             | dict   | `{}`    | Extra environment variables for the subprocess    |
| `url`             | string | --      | Server URL (HTTP transport, required)             |
| `headers`         | dict   | `{}`    | HTTP headers sent with every request              |
| `timeout`         | int    | `120`   | Per-tool-call timeout in seconds                  |
| `connect_timeout` | int    | `60`    | Timeout for initial connection and discovery      |

Note: A server config must have either `command` (stdio) or `url` (HTTP), not both.

## How It Works

### Startup Discovery

When Hermes Agent starts, `discover_mcp_tools()` is called during tool initialization:

1. Reads `mcp_servers` from `~/.hermes/config.yaml`
2. For each server, spawns a connection in a dedicated background event loop
3. Initializes the MCP session and calls `list_tools()` to discover available tools
4. Registers each tool in the Hermes tool registry

### Tool Naming Convention

MCP tools are registered with the naming pattern:

```
mcp_{server_name}_{tool_name}
```

Hyphens and dots in names are replaced with underscores for LLM API compatibility.

Examples:
- Server `filesystem`, tool `read_file` → `mcp_filesystem_read_file`
- Server `github`, tool `list-issues` → `mcp_github_list_issues`
- Server `my-api`, tool `fetch.data` → `mcp_my_api_fetch_data`

### Auto-Injection

After discovery, MCP tools are automatically injected into all `hermes-*` platform toolsets (CLI, Discord, Telegram, etc.). This means MCP tools are available in every conversation without any additional configuration.

### Connection Lifecycle

- Each server runs as a long-lived asyncio Task in a background daemon thread
- Connections persist for the lifetime of the agent process
- If a connection drops, automatic reconnection with exponential backoff kicks in (up to 5 retries, max 60s backoff)
- On agent shutdown, all connections are gracefully closed

### Idempotency

`discover_mcp_tools()` is idempotent -- calling it multiple times only connects to servers that aren't already connected. Failed servers are retried on subsequent calls.

## Transport Types

### Stdio Transport

The most common transport. Hermes launches the MCP server as a subprocess and communicates over stdin/stdout.

```yaml
mcp_servers:
  filesystem:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/projects"]
```

The subprocess inherits a **filtered** environment (see Security section below) plus any variables you specify in `env`.

#### Containerized MCP server (CLI lives inside Docker)

When the MCP server binary ships *inside a Docker container* and is NOT installed on the host (no native install, host lacks the runtime), bridge it with `docker exec -i` as the stdio command. Hermes spawns the in-container CLI over a docker pipe per tool call — no host install, no Node/runtime on host, pure config.

```yaml
mcp_servers:
  open-design:
    command: docker
    args: [exec, -i, <container_name>, node, /path/in/container/cli.js, mcp, --daemon-url, http://127.0.0.1:PORT]
    enabled: true
```

**Verify the stdio handshake BEFORE writing config** — pipe an `initialize` request through `docker exec -i` and confirm a valid MCP response. Don't wire a server you haven't proven answers. Full pattern, the verification probe, the OAuth-bypass auth-gap lesson (a containerized agent runtime that reports every agent `available:false` because no agent CLI is installed inside it), and the **hardened-container execution path** (read-only rootfs, `noexec /tmp`, install into the exec-capable volume, `docker cp` can't write tmpfs → pipe via `docker exec` stdin, native-binary location, real-round-trip auth proof): see `references/containerized-mcp-server.md`.

### HTTP / StreamableHTTP Transport

For remote or shared MCP servers. Requires the `mcp` package to include HTTP client support (`mcp.client.streamable_http`).

```yaml
mcp_servers:
  remote_api:
    url: "https://mcp.example.com/mcp"
    headers:
      Authorization: "Bearer sk-..."
```

If HTTP support is not available in your installed `mcp` version, the server will fail with an ImportError and other servers will continue normally.

## Security

### Environment Variable Filtering

For stdio servers, Hermes does NOT pass your full shell environment to MCP subprocesses. Only safe baseline variables are inherited:

- `PATH`, `HOME`, `USER`, `LANG`, `LC_ALL`, `TERM`, `SHELL`, `TMPDIR`
- Any `XDG_*` variables

All other environment variables (API keys, tokens, secrets) are excluded unless you explicitly add them via the `env` config key. This prevents accidental credential leakage to untrusted MCP servers.

```yaml
mcp_servers:
  github:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      # Only this token is passed to the subprocess
      GITHUB_PERSONAL_ACCESS_TOKEN: "ghp_..."
```

### Credential Stripping in Error Messages

If an MCP tool call fails, any credential-like patterns in the error message are automatically redacted before being shown to the LLM. This covers:

- GitHub PATs (`ghp_...`)
- OpenAI-style keys (`sk-...`)
- Bearer tokens
- Generic `token=`, `key=`, `API_KEY=`, `password=`, `secret=` patterns

## Troubleshooting

### "MCP SDK not available -- skipping MCP tool discovery"

The `mcp` Python package is not installed. Install it:

```bash
pip install mcp
```

### "No MCP servers configured"

No `mcp_servers` key in `~/.hermes/config.yaml`, or it's empty. Add at least one server.

### "Failed to connect to MCP server 'X'"

Common causes:
- **Command not found**: The `command` binary isn't on PATH. Ensure `npx`, `uvx`, or the relevant command is installed.
- **Package not found**: For npx servers, the npm package may not exist or may need `-y` in args to auto-install.
- **Timeout**: The server took too long to start. Increase `connect_timeout`.
- **Port conflict**: For HTTP servers, the URL may be unreachable.

### "MCP server 'X' requires HTTP transport but mcp.client.streamable_http is not available"

Your `mcp` package version doesn't include HTTP client support. Upgrade:

```bash
pip install --upgrade mcp
```

### Tools not appearing

- Check that the server is listed under `mcp_servers` (not `mcp` or `servers`)
- Ensure the YAML indentation is correct
- Look at Hermes Agent startup logs for connection messages
- Tool names are prefixed with `mcp_{server}_{tool}` -- look for that pattern

### Connection keeps dropping

The client retries up to 5 times with exponential backoff (1s, 2s, 4s, 8s, 16s, capped at 60s). If the server is fundamentally unreachable, it gives up after 5 attempts. Check the server process and network connectivity.

## Examples

### Time Server (uvx)

```yaml
mcp_servers:
  time:
    command: "uvx"
    args: ["mcp-server-time"]
```

Registers tools like `mcp_time_get_current_time`.

### Filesystem Server (npx)

```yaml
mcp_servers:
  filesystem:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/documents"]
    timeout: 30
```

Registers tools like `mcp_filesystem_read_file`, `mcp_filesystem_write_file`, `mcp_filesystem_list_directory`.

### GitHub Server with Authentication

```yaml
mcp_servers:
  github:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "ghp_xxxxxxxxxxxxxxxxxxxx"
    timeout: 60
```

Registers tools like `mcp_github_list_issues`, `mcp_github_create_pull_request`, etc.

### Remote HTTP Server

```yaml
mcp_servers:
  company_api:
    url: "https://mcp.mycompany.com/v1/mcp"
    headers:
      Authorization: "Bearer sk-xxxxxxxxxxxxxxxxxxxx"
      X-Team-Id: "engineering"
    timeout: 180
    connect_timeout: 30
```

### Multiple Servers

```yaml
mcp_servers:
  time:
    command: "uvx"
    args: ["mcp-server-time"]

  filesystem:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]

  github:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "ghp_xxxxxxxxxxxxxxxxxxxx"

  company_api:
    url: "https://mcp.internal.company.com/mcp"
    headers:
      Authorization: "Bearer sk-xxxxxxxxxxxxxxxxxxxx"
    timeout: 300
```

All tools from all servers are registered and available simultaneously. Each server's tools are prefixed with its name to avoid collisions.

## Sampling (Server-Initiated LLM Requests)

Hermes supports MCP's `sampling/createMessage` capability — MCP servers can request LLM completions through the agent during tool execution. This enables agent-in-the-loop workflows (data analysis, content generation, decision-making).

Sampling is **enabled by default**. Configure per server:

```yaml
mcp_servers:
  my_server:
    command: "npx"
    args: ["-y", "my-mcp-server"]
    sampling:
      enabled: true           # default: true
      model: "gemini-3-flash" # model override (optional)
      max_tokens_cap: 4096    # max tokens per request
      timeout: 30             # LLM call timeout (seconds)
      max_rpm: 10             # max requests per minute
      allowed_models: []      # model whitelist (empty = all)
      max_tool_rounds: 5      # tool loop limit (0 = disable)
      log_level: "info"       # audit verbosity
```

Servers can also include `tools` in sampling requests for multi-turn tool-augmented workflows. The `max_tool_rounds` config prevents infinite tool loops. Per-server audit metrics (requests, errors, tokens, tool use count) are tracked via `get_mcp_status()`.

Disable sampling for untrusted servers with `sampling: { enabled: false }`.

## Notes

- MCP tools are called synchronously from the agent's perspective but run asynchronously on a dedicated background event loop
- Tool results are returned as JSON with either `{"result": "..."}` or `{"error": "..."}`
- The native MCP client is independent of `mcporter` -- you can use both simultaneously
- Server connections are persistent and shared across all conversations in the same agent process
- Adding or removing servers requires restarting the agent (no hot-reload currently)
