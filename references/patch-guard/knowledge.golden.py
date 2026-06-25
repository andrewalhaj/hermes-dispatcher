#!/usr/bin/env python3
"""Hermes Knowledge Store — LanceDB-backed semantic memory for agent knowledge.

v2.0: Contextualized chunking with overlap-based paragraph splitting,
      Haiku-generated situating prefixes, sha256 caching, synthetic floor.
"""
import os, sys, json, time, uuid, textwrap, hashlib, re, urllib.request, urllib.error
import sqlite3
import math
from collections import OrderedDict
import numpy as np
# NOTE: lancedb and sentence_transformers are imported LAZILY inside get_db()
# and get_model() respectively. Their top-level import costs ~4.8s (torch +
# lancedb native libs). Keeping them lazy means callers that hit the warm
# daemon (kb_client) or only touch lightweight helpers never pay that cost —
# this is what lets `knowledge.py search` run in ~0.1s via the daemon path.

DB_DIR = os.path.expanduser('~/.hermes/knowledge_db')
TABLE_NAME = 'knowledge'
MODEL_NAME = 'all-mpnet-base-v2'  # 768-dim, best quality local model (was all-MiniLM-L6-v2)
MANIFEST_URL = 'http://localhost:2099/v1/chat/completions'
MANIFEST_MODEL = 'claude-haiku-4-5'  # cheapest contextual-prefix model
CHUNK_TARGET_CHARS = 800   # target chunk size for overlap chunker
CHUNK_MAX_CHARS = 1500     # hard cap — split paragraph internally if needed
PREFIX_TIMEOUT = 15        # seconds to wait for Manifest before falling back

# Lazy init
_db = None
_model = None
_manifest_key = None

def get_db():
    global _db
    if _db is None:
        import lancedb
        os.makedirs(DB_DIR, exist_ok=True)
        _db = lancedb.connect(DB_DIR)
        tables_resp = _db.list_tables()
        tables = tables_resp.tables if hasattr(tables_resp, 'tables') else tables_resp
        if TABLE_NAME not in tables:
            _db.create_table(TABLE_NAME, [{
                'id': 'init',
                'text': '',
                'vector': [0.0] * 768,
                'tags': '[]',
                'priority': 'normal',
                'source': '',
                'stored_at': time.time(),
                'context_prefix': '',
                'body_hash': '',
            }])
            tbl = _db.open_table(TABLE_NAME)
            tbl.delete("id = 'init'")
        else:
            # Schema migration: add context_prefix and body_hash columns if missing
            tbl = _db.open_table(TABLE_NAME)
            existing_cols = {c.name for c in tbl.schema}
            new_cols = []
            if 'context_prefix' not in existing_cols:
                new_cols.append(('context_prefix', ''))
            if 'body_hash' not in existing_cols:
                new_cols.append(('body_hash', ''))
            if new_cols:
                import pyarrow as pa
                fields = [pa.field(n, pa.string()) for n, _ in new_cols]
                tbl.add_columns(fields)
    return _db

def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model

def get_manifest_key():
    global _manifest_key
    if _manifest_key is None:
        config_path = os.path.expanduser('~/.hermes/config.yaml')
        try:
            with open(config_path) as f:
                for line in f:
                    m = re.match(r'\s*api_key:\s*(mnfst_\S+)', line)
                    if m:
                        _manifest_key = m.group(1)
                        break
        except Exception:
            pass
        if not _manifest_key:
            _manifest_key = ''  # will trigger synthetic floor
    return _manifest_key

GRAPH_DB = os.path.join(DB_DIR, 'graph.sqlite')

# ── A1: LRU embedding cache ──────────────────────────────────────────────
_EMBED_CACHE = OrderedDict()   # sha256(text) -> (vector, stored_at)
_EMBED_CACHE_CAP = 256
_EMBED_CACHE_TTL = 1800        # 30 min

def _cache_key(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def embed(texts):
    """Embed a list of texts → list of 384-dim vectors. LRU-cached (cap 256, 30min TTL)."""
    now = time.time()
    results = [None] * len(texts)
    misses, miss_idx = [], []
    for i, t in enumerate(texts):
        k = _cache_key(t)
        entry = _EMBED_CACHE.get(k)
        if entry is not None and (now - entry[1]) < _EMBED_CACHE_TTL:
            results[i] = entry[0]
            _EMBED_CACHE.move_to_end(k)
        else:
            if entry is not None:
                _EMBED_CACHE.pop(k, None)   # expired
            misses.append(t)
            miss_idx.append(i)
    if misses:
        model = get_model()
        embeddings = model.encode(misses, normalize_embeddings=True)
        for j, vec in enumerate(embeddings.tolist()):
            results[miss_idx[j]] = vec
            k = _cache_key(misses[j])
            _EMBED_CACHE[k] = (vec, now)
            _EMBED_CACHE.move_to_end(k)
            while len(_EMBED_CACHE) > _EMBED_CACHE_CAP:
                _EMBED_CACHE.popitem(last=False)   # evict oldest
    return results

# ── Paragraph-overlap chunker ────────────────────────────────────────────

def _split_paragraphs(text):
    """Split text into paragraphs on double-newlines. Preserve heading lines."""
    # Split on \n\n+, keeping separators attached to the following paragraph
    paras = re.split(r'\n\n+', text)
    return [p.strip() for p in paras if p.strip()]

def _heading_stack(lines, current_stack=None):
    """Walk lines, maintain a heading hierarchy stack. Returns list of (level, heading)."""
    stack = current_stack or []
    for line in lines:
        m = re.match(r'^(#{1,6})\s+(.+)', line)
        if m:
            level = len(m.group(1))
            heading = m.group(2).strip()
            # Pop headings at same or deeper level
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, heading))
    return stack

def _heading_breadcrumb(heading_stack):
    """Format heading stack as 'Doc Title > Section > Subsection'."""
    if not heading_stack:
        return ''
    return ' > '.join(h[1] for h in heading_stack)

def _leaf_heading_line(heading_stack):
    """Reconstruct the markdown heading line for the deepest (leaf) heading,
    e.g. (2, 'Manifest') -> '## Manifest'. Returns '' if no heading."""
    if not heading_stack:
        return ''
    level, heading = heading_stack[-1]
    return ('#' * int(level)) + ' ' + heading

def _normalize_chunk_heading(body, heading_stack):
    """Ensure a chunk body starts with its leaf heading line.

    The overlap chunker (1-paragraph overlap) can start a chunk on the lone
    content paragraph of a short section, producing a headerless twin of the
    previous chunk that differs ONLY by the heading line. Exact-hash dedup
    (body_hash) misses these. Prepending the leaf heading makes such twins
    byte-identical to the heading-bearing chunk, so body_hash collapses them.
    No-op when the body already leads with that heading line."""
    hl = _leaf_heading_line(heading_stack)
    if not hl:
        return body
    first_line = body.lstrip().split('\n', 1)[0].strip()
    if first_line == hl:
        return body
    return f"{hl}\n\n{body}"

