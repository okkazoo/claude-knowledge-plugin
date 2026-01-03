---
name: install
description: Install knowledge base structure in current project
allowed-tools: Bash, Write
model: haiku
---

# Install Knowledge Base

Sets up the `.claude/knowledge/` directory structure for persistent project knowledge.

## Instructions

### 1. Check if Already Installed

```bash
[ -d ".claude/knowledge" ] && echo "EXISTS" || echo "NEW"
```

**If EXISTS**, respond:
```
Knowledge base already installed.

Use /ok-know:knowledge to see status.
```
Then stop - do not continue to other steps.

**If NEW**, continue to step 2.

### 2. Create Directory Structure

```bash
mkdir -p .claude/knowledge/journey .claude/knowledge/facts .claude/knowledge/patterns .claude/knowledge/savepoints
```

### 3. Create Index Files

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

### 4. Confirm

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
