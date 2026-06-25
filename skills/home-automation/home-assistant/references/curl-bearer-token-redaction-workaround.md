# Bearer-token redaction workaround (curl --oauth2-bearer)

## Symptom
When a shell command — or a `.sh` file you `write_file` then `scp` to the VPS — contains
either of these, Hermes' secret-redaction layer rewrites the token region to `***`,
corrupting the command:
- `TOKEN=$(cat /root/ha-fusion/token.txt)` → becomes `TOKEN=*** ...txt)` → `bash: syntax error near unexpected token ')'`
- `printf 'Authorization: Bearer %s' "$TOK"` → the literal `Bearer <token>` header string → `unexpected EOF while looking for matching '`

This is NOT a quoting bug you can escape your way out of — the redaction happens to the
command text itself, including inside files written via the file tools. It bit 4+ times in
one HA-dashboard session before the fix landed.

## Fix — never construct the Authorization header string; use curl's flag
`curl --oauth2-bearer "$TOK"` passes the raw token as an argument and emits the
`Authorization: Bearer` header internally, so there is no `Bearer <token>` literal in your
command for the redactor to mangle. Read the token with `read -r` (not `$(cat ...)`).

```bash
#!/bin/bash
read -r TOK < /root/ha-fusion/token.txt          # NOT TOKEN=$(cat ...)

# GET
curl -s --oauth2-bearer "$TOK" http://localhost:8123/api/

# POST a service call
curl -s -X POST --oauth2-bearer "$TOK" -H "Content-Type: application/json" \
  -d '{"entity_id":"light.living_room_lamp","brightness_pct":45}' \
  http://localhost:8123/api/services/light/turn_on

# template eval
curl -s --oauth2-bearer "$TOK" -X POST -H "Content-Type: application/json" \
  -d '{"template":"{{ states.light | map(attribute=\"entity_id\") | list | join(\", \") }}"}' \
  http://localhost:8123/api/template
```

## Why this matters for HA work
Nearly every HA verification gate (frontend up, entity list, end-to-end light/color test,
dashboard config readback) is a curl against `:8123` with a bearer token. Without this fix
the verification scripts silently fail to even run, and you mistake a redaction error for an
auth/HA problem. Standardize on `read -r TOK < file` + `--oauth2-bearer "$TOK"` for all
HA API checks. (Source: HA Mushroom/Bubble dashboard build session.)