def chunk_overlap(text, source_path=''):
    """Overlap-based paragraph chunking. Returns list of (chunk_body, heading_context, paragraphs).

    Chunks are ~CHUNK_TARGET_CHARS with 1-paragraph overlap between consecutive chunks.
    Each chunk tracks which heading(s) it falls under.
    """
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return []

    # Build heading context for each paragraph
    # Walk the text, tracking heading stack, assign to each paragraph
    lines = text.split('\n')
    para_headings = []
    stack = []
    para_idx = 0
    # Reconstruct which lines belong to which paragraph
    para_start_lines = {}
    pos = 0
    for i, para in enumerate(paragraphs):
        # Find where this paragraph starts in the original text
        idx = text.index(para, pos) if para in text[pos:] else pos
        # Count newlines before it to get line number
        line_no = text[:idx].count('\n')
        para_start_lines[i] = line_no
        pos = idx + len(para)

    # Now assign headings to each paragraph
    for i in range(len(paragraphs)):
        line_no = para_start_lines[i]
        # Rebuild heading stack up to this paragraph
        stack = []
        for j, line in enumerate(lines[:line_no + 1]):
            m = re.match(r'^(#{1,6})\s+(.+)', line)
            if m:
                level = len(m.group(1))
                heading = m.group(2).strip()
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, heading))
        para_headings.append(list(stack))  # copy

    # Build chunks with overlap
    chunks = []
    i = 0
    while i < len(paragraphs):
        chunk_paras = [paragraphs[i]]
        chunk_len = len(paragraphs[i])
        # Use the heading context from the FIRST paragraph in this chunk.
        # This is the most stable anchor — unlike the last paragraph,
        # it won't get reset by a high-level heading (e.g. "## Cron Jobs"
        # resetting the hierarchy from "Infra > Routing > DB Topology").
        heading_stack = para_headings[i]
        j = i + 1
        while j < len(paragraphs) and chunk_len + len(paragraphs[j]) < CHUNK_TARGET_CHARS:
            chunk_paras.append(paragraphs[j])
            chunk_len += len(paragraphs[j])
            j += 1

        body = '\n\n'.join(chunk_paras)
        # Prepend the leaf heading if this chunk starts mid-section (overlap
        # twin). Makes headerless overlap twins byte-identical to their
        # heading-bearing sibling so body_hash dedup collapses them.
        body = _normalize_chunk_heading(body, heading_stack)
        heading_ctx = _heading_breadcrumb(heading_stack)

        # If body exceeds max, split internally by sentences
        if len(body) > CHUNK_MAX_CHARS:
            sentences = re.split(r'(?<=[.!?])\s+', body)
            sub_body = ''
            for s in sentences:
                if len(sub_body) + len(s) > CHUNK_TARGET_CHARS and sub_body:
                    chunks.append((sub_body.strip(), heading_ctx, chunk_paras))
                    sub_body = s
                else:
                    sub_body = (sub_body + ' ' + s).strip()
            if sub_body:
                chunks.append((sub_body.strip(), heading_ctx, chunk_paras))
        else:
            chunks.append((body, heading_ctx, chunk_paras))

        # Advance: overlap by 1 paragraph
        i = max(i + 1, j - 1) if j > i + 1 else i + 1

    return chunks

# ── Contextual prefix generation ─────────────────────────────────────────

