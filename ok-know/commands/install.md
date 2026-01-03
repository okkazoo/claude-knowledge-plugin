---
name: install
description: Install knowledge base structure in current project
allowed-tools: Bash, Write
---

# Install Knowledge Base

Sets up the `.claude/knowledge/` directory structure for persistent project knowledge.

## Instructions

### 1. Create Directory Structure

```bash
mkdir -p .claude/knowledge/journey .claude/knowledge/facts .claude/knowledge/patterns .claude/knowledge/savepoints
```

### 2. Create Index Files (if missing)

**Only create if they don't exist** - never overwrite existing knowledge:

```bash
[ -f ".claude/knowledge/knowledge.json" ] && echo "knowledge.json exists" || echo "creating knowledge.json"
[ -f ".claude/knowledge/coderef.json" ] && echo "coderef.json exists" || echo "creating coderef.json"
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

If `.claude/knowledge/coderef.json` does NOT exist, create it:
```json
{
  "version": 1,
  "updated": null,
  "files": {}
}
```

### 3. Confirm

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
