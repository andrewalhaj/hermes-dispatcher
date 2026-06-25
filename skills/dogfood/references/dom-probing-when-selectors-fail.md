# DOM probing when class selectors fail (purged Tailwind / CSS modules)

Many production SPAs ship with Tailwind purged or CSS-module hashed class names,
so `document.querySelector('[class*="message"]')` returns nothing and the
accessibility snapshot shows generic `<div>` with empty `class=""`. When that
happens, stop guessing class names and probe by *behavior* via `browser_evaluate`
(or `browser_console` with an `expression`). These probes are evidence-grade —
they read live layout/state the screenshot can't prove.

## Find the scroll container & verify "pinned to bottom"

Screenshots cannot prove scroll position. This can:

```js
() => {
  const el = Array.from(document.querySelectorAll('*')).find(e => {
    const s = getComputedStyle(e);
    return (s.overflowY === 'auto' || s.overflowY === 'scroll')
           && e.scrollHeight > e.clientHeight;
  });
  if (!el) return 'no scroll container';
  return {
    scrollTop: el.scrollTop, scrollHeight: el.scrollHeight,
    clientHeight: el.clientHeight,
    atBottom: el.scrollHeight - el.scrollTop - el.clientHeight < 10,
  };
}
```

`atBottom: true` is the real verification that a chat/log panel opened pinned to
the most recent message. (Used to confirm the Chat "open on most-recent session"
fix — the bottom-most text node was the current message, not yesterday's.)

## Read the last rendered messages (content the snapshot truncates)

TreeWalker over text nodes, then take the tail:

```js
() => {
  const texts = [];
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n; while (n = w.nextNode()) {
    const t = n.textContent.trim();
    if (t.length > 15 && t.length < 200) texts.push(t);
  }
  return texts.slice(-8); // last few = what's pinned at the bottom
}
```

This tells you *which* session/thread is actually loaded — compare the tail text
against the expected newest message.

## Detect dropdown / overlay clipping (overflow:hidden ancestor)

A screenshot makes a dropdown *look* clipped; confirm whether the item is truly
unreachable or just visually cut. Locate the menu item by text, check its rect is
on-screen, and walk ancestors for `overflow:hidden`:

```js
() => {
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n; const hits = [];
  while (n = w.nextNode()) {
    if (/^LH0\d$/.test(n.textContent.trim())) {
      const el = n.parentElement, r = el.getBoundingClientRect();
      hits.push({ text: n.textContent.trim(),
        onScreen: r.bottom <= innerHeight && r.width > 0, y: Math.round(r.y) });
    }
  }
  return hits;
}
```

If both items report `onScreen: true`, the "clipping" was cosmetic, not a real
bug — don't file it. If the second item's `y > innerHeight`, it's genuinely
clipped by an `overflow:hidden` card and IS a bug.

## Drive an element when click-by-ref times out

When `browser_click(ref=...)` fails with "`<div>` intercepts pointer events"
(usually a modal/overlay still mounted), either close the overlay first or click
the target programmatically:

```js
() => {
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n; while (n = w.nextNode()) {
    if (n.textContent.trim() === 'LH02') { n.parentElement.click(); return 'ok'; }
  }
  return 'not found';
}
```

A pointer-intercepting `<div>` that blocks nav clicks is itself a finding: it
usually means a detail panel / modal has no Escape handler and stays mounted.

## Hit the API directly to bisect frontend-vs-backend

When a panel shows "empty / no data," call its endpoint from page context to see
whether the bug is the API or the render layer:

```js
async () => {
  const r = await fetch('/api/logs?source=hermes&lines=3');
  return { status: r.status, body: JSON.stringify(await r.json()).slice(0, 300) };
}
```

Mismatch between the response shape and what the component reads is a classic
bug (e.g. API returns `{lines:[...]}` but the component expected a bare array).
Also catches **stale-process** bugs: the live server serving an old build returns
a different shape/row-count than the current source — verify the served bundle
hash matches the freshly built `dist/assets/index-<hash>.js` before blaming code.

## Pitfall: screenshot path must be readable by the vision step

`browser_take_screenshot` saves to the *browser process* cwd, not yours. An
`http://host/<file>.png` URL or an unresolved `media:` path will fail the vision
analyzer with "Invalid image source." Find the real file
(`search_files` for the PNG, newest first) and pass the absolute local path to
`vision_analyze`.