def _manifest_prefix(chunk_body, source_path, heading_context):
    """Generate a 1-sentence situating prefix via Manifest Haiku.

    Returns the prefix string, or '' on any failure (caller uses synthetic floor).
    """
    key = get_manifest_key()
    if not key:
        return ''

    # Build source context line
    fname = os.path.basename(source_path) if source_path else 'unknown'
    ctx = f"File: {fname}"
    if heading_context:
        ctx += f" | Section: {heading_context}"

    prompt = (
        f"You are annotating a passage for a semantic search index. "
        f"Given the source context and the passage below, write exactly ONE short sentence "
        f"that situates this passage — what document it's from and what topic or section it covers. "
        f"Be specific and factual. Do NOT summarize the content. "
        f"Output ONLY the sentence, nothing else.\n\n"
        f"Source context: {ctx}\n\n"
        f"Passage:\n{chunk_body[:2000]}"
    )

    payload = json.dumps({
        'model': MANIFEST_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 80,
        'temperature': 0.3,
    }).encode('utf-8')

    req = urllib.request.Request(
        MANIFEST_URL,
        data=payload,
        headers={
            'Authorization': f'***',
            'Content-Type': 'application/json',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=PREFIX_TIMEOUT) as resp:
            data = json.loads(resp.read())
            content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            # Clean up: take first sentence, strip quotes
            prefix = content.strip().strip('"').strip("'")
            # If it's multiple sentences, take just the first
            prefix = re.split(r'(?<=[.!?])\s+', prefix)[0]
            if len(prefix) < 10:
                return ''
            return prefix
    except Exception as e:
        # Haiku unreachable, inactive provider, timeout, etc. → synthetic floor
        return ''

def _synthetic_prefix(source_path, heading_context):
    """Fallback prefix when Manifest is unreachable."""
    fname = os.path.basename(source_path) if source_path else 'unknown'
    fname_clean = fname.replace('.md', '').replace('-', ' ').replace('_', ' ')
    if heading_context:
        return f"This passage is from {fname_clean}: {heading_context}."
    return f"This passage is from {fname_clean}."

def generate_prefix(chunk_body, source_path, heading_context):
    """Generate a situating prefix — Manifest Haiku with synthetic floor."""
    prefix = _manifest_prefix(chunk_body, source_path, heading_context)
    if not prefix:
        prefix = _synthetic_prefix(source_path, heading_context)
    return prefix

# ── Sha256 cache ─────────────────────────────────────────────────────────

def body_hash(chunk_body):
    """SHA-256 hex digest of the chunk body for cache-deduplication."""
    return hashlib.sha256(chunk_body.encode('utf-8')).hexdigest()[:16]

def find_by_hash(hash_val):
    """Check if a chunk with this body_hash already exists. Returns row dict or None."""
    db = get_db()
    tbl = db.open_table(TABLE_NAME)
    try:
        # LanceDB filter on body_hash column
        results = tbl.search([0.0] * 384).where(f"body_hash = '{hash_val}'").limit(1).to_list()
        # Actually, LanceDB search requires a vector. Try pandas filter instead.
        df = tbl.to_pandas()
        matches = df[df['body_hash'] == hash_val]
        if len(matches) > 0:
            row = matches.iloc[0]
            return {
                'id': row['id'],
                'text': row['text'],
                'context_prefix': row.get('context_prefix', ''),
            }
    except Exception:
        pass
    return None

# ── Contextualized store ─────────────────────────────────────────────────

def store_contextualized(chunk_body, heading_context, source_path, tags=None, priority='normal'):
    """Store a chunk with contextual prefix wrapping.

    1. Check sha256 cache — skip if unchanged.
    2. Validate against cold-store guard — raise ValueError on rejection.
    3. Generate situating prefix.
    4. Embed "{prefix}\\n\\n{chunk_body}" (NOT raw chunk).
    5. Store prefix in context_prefix column, hash in body_hash column.
    """
    bh = body_hash(chunk_body)
    existing = find_by_hash(bh)
    if existing:
        return existing['id']  # already contextualized, skip

    # Validate BEFORE generating prefix (expensive) or embedding
    entry_id = str(uuid.uuid4())[:8]
    ok, reason = _coldstore_validate(chunk_body, source_path)
    _coldstore_log(entry_id, 'allow' if ok else 'reject', reason or 'ok', source_path)
    if not ok:
        raise ValueError(f'[cold-store-guard] write rejected: {reason}')

    prefix = generate_prefix(chunk_body, source_path, heading_context)
    # The embedding text is contextualized: prefix + body
    embed_text = f"{prefix}\n\n{chunk_body}"

    db = get_db()
    tbl = db.open_table(TABLE_NAME)
    vector = embed([embed_text])[0]

    row = {
        'id': entry_id,
        'text': embed_text,
        'vector': vector,
        'tags': json.dumps(tags or []),
        'priority': priority,
        'source': source_path,
        'stored_at': time.time(),
        'context_prefix': prefix,
        'body_hash': bh,
    }
    tbl.add([row])
    return row['id']

# ── Cold-store schema guard (HERMES-GUARD cold-store-validator) ─────────────
# Fail-closed validator: every write to the cold store passes through
# _coldstore_validate() before tbl.add(). Returns (ok, reason).
# On error inside the guard, rejects the write (fail closed).
# Audit log: ~/.hermes/references/cold-store-audit.log
# To disable: export HERMES_COLDSTORE_GUARD=off
import re as _re, datetime as _dt

_COLDSTORE_GUARD_ENABLED = (
    os.environ.get('HERMES_COLDSTORE_GUARD', 'on').lower()
    not in ('off', '0', 'false', 'no')
)
_COLDSTORE_AUDIT_LOG = os.path.expanduser(
    '~/.hermes/references/cold-store-audit.log'
)

# Narrative/affect/methodology self-referential genre — reject these.
# Tuned NARROW: first-person self-diagnosis and affect only, NOT descriptive prose.
# Legitimate session digests contain decisions, outcomes, code facts — those must ACCEPT.
_COLDSTORE_BANNED_RE = _re.compile(
    r'\bI (felt|feel|sensed|thought I|found myself|noticed myself|caught myself)\b'
    r'|\bI was (feeling|struggling|overwhelmed|panicking|spiral)\b'
    r'|\b(a pull|the pull|felt (safer|risky|exposed|like a|like the))\b'
    r'|\b(grind|grinding|grinded) (works|helped|through|approach)\b'
    r'|\b(trust my|my own methodology|my instinct|my instincts|my gut)\b'
    r'|\b(learned to|reinforced that|trained me|i now (know|believe|trust) that)\b'
    r'|\bself.diagnos\b'
    r'|\b(frantic|frantically|panic.spiral|momentum (carried|pulled|took))\b'
    r'|\bwild.?card (moment|move|play)\b',
    _re.IGNORECASE,
)

# Hard minimum: reject entries shorter than 10 chars (empty/placeholder writes)
_COLDSTORE_MIN_CHARS = 10


def _coldstore_log(entry_id, decision, reason, source=''):
    """Append one audit line. Silently no-ops on any I/O error."""
    try:
        os.makedirs(os.path.dirname(_COLDSTORE_AUDIT_LOG), exist_ok=True)
        ts = _dt.datetime.now(_dt.timezone.utc).isoformat()
        with open(_COLDSTORE_AUDIT_LOG, 'a') as fh:
            fh.write(
                f"{ts} id={entry_id or '-'} source={source or '-'} "
                f"decision={decision} reason={reason}\n"
            )
    except Exception:
        pass


def _coldstore_validate(text, source=''):
    """
    Returns (ok: bool, reason: str).
    ok=True  → write allowed.
    ok=False → write rejected; reason is the human-readable cause.
    Fails closed: any internal exception → (False, 'guard-error:…').
    """
    if not _COLDSTORE_GUARD_ENABLED:
        return True, ''
    try:
        if not text or not str(text).strip():
            return False, 'empty-text'
        t = str(text).strip()
        if len(t) < _COLDSTORE_MIN_CHARS:
            return False, f'too-short:{len(t)}'
        m = _COLDSTORE_BANNED_RE.search(t)
        if m:
            return False, f'banned-narrative-affect:{m.group(0)!r}'
        return True, ''
    except Exception as exc:
        return False, f'guard-error:{exc}'


# ── Core store/search (backward compatible) ──────────────────────────────

def store(text, tags=None, priority='normal', source=''):
    """Store a fact in the knowledge DB (plain, non-contextualized).
    Passes through _coldstore_validate(); raises ValueError on rejection.
    """
    entry_id = str(uuid.uuid4())[:8]
    ok, reason = _coldstore_validate(text, source)
    _coldstore_log(entry_id, 'allow' if ok else 'reject', reason or 'ok', source)
    if not ok:
        raise ValueError(f'[cold-store-guard] write rejected: {reason}')
    db = get_db()
    tbl = db.open_table(TABLE_NAME)
    vector = embed([text])[0]
    row = {
        'id': entry_id,
        'text': text,
        'vector': vector,
        'tags': json.dumps(tags or []),
        'priority': priority,
        'source': source,
        'stored_at': time.time(),
        'context_prefix': '',
        'body_hash': '',
    }
    tbl.add([row])
    return row['id']

def _ensure_fts(tbl):
    """Ensure an FTS index exists on 'text'. Returns True if FTS is usable."""
    try:
        tbl.create_fts_index("text", replace=True)
        return True
    except Exception as e:
        print(f"[knowledge] FTS index unavailable, vector-only fallback: {e}", file=sys.stderr)
        return False

def _bm25_ranking(tbl, query, pool):
    """Return ordered list of row ids from BM25/FTS search. Empty list on failure."""
    try:
        res = tbl.search(query, query_type="fts").limit(pool).to_list()
        return [r['id'] for r in res]
    except Exception as e:
        print(f"[knowledge] BM25 search failed, vector-only: {e}", file=sys.stderr)
        return []

def _cosine(a, b):
    a = np.asarray(a, dtype=float); b = np.asarray(b, dtype=float)
    na = np.linalg.norm(a); nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))

_IMPORTANCE = {'critical': 1.0, 'high': 0.7, 'normal': 0.5, 'low': 0.3}

