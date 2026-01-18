# /memory - Dynamic Memory System

You are the memory management assistant for ok-know. Help users interact with their project's memory system.

## Memory Location
Database: `.claude/knowledge/memory.db`
Config: `.claude/knowledge/config.json`

## Usage Patterns

### Show Status (default, no args)
Display memory statistics and recent facts.

**Action:**
1. Run this Python snippet to get stats:
```python
import sys
sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
from core.database import Database
from core.config import Config

config = Config.load()
db = Database(config)
stats = db.get_stats()
recent = db.get_recent_facts(5)

print(f"Total facts: {stats['total_facts']}")
print(f"By type: {stats['by_type']}")
print(f"With embeddings: {stats['with_embeddings']}")
print("\nRecent facts:")
for f in recent:
    print(f"  [{f.fact_type.value}] {f.text[:80]}")
db.close()
```

### Search Memory: `/memory search <query>`
Search for relevant facts using hybrid search (keyword + semantic).

**Action:**
1. Extract the search query from args
2. Run hybrid search:
```python
import sys
sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
from core.searcher import Searcher

searcher = Searcher()
results = searcher.search("<query>", top_k=10)

for fact, score in results:
    print(f"[{fact.fact_type.value}] (score: {score:.2f})")
    print(f"  {fact.text}")
    if fact.file_refs:
        print(f"  Files: {', '.join(fact.file_refs)}")
    print()
```

### Add Fact: `/memory add <fact text>`
Manually add a fact to memory.

**Action:**
1. Parse the fact text and optional flags:
   - `-t <type>`: solution, gotcha, tried-failed, decision, context (default: context)
   - `-f <file>`: Associate with a file
2. Create and store the fact:
```python
import sys
sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
from core.extractor import manual_fact
from core.database import Database
from core.config import Config
from core.models import FactType

config = Config.load()
db = Database(config)

fact = manual_fact(
    text="<fact text>",
    fact_type=FactType.<TYPE>,
    file_refs=["<file>"] if file else None
)
fact_id = db.add_fact(fact)
print(f"Added fact: {fact_id[:8]}...")
db.close()
```

### Forget Fact: `/memory forget <id>`
Remove a fact from memory.

**Action:**
1. Delete the fact by ID (first 8 chars is enough):
```python
import sys
sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
from core.database import Database
from core.config import Config

config = Config.load()
db = Database(config)

# Search for fact by partial ID
cursor = db.conn.cursor()
rows = cursor.execute(
    "SELECT id, text FROM facts WHERE id LIKE ?",
    ("<id>%",)
).fetchall()

if rows:
    for row in rows:
        db.delete_fact(row['id'])
        print(f"Deleted: {row['text'][:50]}...")
else:
    print("No fact found with that ID")
db.close()
```

### Export to JSON: `/memory export`
Export all facts to a JSON file.

**Action:**
```python
import sys
import json
sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
from core.database import Database
from core.config import Config
from pathlib import Path

config = Config.load()
db = Database(config)

facts = db.get_recent_facts(1000)  # Get all
export_data = [f.to_dict() for f in facts]

export_path = Path('.claude/knowledge/memory_export.json')
export_path.write_text(json.dumps(export_data, indent=2, default=str))
print(f"Exported {len(facts)} facts to {export_path}")
db.close()
```

### Import from JSON: `/memory import <file>`
Import facts from a JSON file.

**Action:**
```python
import sys
import json
sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
from core.database import Database
from core.config import Config
from core.models import AtomicFact
from pathlib import Path

config = Config.load()
db = Database(config)

data = json.loads(Path("<file>").read_text())
count = 0
for item in data:
    fact = AtomicFact.from_dict(item)
    db.add_fact(fact)
    count += 1

print(f"Imported {count} facts")
db.close()
```

### Migrate from ok-know v1: `/memory migrate`
Migrate data from the old ok-know format.

**Action:**
Run the migration script:
```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/migrate_ok_know.py
```

## Fact Types
- **solution**: Working approach or fix
- **gotcha**: Important warning/caveat (shown at session start)
- **tried-failed**: Approach that didn't work
- **decision**: Design or architecture decision
- **context**: General project context

## Examples

```
/memory                        # Show status
/memory search "hook error"    # Search for facts about hook errors
/memory add "Use python prefix for hooks on Windows" -t gotcha
/memory add "API uses JWT auth" -t decision -f src/api/auth.py
/memory forget abc123          # Delete fact starting with abc123
/memory export                 # Export to JSON
/memory migrate                # Migrate from v1
```
