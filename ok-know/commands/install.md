---
name: install
description: Install knowledge base structure in current project
allowed-tools:
  - Bash
  - Write
model: sonnet
---

# Install Knowledge Base

Sets up the `.claude/knowledge/` directory structure for persistent project knowledge.

## Instructions

### 1. Check Installation Status

```bash
echo "=== Checking knowledge base ===" && \
[ -d ".claude/knowledge" ] && echo "DIR:EXISTS" || echo "DIR:NEW" && \
[ -d ".claude/knowledge/journey" ] && echo "JOURNEY:OK" || echo "JOURNEY:MISSING" && \
[ -d ".claude/knowledge/facts" ] && echo "FACTS:OK" || echo "FACTS:MISSING" && \
[ -d ".claude/knowledge/patterns" ] && echo "PATTERNS:OK" || echo "PATTERNS:MISSING" && \
[ -d ".claude/knowledge/savepoints" ] && echo "SAVEPOINTS:OK" || echo "SAVEPOINTS:MISSING" && \
[ -f ".claude/knowledge/knowledge.json" ] && echo "INDEX:OK" || echo "INDEX:MISSING"
```

**Evaluate the output:**

- **If DIR:NEW** → Fresh install, continue to step 2
- **If any MISSING** → Repair install, continue to step 2
- **If all OK** → Existing install, skip to step 3 (rebuild index)

### 2. Create/Repair Directory Structure

```bash
mkdir -p .claude/knowledge/journey .claude/knowledge/facts .claude/knowledge/patterns .claude/knowledge/savepoints
```

If `.claude/knowledge/knowledge.json` does NOT exist, create it:
```json
{
  "version": 1,
  "updated": "",
  "files": {},
  "patterns": []
}
```

### 3. Rebuild Knowledge Index

Always run this to ensure knowledge.json is populated with existing content:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/_wip_helpers.py" rebuild_knowledge_index
```

### 4. Confirm

**For fresh/repaired install:**
```
Knowledge base installed!

Structure:
  .claude/knowledge/
  ├── journey/      (work-in-progress entries)
  ├── facts/        (quick facts, gotchas)
  ├── patterns/     (extracted solutions)
  └── savepoints/   (state snapshots)

Commands:
  /ok-know:wip          Save work-in-progress
  /ok-know:wip -f       Save a fact directly
  /ok-know:save         Create restore point
  /ok-know:knowledge    Show status
```

**For existing install (all OK):**
```
Knowledge base verified and index rebuilt.

Use /ok-know:knowledge to see status.
```
