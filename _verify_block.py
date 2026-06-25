import os, traceback
from pathlib import Path
HERMES_HOME = Path(os.environ.get("HERMES_HOME", "/root/.hermes"))
try:
    import sys
    sys.path.insert(0, str(HERMES_HOME / "scripts"))
    import knowledge as kb
    kb_rows = kb.recent(200)
    print("rows:", len(kb_rows))
    for row in kb_rows[:1]:
        text = row.get("text", "") or ""
        priority = row.get("priority", "normal")
        node = {
            "id": f"kb-{row['id'][:8]}",
            "label": text[:40],
            "tier": "knowledge",
            "body": text[:300],
            "metadata": {"priority": priority},
        }
        print(node)
except Exception:
    traceback.print_exc()