def search(query, top_k=5, tag_filter=None, min_priority=None, use_graph=True):
    """Hybrid search: vector + BM25 (RRF fusion) + priority/recency scoring + MMR + graph boost.

    v3.0. Backward-compatible: same return shape as before. Set use_graph=False to skip
    the wikilink-graph confirmatory boost.
    """
    db = get_db()
    tbl = db.open_table(TABLE_NAME)
    qvec = embed([query])[0]
    pool = max(top_k * 4, 20)

    # --- Vector search (fetch a larger pool before scoring) ---
    vec_results = tbl.search(qvec).limit(pool).to_list()
    by_id = {r['id']: r for r in vec_results}
    vec_rank = {r['id']: i for i, r in enumerate(vec_results)}

    # --- A3: BM25 keyword search via FTS ---
    _ensure_fts(tbl)
    bm25_ids = _bm25_ranking(tbl, query, pool)
    bm25_rank = {rid: i for i, rid in enumerate(bm25_ids)}
    bm25_n = max(len(bm25_ids), 1)
    # pull any BM25-only rows into the candidate map
    for rid in bm25_ids:
        if rid not in by_id:
            row = tbl.search().where(f"id = '{rid}'").limit(1).to_list()
            if row:
                by_id[rid] = row[0]

    # Adaptive fusion weight: bare-identifier queries (JINA_API_KEY, max_spawn_depth,
    # error codes) are exact-match intent — trust BM25 over semantics. Prose queries
    # stay vector-dominant.
    q_stripped = query.strip()
    is_exact_query = bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{2,}', q_stripped)) and (
        '_' in q_stripped or q_stripped.isupper() or ' ' not in q_stripped)
    w_vec, w_bm25 = (0.25, 0.75) if is_exact_query else (0.6, 0.4)

    now = time.time()
    hits = []
    for rid, r in by_id.items():
        tags = json.loads(r.get('tags', '[]'))
        priority = r.get('priority', 'normal')
        if tag_filter and not any(t in tags for t in tag_filter):
            continue
        if min_priority:
            order = {'critical': 0, 'high': 1, 'normal': 2, 'low': 3}
            if order.get(priority, 2) > order.get(min_priority, 2):
                continue

        # Normalized cosine similarity in [0,1] (robust to L2 metric + sign issues)
        rvec = r.get('vector')
        if rvec is not None:
            vec_sim = (_cosine(qvec, rvec) + 1.0) / 2.0
        else:
            vec_sim = max(0.0, 1.0 - r.get('_distance', 1.0) / 2.0)
        # BM25 strength: 1.0 at top rank, →0 at tail, 0.0 if absent from keyword hits
        bm25_strength = (1.0 - bm25_rank[rid] / bm25_n) if rid in bm25_rank else 0.0
        # Weighted hybrid (A3) — vector-dominant for prose, BM25-dominant for exact tokens
        score = w_vec * vec_sim + w_bm25 * bm25_strength
        # A2: importance weight
        score *= (0.7 + 0.3 * _IMPORTANCE.get(priority, 0.5))
        # A2: recency boost
        age_days = (now - r.get('stored_at', now)) / 86400.0
        score += math.exp(-age_days / 14.0) * 0.10

        hits.append({
            'id': rid,
            'text': r['text'],
            'score': round(score, 4),
            'tags': tags,
            'priority': priority,
            'source': r.get('source', ''),
            'stored_at': r.get('stored_at', 0),
            'context_prefix': r.get('context_prefix', ''),
            '_vector': r.get('vector'),
        })

    hits.sort(key=lambda h: h['score'], reverse=True)

    # --- B3: graph confirmatory boost ---
    if use_graph and hits:
        try:
            top_sources = {h['source'] for h in hits[:3] if h.get('source')}
            neighbors = set()
            for src in top_sources:
                neighbors |= graph_neighbors(_page_name(src), hops=1)
            for h in hits:
                pn = _page_name(h.get('source', ''))
                if pn and pn in neighbors:
                    h['score'] = round(h['score'] + 0.05, 4)
            hits.sort(key=lambda h: h['score'], reverse=True)
        except Exception:
            pass  # graph not built yet — no-op

    # --- A4: MMR diversity (only when returning more than 3) ---
    if top_k > 3:
        selected = []
        for h in hits:
            dup = False
            for s in selected:
                if h.get('_vector') is not None and s.get('_vector') is not None:
                    if _cosine(h['_vector'], s['_vector']) > 0.85:
                        dup = True
                        break
            if not dup:
                selected.append(h)
            if len(selected) >= top_k:
                break
        hits = selected
    else:
        hits = hits[:top_k]

    for h in hits:
        h.pop('_vector', None)
    return hits

# ── Markdown indexing ────────────────────────────────────────────────────

def index_markdown(content, source_path='', contextualize=False):
    """Chunk a markdown file and index each section.

    When contextualize=True: overlap-based paragraph chunking + contextual prefixes.
    When contextualize=False (default): heading-based chunking, plain text (legacy).
    """
    if contextualize:
        return _index_markdown_contextualized(content, source_path)

    # Legacy heading-based chunking
    sections = []
    current = []
    current_header = ''

    for line in content.split('\n'):
        if line.startswith('## ') or line.startswith('# '):
            if current:
                sections.append((current_header, '\n'.join(current).strip()))
            current_header = line.lstrip('# ').strip()
            current = [line]
        elif line.startswith('### '):
            if current:
                sections.append((current_header, '\n'.join(current).strip()))
            current_header = line.lstrip('# ').strip()
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append((current_header, '\n'.join(current).strip()))

    count = 0
    for header, body in sections:
        text = f"{header}: {body}" if header else body
        if len(text.strip()) < 20:
            continue
        store(text, tags=[source_path.split('/')[-1].replace('.md', '')],
              source=source_path)
        count += 1
    return count

def _index_markdown_contextualized(content, source_path):
    """Contextualized indexing: overlap chunks + situating prefixes + sha256 cache."""
    chunks = chunk_overlap(content, source_path)
    count = 0
    skipped = 0
    for body, heading_ctx, _paras in chunks:
        if len(body.strip()) < 20:
            continue
        fid = store_contextualized(body, heading_ctx, source_path,
                                   tags=[source_path.split('/')[-1].replace('.md', '')])
        count += 1
    return count

# ── Vault indexing ───────────────────────────────────────────────────────

def index_vault(vault_path=None, contextualize=False):
    """Index all markdown files in the Obsidian hermes-memories directory."""
    if vault_path is None:
        vault_path = os.path.expanduser('~/Documents/Obsidian Vault/hermes-memories')

    total = 0
    for root, dirs, files in os.walk(vault_path):
        dirs[:] = [d for d in dirs if not d.startswith('archive') and not d.startswith('backups')]
        for f in files:
            if not f.endswith('.md'):
                continue
            path = os.path.join(root, f)
            relpath = os.path.relpath(path, vault_path)
            try:
                with open(path) as fh:
                    content = fh.read()
                count = index_markdown(content, source_path=relpath, contextualize=contextualize)
                total += count
            except Exception as e:
                print(f"  Skip {path}: {e}", file=sys.stderr)
    return total

# ── Single-file contextualization ────────────────────────────────────────

