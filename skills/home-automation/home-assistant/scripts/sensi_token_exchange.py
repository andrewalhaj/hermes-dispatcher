#!/usr/bin/env python3
"""Exchange Sensi refresh token for access token and write HA storage file.

Usage: python3 sensi_token_exchange.py <refresh_token> [--output /path/to/.storage/sensi]

The refresh_token is the JWT from manager.sensicomfort.com DevTools.
Writes the HA storage.Store format to stdout or the specified output file.
"""

import json, sys, time, urllib.request, urllib.parse

CLIENT_ID = "fleet"
CLIENT_SECRET = "JLFjJmketRhj>M9uoDhusYKyi?zUyNqhGB)H2XiwLEF#KcGKrRD2JZsDQ7ufNven"
OAUTH_URL = "https://oauth.sensiapi.io/token"

def exchange(refresh_token: str) -> dict:
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }).encode()
    req = urllib.request.Request(OAUTH_URL, data=data)
    req.add_header("Content-Type", "application/x-www-form-urlencoded; charset=utf-8")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def build_store(result: dict) -> dict:
    return {
        "version": 1,
        "minor_version": 1,
        "key": "sensi",
        "data": {
            "access_token": result["access_token"],
            "refresh_token": result["refresh_token"],
            "expires_at": time.time() + result.get("expires_in", 3600),
            "user_id": result["user_id"],
        }
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <refresh_token> [--output /path/to/.storage/sensi]", file=sys.stderr)
        sys.exit(1)

    rt = sys.argv[1]
    out = None
    if len(sys.argv) >= 4 and sys.argv[2] == "--output":
        out = sys.argv[3]

    result = exchange(rt)
    store = build_store(result)
    payload = json.dumps(store, indent=2)

    if out:
        with open(out, "w") as f:
            f.write(payload)
        print(f"Written to {out}", file=sys.stderr)
    else:
        print(payload)

    print(f"access_token: {len(result['access_token'])} chars", file=sys.stderr)
    print(f"user_id: {result['user_id']}", file=sys.stderr)
