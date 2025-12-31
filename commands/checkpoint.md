---
name: checkpoint
description: Save current working state before risky changes. Creates a restore point.
allowed-tools: Read, Write, Bash
argument-hint: [description]
---

# Save Checkpoint

## When to Use

Before:
- Major refactoring
- Risky changes to core files
- Experimenting with something uncertain
- Any change affecting 3+ files

## Instructions

### 1. Ensure Knowledge Base Exists

```bash
if [ ! -d ".claude/knowledge" ]; then
  echo "Knowledge base not initialized. Run /knowledge-base:init first."
  exit 1
fi
```

### 2. Capture Current State

```bash
git status --short
git diff --stat HEAD~3..HEAD 2>/dev/null || echo "No recent commits"
git diff --name-only 2>/dev/null
```

### 3. Create Checkpoint File

Save to: `.claude/knowledge/checkpoints/YYYY-MM-DD-HH-MM-[description-slug].md`

```markdown
# Checkpoint: [Description]

## Date: YYYY-MM-DD HH:MM
## Git Branch: [branch name]
## Git Commit: [short hash]

## Description
[User's description or auto-generated from context]

## State at Checkpoint

### Modified Files
- [file1.py]
- [file2.jsx]

### Recent Changes
[Summary of what was done before checkpoint]

## To Restore

If things break after this checkpoint:

1. Review what changed:
   ```bash
   git diff [commit-hash]..HEAD
   ```

2. Revert to this state:
   ```bash
   git checkout [commit-hash] -- .
   ```
```

### 4. Optionally Stage/Commit

Ask user if they want to commit current changes before proceeding.

### 5. Confirm

```
Checkpoint saved: [description]
File: .claude/knowledge/checkpoints/YYYY-MM-DD-HH-MM-description.md
Safe to proceed with risky changes.
```
