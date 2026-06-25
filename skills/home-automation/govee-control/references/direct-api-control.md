# Direct API Control — Govee

When the `govee.py` script can't disambiguate a device name (e.g., "Bathroom" matches "Bathroom 1", "Bathroom 2", and "Bathroom 3"), use the device ID directly via a Python snippet.

## List devices with their IDs

```bash
python3 -c "
import os, json, urllib.request
with open(os.path.expanduser('~/.hermes/.env')) as f:
    for line in f:
        if line.startswith('GOVEE_API_KEY'):
            key = line.strip().split('=',1)[1]
            break
req = urllib.request.Request('https://openapi.api.govee.com/router/api/v1/user/devices')
req.add_header('Govee-API-Key', key)
with urllib.request.urlopen(req, timeout=10) as r:
    for d in json.loads(r.read()).get('data',[]):
        print(f'{d[\"deviceName\"]:<30} {d[\"device\"]:<20} {d[\"sku\"]}')
"
```

## Turn off by device ID

```python
import os, json, uuid, urllib.request

with open(os.path.expanduser('~/.hermes/.env')) as f:
    for line in f:
        if line.startswith('GOVEE_API_KEY'):
            API_KEY = line.strip().split('=', 1)[1]
            break

body = {
    'requestId': str(uuid.uuid4()),
    'payload': {
        'sku': 'SameModeGroup',
        'device': '15807664',  # device ID from list output
        'capability': {
            'type': 'devices.capabilities.on_off',
            'instance': 'powerSwitch',
            'value': 0  # 0=off, 1=on
        }
    }
}

url = 'https://openapi.api.govee.com/router/api/v1/device/control'
req = urllib.request.Request(url, method='POST')
req.add_header('Content-Type', 'application/json')
req.add_header('Govee-API-Key', API_KEY)

with urllib.request.urlopen(req, data=json.dumps(body).encode(), timeout=10) as r:
    print(r.read().decode())
```

## Set color by device ID (for ambiguous names)

Same pattern, but change the capability:

```python
'capability': {
    'type': 'devices.capabilities.color_setting',
    'instance': 'colorRgb',
    'value': rgb_int  # (R << 16) | (G << 8) | B
}
```

## Set brightness by device ID

```python
'capability': {
    'type': 'devices.capabilities.range',
    'instance': 'brightness',
    'value': pct  # 1-100
}
```

## Known device IDs (from 2026-06-02 scan)

| Name | Device ID | SKU |
|------|-----------|-----|
| Living Room Lamp | 2F:CF:5C:E7:53:F0:5E:6E | H1401 |
| Lantern Floor Lamp | 25:9C:DB:B2:28:8D:F8:2D | H1630 |
| TV | 8E:86:C0:4A:A1:2C:7A:4A | H6604 |
| Bathroom 1 | 7C:37:5C:E7:53:C7:50:B6 | H6006 |
| Bathroom 2 | 1F:E5:5C:E7:53:C6:94:B4 | H6006 |
| Bathroom 3 | F1:A7:5C:E7:53:C4:94:72 | H6006 |
| Andrew's Office Fan | 2F:A2:FE:F6:B1:78:0F:1B | H1310 |
| Bathroom (group) | 15838108 | SameModeGroup |
| Andrew's Office (group) | 15807664 | SameModeGroup |