def contextualize_file(filepath):
    """Fully contextualize a single file: chunk, prefix, embed, store.

    Prints a summary of what was done per chunk.
    """
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}", file=sys.stderr)
        return 0

    with open(filepath) as f:
        content = f.read()

    chunks = chunk_overlap(content, filepath)
    total = 0
    cached = 0

    for body, heading_ctx, _paras in chunks:
        if len(body.strip()) < 20:
            continue
        bh = body_hash(body)
        existing = find_by_hash(bh)
        if existing:
            print(f"  [cache hit] {existing['id']}: {existing['context_prefix'][:80]}...")
            cached += 1
            continue

        prefix = generate_prefix(body, filepath, heading_ctx)
        fid = store_contextualized(body, heading_ctx, filepath,
                                   tags=[os.path.basename(filepath).replace('.md', '')])
        print(f"  [stored] {fid}: {prefix[:100]}")
        total += 1

    print(f"\nContextualized: {total} new chunks, {cached} cache hits, {total + cached} total")
    return total

# ── Utility ──────────────────────────────────────────────────────────────

# ── B: Knowledge graph from wikilinks ────────────────────────────────────

def _page_name(path_or_name):
    """Normalize a source path or wikilink target to a bare page name (no dir, no .md)."""
    if not path_or_name:
        return ''
    base = str(path_or_name).strip().split('/')[-1]
    if base.endswith('.md'):
        base = base[:-3]
    return base.strip()

def _extract_frontmatter_lists(text):
    """Return (related_list, tags_list) parsed from a leading YAML frontmatter block."""
    related, tags = [], []
    if not text.startswith('---'):
        return related, tags
    end = text.find('\n---', 3)
    if end == -1:
        return related, tags
    fm = text[3:end]
    for key, bucket in (('related', related), ('tags', tags)):
        # inline list:  key: [a, b, c]
        m = re.search(rf'^{key}:\s*\[(.*?)\]', fm, re.MULTILINE)
        if m:
            bucket.extend(x.strip().strip('"\'') for x in m.group(1).split(',') if x.strip())
            continue
        # block list:  key:\n  - a\n  - b
        m = re.search(rf'^{key}:\s*\n((?:\s*-\s*.+\n?)+)', fm, re.MULTILINE)
        if m:
            for line in m.group(1).splitlines():
                v = line.strip().lstrip('-').strip().strip('"\'')
                if v:
                    bucket.append(v)
    return related, tags

def _graph_scan_dirs():
    dirs = [os.path.expanduser('~/.hermes/references')]
    for cand in ('~/wiki', os.environ.get('WIKI_PATH', '')):
        if cand:
            p = os.path.expanduser(cand)
            if os.path.isdir(p):
                dirs.append(p)
    return [d for d in dirs if os.path.isdir(d)]

