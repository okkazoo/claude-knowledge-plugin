---
name: init
description: Initialize knowledge base structure in current project
allowed-tools: Bash, Write
argument-hint: (no arguments)
---

# Initialize Knowledge Base

Sets up the `.claude/knowledge/` directory structure for persistent project knowledge.

## Instructions

### 1. Create Directory Structure

```bash
mkdir -p .claude/knowledge/journey .claude/knowledge/facts .claude/knowledge/patterns .claude/knowledge/checkpoints .claude/knowledge/versions
```

### 2. Create Index Files

Create `.claude/knowledge/knowledge.json`:
```json
{
  "version": 1,
  "updated": "",
  "files": {},
  "patterns": []
}
```

Create `.claude/knowledge/coderef.json`:
```json
{
  "version": 1,
  "updated": null,
  "files": {}
}
```

### 3. Create Helper Script

Copy the `_wip_helpers.py` script to `.claude/knowledge/journey/`

### 4. Confirm

```
Knowledge base initialized!

Structure created:
  .claude/knowledge/
  ├── journey/      (work-in-progress entries)
  ├── facts/        (quick facts, gotchas)
  ├── patterns/     (extracted solutions)
  ├── checkpoints/  (state snapshots)
  └── versions/     (version history)

Use /knowledge-base:wip to save progress.
```
