# Sentry SDK Instrumentation Patterns

Multi-language Sentry SDK initialization. DSNs are **public keys** — safe to hardcode.

## Python / FastAPI

```python
# At the VERY TOP of server.py (before any other imports that might crash)
import sentry_sdk
sentry_sdk.init(
    dsn="https://<key>@o<orgid>.ingest.us.sentry.io/<projectid>",
    environment="production",
    traces_sample_rate=0.1,
)

# ... all other imports, middleware, routes ...

# At the VERY END of server.py (after ALL middleware and routes are registered):
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
app = SentryAsgiMiddleware(app)
```

Pitfall: Placing `SentryAsgiMiddleware` immediately after `app = FastAPI()` breaks `app.add_middleware()` calls. Must go at end.

## Python / CLI

```python
# Top of main.py
import sentry_sdk
sentry_sdk.init(
    dsn="https://<key>@o<orgid>.ingest.us.sentry.io/<projectid>",
    environment="production",
    traces_sample_rate=0.1,
)
```

## React / TypeScript

```tsx
// Top of main.tsx/index.tsx — BEFORE createRoot()
import * as Sentry from '@sentry/react';

Sentry.init({
  dsn: 'https://<key>@o<orgid>.ingest.us.sentry.io/<projectid>',
  environment: 'production',
  integrations: [Sentry.browserTracingIntegration()],
  tracesSampleRate: 0.1,
});

// Wrap App with ErrorBoundary
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Sentry.ErrorBoundary fallback={<p>An error has occurred</p>}>
      <App />
    </Sentry.ErrorBoundary>
  </StrictMode>
);
```

Install: `npm install @sentry/react`

## Node.js / Docker (existing Sentry support)

If the app already has a `sentry.ts` that activates on env var:
```yaml
# docker-compose.yml — add to common-env or service env
environment:
  SENTRY_DSN: https://<key>@o<orgid>.ingest.us.sentry.io/<projectid>
```

## Creating Projects via API

```python
import requests

token = os.getenv("SENTRY_AUTH_TOKEN")
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# List teams to find correct slug
r = requests.get("https://sentry.io/api/0/organizations/<org>/teams/", headers=headers)
team_slug = r.json()[0]["slug"]

# Create project
r = requests.post(
    f"https://sentry.io/api/0/teams/{org}/{team_slug}/projects/",
    headers=headers,
    json={"name": "My Project", "slug": "my-project"}
)

# Get DSN
r = requests.get(f"https://sentry.io/api/0/projects/{org}/{slug}/keys/", headers=headers)
dsn = r.json()[0]["dsn"]["public"]
```

## Testing After Instrumentation

Python:
```python
import sentry_sdk
sentry_sdk.capture_exception(Exception("Test exception — verify instrumentation"))
```

The event should appear in the Sentry dashboard within seconds. The webhook pipeline (if set up) will then fire: knowledge store → Kanban card → Telegram.