def build_graph(paths=None):
    """Scan markdown files, extract wikilinks + frontmatter related/tags into graph.sqlite.
    Returns the number of edges written."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(GRAPH_DB)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS edges")
    cur.execute("CREATE TABLE edges (source_page TEXT, edge_type TEXT, target_page TEXT)")
    scan_dirs = paths or _graph_scan_dirs()
    wikilink_re = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')
    mdref_re = re.compile(r'([A-Za-z0-9][A-Za-z0-9._-]*\.md)')
    # First pass: collect the set of real page names that exist on disk
    known_pages = set()
    for d in scan_dirs:
        for root, _dirs, files in os.walk(d):
            for fn in files:
                if fn.endswith('.md'):
                    known_pages.add(_page_name(fn))
    edges = []
    for d in scan_dirs:
        for root, _dirs, files in os.walk(d):
            for fn in files:
                if not fn.endswith('.md'):
                    continue
                fpath = os.path.join(root, fn)
                src = _page_name(fn)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        text = f.read()
                except Exception:
                    continue
                for tgt in wikilink_re.findall(text):
                    edges.append((src, 'wikilink', _page_name(tgt)))
                # mdref: bare filename.md mentions pointing to a page that exists
                for raw in set(mdref_re.findall(text)):
                    tgt = _page_name(raw)
                    if tgt and tgt != src and tgt in known_pages:
                        edges.append((src, 'mdref', tgt))
                related, tags = _extract_frontmatter_lists(text)
                for r in related:
                    edges.append((src, 'related', _page_name(r)))
                for t in tags:
                    edges.append((src, 'tag', t.strip()))
    cur.executemany("INSERT INTO edges VALUES (?, ?, ?)", edges)
    conn.commit()
    conn.close()
    return len(edges)

def graph_neighbors(page, hops=2):
    """BFS over the edges table from `page`, up to `hops` hops. Returns set of page names."""
    page = _page_name(page)
    if not page or not os.path.exists(GRAPH_DB):
        return set()
    conn = sqlite3.connect(GRAPH_DB)
    cur = conn.cursor()
    visited, frontier = set(), {page}
    for _ in range(max(1, hops)):
        if not frontier:
            break
        nxt = set()
        for node in frontier:
            cur.execute(
                "SELECT target_page FROM edges WHERE source_page = ? "
                "UNION SELECT source_page FROM edges WHERE target_page = ?",
                (node, node))
            for (n,) in cur.fetchall():
                if n and n not in visited and n != page:
                    nxt.add(n)
        visited |= nxt
        frontier = nxt
    conn.close()
    visited.discard(page)
    return visited

# ── Eval harness ─────────────────────────────────────────────────────────

def eval_benchmark(benchmark_path=None, top_k=5):
    """Run benchmark queries and report precision/recall.

    Benchmark file: JSON array of {query, expected_id, description?}.
    Defaults to ~/.hermes/knowledge_db/benchmark_queries.json.

    Returns dict with metrics and per-query results.
    """
    if benchmark_path is None:
        benchmark_path = os.path.join(DB_DIR, 'benchmark_queries.json')
    if not os.path.exists(benchmark_path):
        print(f"No benchmark file at {benchmark_path}", file=sys.stderr)
        return {'error': 'no_benchmark_file', 'path': benchmark_path}

    with open(benchmark_path) as f:
        queries = json.load(f)

    results = []
    for q in queries:
        hits = search(q['query'], top_k=top_k)
        hit_ids = [h['id'] for h in hits]
        # Ground-truth matching: prefer 'expected_substring' (re-chunk robust —
        # survives dedup re-IDing) over the legacy volatile 'expected_id'.
        sub = q.get('expected_substring')
        if sub:
            sub_l = sub.lower()
            rank = -1
            for i, h in enumerate(hits):
                if sub_l in (h.get('text') or '').lower():
                    rank = i
                    break
            found = rank >= 0
            expected = sub
        else:
            expected = q.get('expected_id')
            found = expected in hit_ids
            rank = hit_ids.index(expected) if found else -1
        results.append({
            'query': q['query'],
            'expected': expected,
            'found': found,
            'rank': rank,
            'top_hit': hit_ids[0] if hits else None,
            'top_score': hits[0]['score'] if hits else 0,
            'description': q.get('description', ''),
        })

    p_at_5 = sum(1 for r in results if r['found']) / len(results)
    mrr = sum(1.0 / (r['rank'] + 1) for r in results if r['found']) / len(results)
    return {
        'p@5': round(p_at_5, 4),
        'MRR': round(mrr, 4),
        'total': len(results),
        'passed': sum(1 for r in results if r['found']),
        'results': results,
    }


def count_facts():
    db = get_db()
    tbl = db.open_table(TABLE_NAME)
    return tbl.count_rows()

def recent(limit=10):
    db = get_db()
    tbl = db.open_table(TABLE_NAME)
    all_rows = tbl.to_pandas()
    if len(all_rows) == 0:
        return []
    sorted_rows = all_rows.sort_values('stored_at', ascending=False).head(limit)
    results = []
    for _, r in sorted_rows.iterrows():
        prefix = r.get('context_prefix', '')
        text_preview = r['text'][:120]
        results.append({
            'id': r['id'],
            'text': text_preview,
            'tags': json.loads(r.get('tags', '[]')),
            'priority': r.get('priority', 'normal'),
            'stored_at': r.get('stored_at', 0),
            'context_prefix': prefix if prefix else '',
        })
    return results

# ── #3: Staleness detection ──────────────────────────────────────────────

_STALE_INFRA_TAGS = {'infrastructure', 'config', 'server', 'routing', 'deployment', 'manifest', 'database', 'gateway'}

def _extract_resources(text):
    """Extract IPs, file paths, hostnames, and URLs from fact text."""
    resources = []
    # IPv4
    for m in re.finditer(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b', text):
        resources.append(('ip', m.group(1)))
    # File paths (unix absolute or tilde)
    for m in re.finditer(r'(~?/[\w./-]+)', text):
        p = os.path.expanduser(m.group(1))
        if len(p) > 3:
            resources.append(('file', p))
    # localhost URLs
    for m in re.finditer(r'(https?://localhost:\d+[\w./-]*)', text):
        resources.append(('url', m.group(1)))
    return resources

def stale_check(threshold_days=30, dry_run=True):
    """Flag facts tagged as infra/config that reference stale resources or are too old."""
    db = get_db()
    tbl = db.open_table(TABLE_NAME)
    df = tbl.to_pandas()
    now = time.time()
    stale = []
    for _, r in df.iterrows():
        tags = set(json.loads(r.get('tags', '[]')))
        if not (tags & _STALE_INFRA_TAGS):
            continue
        issues = []
        # Age check
        age_days = (now - r.get('stored_at', 0)) / 86400.0
        if age_days > threshold_days:
            issues.append(f'age={age_days:.0f}d')
        # Resource checks
        if not dry_run:
            for kind, val in _extract_resources(r['text']):
                if kind == 'file' and not os.path.exists(val):
                    issues.append(f'missing_file={val}')
                elif kind == 'ip':
                    import socket
                    try:
                        s = socket.socket(); s.settimeout(1)
                        s.connect((val, 80)); s.close()
                    except:
                        try:
                            s = socket.socket(); s.settimeout(1)
                            s.connect((val, 22)); s.close()
                        except:
                            issues.append(f'unreachable_ip={val}')
                elif kind == 'url':
                    try:
                        req = urllib.request.Request(val, method='HEAD')
                        urllib.request.urlopen(req, timeout=2)
                    except:
                        issues.append(f'unreachable_url={val}')
        if issues:
            stale.append({'id': r['id'], 'priority': r.get('priority', 'normal'),
                          'text_preview': r['text'][:100], 'issues': issues})
    return stale

# ── #4: Auto-index watch ─────────────────────────────────────────────────

_AUTO_INDEX_MTIME = os.path.join(DB_DIR, '.last_index_mtime')

def auto_index(dirs=None):
    """Index any reference/vault files changed since the last run. Returns count of files indexed."""
    if dirs is None:
        dirs = [os.path.expanduser(d) for d in ['~/.hermes/references']]
        if os.environ.get('WIKI_PATH'):
            dirs.append(os.path.expanduser(os.environ['WIKI_PATH']))

    # Load last mtime
    last_run = 0.0
    if os.path.exists(_AUTO_INDEX_MTIME):
        with open(_AUTO_INDEX_MTIME) as f:
            last_run = float(f.read().strip())

    now = time.time()
    changed = 0
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fn in files:
                if not fn.endswith('.md'):
                    continue
                fpath = os.path.join(root, fn)
                if os.path.getmtime(fpath) > last_run:
                    try:
                        contextualize_file(fpath)
                        changed += 1
                    except Exception as e:
                        print(f'[auto-index] skipped {fpath}: {e}', file=sys.stderr)

    # Update mtime
    with open(_AUTO_INDEX_MTIME, 'w') as f:
        f.write(str(now))

    # Rebuild graph if anything changed
    if changed > 0:
        n = build_graph()
        print(f'[auto-index] indexed {changed} files, graph: {n} edges')

    return changed

# ── #5: Entity graph extraction ───────────────────────────────────────────

_ENTITY_PATTERNS = [
    ('ipv4', re.compile(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b')),
    ('port', re.compile(r'\b(:\d{2,5})\b')),
    ('container', re.compile(r'\b(mnfst-[a-z0-9-]+|ha-[a-z0-9]+|homeassistant)\b')),
    ('domain', re.compile(r'\b([a-z0-9][a-z0-9-]*\.[a-z]{2,}(?!/)(?:\d+)?)\b')),
    ('skill', re.compile(r'`([a-z][a-z0-9-]+)`\s+skill')),
]

_FILE_EXTENSIONS = {'.md', '.yaml', '.yml', '.sh', '.py', '.js', '.ts', '.json', '.toml', '.env', '.cfg', '.ini', '.css', '.html', '.prev', '.bak', '.txt', '.svg', '.png', '.jpg'}

def _skip_entity(etype, val):
    """Filter out known non-domain noise."""
    if etype == 'domain':
        for ext in _FILE_EXTENSIONS:
            if val.endswith(ext):
                return True
    return False

def _entity_page_name(entity_type, value):
    return f'ENTITY:{entity_type}:{value}'

def build_graph(paths=None, extract_entities=True):
    """Scan markdown files, extract wikilinks + frontmatter related/tags into graph.sqlite.
    If extract_entities=True, also add entity edges from fact text (IPs, ports, containers, domains, skills).
    Returns the number of edges written."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(GRAPH_DB)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS edges")
    cur.execute("CREATE TABLE edges (source_page TEXT, edge_type TEXT, target_page TEXT)")
    scan_dirs = paths or _graph_scan_dirs()
    wikilink_re = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')
    mdref_re = re.compile(r'([A-Za-z0-9][A-Za-z0-9._-]*\.md)')
    known_pages = set()
    for d in scan_dirs:
        for root, _dirs, files in os.walk(d):
            for fn in files:
                if fn.endswith('.md'):
                    known_pages.add(_page_name(fn))
    edges = []
    for d in scan_dirs:
        for root, _dirs, files in os.walk(d):
            for fn in files:
                if not fn.endswith('.md'):
                    continue
                fpath = os.path.join(root, fn)
                src = _page_name(fn)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        text = f.read()
                except Exception:
                    continue
                for tgt in wikilink_re.findall(text):
                    edges.append((src, 'wikilink', _page_name(tgt)))
                for raw in set(mdref_re.findall(text)):
                    tgt = _page_name(raw)
                    if tgt and tgt != src and tgt in known_pages:
                        edges.append((src, 'mdref', tgt))
                related, tags = _extract_frontmatter_lists(text)
                for r in related:
                    edges.append((src, 'related', _page_name(r)))
                for t in tags:
                    edges.append((src, 'tag', t.strip()))

    # #5: Entity extraction from fact text
    if extract_entities:
        db = get_db()
        tbl = db.open_table(TABLE_NAME)
        df = tbl.to_pandas()
        for _, row in df.iterrows():
            src = row.get('source', '') or ''
            if src:
                src = _page_name(src)
            else:
                src = row['id']  # fall back to fact ID as node name
            text = row['text']
            for etype, pattern in _ENTITY_PATTERNS:
                seen = set()
                for m in pattern.finditer(text):
                    val = m.group(1)
                    if val in seen:
                        continue
                    if _skip_entity(etype, val):
                        continue
                    seen.add(val)
                    tgt = _entity_page_name(etype, val)
                    edges.append((src, f'has_{etype}', tgt))

    cur.executemany("INSERT INTO edges VALUES (?, ?, ?)", edges)
    conn.commit()
    conn.close()
    return len(edges)

