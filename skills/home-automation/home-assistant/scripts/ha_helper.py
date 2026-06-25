import urllib.request, urllib.parse, json, os

BASE = os.environ.get("HA_BASE_URL", "http://localhost:8123")
RT = os.environ.get("HA_REFRESH_TOKEN")

if not RT:
    raise RuntimeError("HA_REFRESH_TOKEN not set in environment")

def get_token():
    """Exchange refresh token for a fresh access token (valid 30 min)."""
    form = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": RT
    }).encode()
    req = urllib.request.Request(
        BASE + "/auth/token", data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    return json.loads(urllib.request.urlopen(req).read())["access_token"]

def call_service(domain, service, entity_id=None, data=None):
    """Call an HA service. Returns JSON response."""
    payload = {}
    if entity_id:
        payload["entity_id"] = entity_id
    if data:
        payload.update(data)
    token = get_token()
    req = urllib.request.Request(
        f"{BASE}/api/services/{domain}/{service}",
        data=json.dumps(payload).encode() if payload else None,
        headers={"Authorization": f"Bearer ***"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())

def get_state(entity_id=None):
    """Get all states or a specific entity."""
    token = get_token()
    url = BASE + "/api/states"
    if entity_id:
        url += "/" + entity_id
    req = urllib.request.Request(url,
        headers={"Authorization": f"Bearer ***    return json.loads(urllib.request.urlopen(req).read())

if __name__ == "__main__":
    print(f"Token valid: {get_token()[:20]}...")
    states = get_state()
    print(f"Entities: {len(states) if isinstance(states, list) else 'single'}")
