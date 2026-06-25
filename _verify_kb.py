import sys
from pathlib import Path
HERMES_HOME = Path("/root/.hermes")
sys.path.insert(0, str(HERMES_HOME / "scripts"))
import knowledge as kb
rows = kb.recent(200)
print("rows:", len(rows))
if rows:
    print(rows[0])