# ── #6: Synthesis tooling ─────────────────────────────────────────────────

def summarize(question, top_k=10):
    """Compile search results into a structured summary with citations and gap analysis.

    Returns a dict with: summary_lines (list of string bullets with citation IDs),
    gaps (list of query terms with zero hits), raw_hits (full search results).
    No LLM — pure compilation of retrieval results.
    """
    hits = search(question, top_k=top_k, use_graph=True)
    if not hits:
        return {'summary_lines': ['No results found.'], 'gaps': [question], 'raw_hits': []}

    # Build summary lines with citations
    lines = []
    for i, h in enumerate(hits[:top_k]):
        src = h.get('source', '') or 'untagged'
        prefix = f'[{h["priority"]}]' if h.get('priority') != 'normal' else ''
        lines.append(f'{i+1}. {prefix} {h["text"][:200]}  (id={h["id"]}, src={src})')

    # Gap analysis: split query into terms, check which have no matches at all
    terms = set(re.findall(r'[a-zA-Z_]{3,}', question.lower()))
    # For each term, check if any hit text or tags contain it
    all_text = ' '.join(h['text'].lower() for h in hits)
    all_tags = set()
    for h in hits:
        all_tags.update(t.lower() for t in h.get('tags', []))
    gaps = [t for t in sorted(terms) if t not in all_text and t not in all_tags]

    # Also check if any hit scored very low
    score_cutoff = max(h['score'] for h in hits) * 0.3
    weak = [h for h in hits if h['score'] < score_cutoff]
    if weak:
        gaps.append(f'(weak: {len(weak)} results below relevance threshold)')

    return {'summary_lines': lines, 'gaps': gaps, 'raw_hits': hits}


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'

    if cmd == 'status':
        count = count_facts()
        # Count contextualized
        db = get_db()
        tbl = db.open_table(TABLE_NAME)
        df = tbl.to_pandas()
        ctx_count = int((df['context_prefix'].notna() & (df['context_prefix'] != '')).sum()) if 'context_prefix' in df.columns else 0
        print(f"Knowledge DB: {count} facts ({ctx_count} contextualized) stored in {DB_DIR}")

    elif cmd == 'store' and len(sys.argv) > 2:
        contextualize = '--contextualize' in sys.argv
        args = [a for a in sys.argv[2:] if a != '--contextualize']
        if not args:
            print("Usage: knowledge.py store [--contextualize] <text>", file=sys.stderr)
            sys.exit(1)
        text = ' '.join(args)
        tags_raw = os.environ.get('KNOWLEDGE_TAGS', '')
        tags = [t.strip() for t in tags_raw.split(',') if t.strip()]
        priority = os.environ.get('KNOWLEDGE_PRIORITY', 'normal')

        if contextualize:
            # Treat as a single-chunk file for contextualization
            chunks = chunk_overlap(text, source_path='cli-input')
            for body, heading_ctx, _paras in chunks:
                if len(body.strip()) < 20:
                    continue
                fid = store_contextualized(body, heading_ctx, 'cli-input', tags=tags, priority=priority)
                print(f"Stored (contextualized): {fid}")
        else:
            fid = store(text, tags=tags, priority=priority)
            print(f"Stored: {fid}")

    elif cmd == 'search' and len(sys.argv) > 2:
        query = ' '.join(sys.argv[2:])
        top_k = int(os.environ.get('KNOWLEDGE_TOP_K', '5'))
        # Fast path: try the warm daemon (kb_daemon.py) — turns the ~7.9s
        # cold-start into ~0.1s. Falls back to in-process search on ANY daemon
        # failure, so the daemon is pure acceleration, never a dependency.
        # Set KB_NO_DAEMON=1 to force in-process (e.g. for benchmarking).
        hits = None
        if os.environ.get('KB_NO_DAEMON') != '1':
            try:
                _cdir = os.path.dirname(os.path.abspath(__file__))
                if _cdir not in sys.path:
                    sys.path.insert(0, _cdir)
                from kb_client import daemon_search, DaemonUnavailable
                try:
                    hits = daemon_search(query, top_k=top_k)
                except DaemonUnavailable:
                    hits = None
            except Exception:
                hits = None
        if hits is None:
            hits = search(query, top_k=top_k)
        for h in hits:
            prefix_info = f" [{h.get('context_prefix', '')}]" if h.get('context_prefix') else ''
            print(f"[{h['score']}] [{h['priority']}]{prefix_info} {h['text'][:200]}")
            print(f"  tags: {h['tags']}  id: {h['id']}\n")

    elif cmd == 'search-batch' and len(sys.argv) > 2:
        # Batch dedup-check: run N queries in ONE process so the embedding
        # model + LanceDB connection load exactly once instead of N times.
        # Queries are '|||'-separated (or newline-separated via stdin '-').
        # Used by the Daily Knowledge Capture cron to avoid 17 sequential
        # cold-start invocations (pending-fixes.md Entry 9, 2026-06-06).
        raw = sys.argv[2]
        if raw == '-':
            raw = sys.stdin.read()
            sep = '\n'
        else:
            sep = '|||'
        queries = [q.strip() for q in raw.split(sep) if q.strip()]
        top_k = int(os.environ.get('KNOWLEDGE_TOP_K', '5'))
        for q in queries:
            print(f"=== QUERY: {q} ===")
            hits = search(q, top_k=top_k)
            if not hits:
                print("  (no existing facts — safe to store)\n")
                continue
            for h in hits:
                prefix_info = f" [{h.get('context_prefix', '')}]" if h.get('context_prefix') else ''
                print(f"[{h['score']}] [{h['priority']}]{prefix_info} {h['text'][:200]}")
                print(f"  tags: {h['tags']}  id: {h['id']}")
            print()

    elif cmd == 'recent':
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        for r in recent(limit):
            prefix_info = f" [{r.get('context_prefix', '')}]" if r.get('context_prefix') else ''
            print(f"[{r['priority']}]{prefix_info} {r['id']}: {r['text']}")

    elif cmd == 'build-graph':
        n = build_graph()
        print(f"Knowledge graph: {n} edges written to {GRAPH_DB}")

    elif cmd == 'graph-query' and len(sys.argv) > 2:
        page = ' '.join(sys.argv[2:])
        hops = int(os.environ.get('GRAPH_HOPS', '2'))
        neighbors = graph_neighbors(page, hops=hops)
        print(f"Neighbors of '{_page_name(page)}' (≤{hops} hops): {len(neighbors)}")
        for n in sorted(neighbors):
            print(f"  - {n}")

    elif cmd == 'eval':
        bpath = sys.argv[2] if len(sys.argv) > 2 else None
        top_k = int(os.environ.get('EVAL_TOP_K', '5'))
        result = eval_benchmark(bpath, top_k=top_k)
        if 'error' in result:
            print(f"Error: {result['error']} ({result['path']})")
            sys.exit(1)
        pct = round(result['p@5'] * 100, 1)
        print(f"Benchmark: {result['passed']}/{result['total']} passed, P@5={pct}%, MRR={result['MRR']}")
        for r in result['results']:
            status = "✓" if r['found'] else "✗"
            detail = f"rank={r['rank']}" if r['found'] else f"top={r['top_hit']}"
            print(f"  {status} {r['description']} [{detail}]  query='{r['query'][:60]}'")

    elif cmd == 'stale-check':
        dry = '--live' not in sys.argv
        threshold = int(os.environ.get('STALE_THRESHOLD_DAYS', '30'))
        results = stale_check(threshold_days=threshold, dry_run=dry)
        mode = 'DRY RUN' if dry else 'LIVE CHECK'
        if not results:
            print(f'Staleness check ({mode}, threshold={threshold}d): 0 stale facts')
        else:
            print(f'Staleness check ({mode}, threshold={threshold}d): {len(results)} stale')
            for r in results:
                print(f'  [{r["priority"]}] {r["id"]}: {r["text_preview"][:80]}')
                for issue in r['issues']:
                    print(f'    -> {issue}')

    elif cmd == 'auto-index':
        changed = auto_index()
        if changed == 0:
            print('auto-index: no changed files')

    elif cmd == 'summarize' and len(sys.argv) > 2:
        question = ' '.join(sys.argv[2:])
        top_k = int(os.environ.get('SUMMARIZE_TOP_K', '10'))
        result = summarize(question, top_k=top_k)
        n = len(result["summary_lines"])
        print(f'Results ({n}):')
        for line in result['summary_lines']:
            print(line)
        if result['gaps']:
            gap_list = ", ".join(result['gaps'])
            print()
            print(f'Gaps: {gap_list}')
        else:
            print()
            print('Gaps: none')

    elif cmd == 'contextualize-file' and len(sys.argv) > 2:
        filepath = sys.argv[2]
        contextualize_file(filepath)

    elif cmd == 'index-vault':
        contextualize = '--contextualize' in sys.argv
        args = [a for a in sys.argv[2:] if a != '--contextualize']
        path = args[0] if args else None
        mode = "contextualized" if contextualize else "standard"
        print(f"Indexing vault ({mode})...")
        n = index_vault(path, contextualize=contextualize)
        print(f"Indexed {n} sections from vault")
        print(f"Total facts: {count_facts()}")

    elif cmd == 'test':
        # Quick smoke test
        fid = store("Hermes uses Manifest router at localhost:2099 for all model requests",
                     tags=["manifest", "config", "routing"], priority="high")
        print(f"Test store: {fid}")
        hits = search("manifest model routing", top_k=2)
        print(f"Test search: {len(hits)} results")
        for h in hits:
            print(f"  [{h['score']}] {h['text'][:100]}")

        # Test contextualized store
        print("\n--- Contextualized test ---")
        test_chunk = "The nginx proxy on the backup host provides HA failover, not load balancing. It uses the backup directive to keep the local Manifest dormant until the primary fails."
        chunks = chunk_overlap(test_chunk, source_path='test/infrastructure.md')
        for body, heading_ctx, _paras in chunks:
            fid = store_contextualized(body, heading_ctx, 'test/infrastructure.md',
                                       tags=['infrastructure', 'test'], priority='normal')
            print(f"Contextualized store: {fid}")
            hits = search("nginx proxy failover", top_k=2)
            for h in hits:
                print(f"  [{h['score']}] prefix='{h.get('context_prefix', 'N/A')}' text={h['text'][:100]}")

    elif cmd == 'test-contextualize':
        # Full contextualize test with a temp file
        test_md = """# Infrastructure Overview

## Routing Architecture

Manifest routes all model requests through a complexity classifier.
The classifier scores each request across 23 dimensions and assigns a tier.

### Nginx HA Proxy

The nginx proxy on the backup host provides HA failover, not load balancing.
It uses the backup directive to keep the local Manifest dormant until the primary fails.
This means 100% of traffic hits the primary Manifest under normal conditions.

### Database Topology

Both Manifest instances share a single Railway PostgreSQL database.
This ensures identical routing behavior across both hosts.
The local mnfst-postgres-1 container is unused and its data is stale.

## Cron Jobs

Six cron jobs run on the primary server, including the Infra Watchdog.
The watchdog runs every 15 minutes and only alerts on P0/P1 incidents.
"""
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as tf:
            tf.write(test_md)
            tmpath = tf.name

        print(f"Testing contextualize-file on {tmpath}")
        contextualize_file(tmpath)

        # Verify search
        print("\n--- Search test ---")
        hits = search("nginx HA failover", top_k=2)
        for h in hits:
            print(f"  [{h['score']}] prefix='{h.get('context_prefix', 'N/A')}'")
            print(f"  text preview: {h['text'][:150]}")

        os.unlink(tmpath)

    else:
        print("Usage: knowledge.py [status|store|search|recent|index-vault|contextualize-file|test|test-contextualize]")
        print()
        print("Commands:")
        print("  status                          Show DB stats")
        print("  store [--contextualize] <text>  Store a fact (with optional contextual prefix)")
        print("  search <query>                  Semantic search")
        print("  recent [N]                      Show N most recent entries")
        print("  build-graph                     Build wikilink/entity/cross-reference knowledge graph")
        print("  graph-query <page>              Show graph neighbors of a page (GRAPH_HOPS=2)")
        print("  eval [benchmark.json]           Run benchmark and report P@5/MRR")
        print("  stale-check [--live]            Find facts with stale/aged references (dry-run default)")
        print("  auto-index                      Index changed reference files since last run")
        print("  summarize <question>            Compile search results with citations + gap analysis")
        print("  index-vault [--contextualize] [path]")
        print("                                  Index Obsidian vault markdown files")
        print("  contextualize-file <path>       Contextualize a single file with prefix generation")
        print("  test                            Quick smoke test")
        print("  test-contextualize              Full contextualization test")
        print()
        print("Env vars: KNOWLEDGE_TAGS=tag1,tag2  KNOWLEDGE_PRIORITY=high  KNOWLEDGE_TOP_K=5")
