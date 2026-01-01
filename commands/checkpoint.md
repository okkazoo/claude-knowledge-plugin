---
name: checkpoint
description: Save working state, auto-bump VERSION based on consumed knowledge patterns, and update CHANGELOG.
allowed-tools: Read, Write, Bash, Grep, Glob, AskUserQuestion
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

### 1. Capture Current State

```bash
# Get git status
git status --short

# Get recent changes
git diff --stat HEAD~3..HEAD 2>/dev/null || echo "No recent commits"

# List modified files (uncommitted + staged)
git diff --name-only 2>/dev/null
git diff --cached --name-only 2>/dev/null
```

### 2. Auto-Generate Commit Message from Knowledge

If no description provided, generate from knowledge:

#### Step 2a: Get changed files
```bash
git diff --name-only
git diff --cached --name-only
```

#### Step 2b: Find relevant knowledge files
Search `.claude/knowledge/journey/` and `.claude/knowledge/facts/` for mentions of the changed files.

#### Step 2c: Check what's already been used
Read `.claude/knowledge/commit-history.md` to get list of already-consumed knowledge files.

#### Step 2d: Filter to unused knowledge (with existence check)
1. Parse knowledge files from commit-history.md
2. **Verify each file still exists** - if a file was deleted (e.g., via `.knowledge -audit`), ignore that entry
3. Only use knowledge files NOT in the valid (existing) consumed list

This ensures deleted knowledge files are treated as "not consumed" since they no longer exist.

#### Step 2e: Generate message
Read the unused knowledge files and summarize what was accomplished:
- Focus on the "what" and "why" from journey progress
- Keep it concise (1-2 sentences)
- Format: `checkpoint: [summary from knowledge]`

If no unused knowledge found, fall back to: `checkpoint: work in progress on [changed-files]`

### 3. Create Checkpoint File

Save to: `.claude/knowledge/checkpoints/YYYY-MM-DD-HH-MM-[description-slug].md`

```markdown
# Checkpoint: [Description]

## Date: YYYY-MM-DD HH:MM
## Git Branch: [branch name]
## Git Commit: [short hash]

## Description
[User's description or auto-generated from knowledge]

## Knowledge Used
- [list of knowledge files used to generate this message]

## Version Bump
- Previous: [old version]
- New: [new version]
- Type: [patch/minor/major] ([X] solutions, [Y] gotchas)

## State at Checkpoint

### Modified Files
- [file1.py]
- [file2.jsx]

### Recent Changes
[Summary of what was done before checkpoint]

### Git Diff Summary
```
[output of git diff --stat]
```

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

3. Or use Claude's /rewind command
```

### 4. Auto-Bump VERSION

Every checkpoint automatically bumps the VERSION file based on consumed knowledge patterns.

#### Step 4a: Read current version
```bash
cat VERSION 2>/dev/null || echo "0.0.0"
```
If no VERSION file exists, start at 0.1.0.

#### Step 4b: Scan patterns from consumed knowledge
Read `.claude/knowledge/knowledge.json` and find patterns from the knowledge files used in this checkpoint.

#### Step 4c: Infer bump type from pattern types

| Pattern Type | Version Bump |
|--------------|--------------|
| `solution` | minor (new feature) |
| `best-practice` | minor |
| `tried-failed` | patch (learned from failure) |
| `gotcha` | patch (bug/trap found) |
| Text contains "breaking", "removed", "deprecated" | major |

Priority: major > minor > patch

If no patterns found, default to **patch**.

#### Step 4d: Calculate new version
- `-patch`: X.Y.Z -> X.Y.(Z+1)
- `-minor`: X.Y.Z -> X.(Y+1).0
- `-major`: X.Y.Z -> (X+1).0.0

#### Step 4e: Update VERSION file
```bash
echo "0.2.0" > VERSION
```

#### Step 4f: Update CHANGELOG.md

Ensure `.claude/knowledge/versions/CHANGELOG.md` exists:
```bash
mkdir -p .claude/knowledge/versions
```

If new file, create header:
```markdown
# Changelog

All notable changes to this project.

Format based on [Keep a Changelog](https://keepachangelog.com/).

```

Prepend new version entry (newest at top, after header).
Auto-generate categories from consumed patterns:

```markdown
## [0.2.0] - YYYY-MM-DD

### Added
- [Pattern descriptions from solution/best-practice patterns]

### Fixed
- [Pattern descriptions from tried-failed/gotcha patterns]
```

#### Step 4g: Update checkpoint file with version info

Add to checkpoint file:
```markdown
## Version Bump
- Previous: 0.1.0
- New: 0.2.0
- Type: minor (3 solutions consumed)
```

### 5. Optionally Stage/Commit

Use AskUserQuestion:
```json
{
  "questions": [{
    "question": "Commit current changes? This creates a git checkpoint you can revert to.",
    "header": "Commit",
    "multiSelect": false,
    "options": [
      {"label": "Yes", "description": "Stage and commit all changes"},
      {"label": "No", "description": "Skip commit, just save checkpoint file"}
    ]
  }]
}
```

If Yes:
```bash
git add -A
git commit -m "checkpoint: [description]"
```

### 6. Record Knowledge Usage

After successful commit, append to `.claude/knowledge/commit-history.md`:

```markdown
## [short-hash] (YYYY-MM-DD HH:MM)
**Message:** [commit message]
**Version:** 0.1.0 -> 0.2.0 (minor)
**Files changed:** [list]
**Knowledge used:**
- [knowledge-file-1.md]
- [knowledge-file-2.md]
```

Create the file if it doesn't exist with header:
```markdown
# Commit History - Knowledge Usage

Tracks which knowledge files have been used to generate commit messages.
This prevents reusing the same knowledge for multiple commits.

---
```

### 7. Confirm

```
Checkpoint saved: [description]

File: .claude/knowledge/checkpoints/YYYY-MM-DD-HH-MM-description.md
Version: 0.1.0 -> 0.2.0 (minor)
Git: [committed/not committed]
Commit: [hash if committed]
Knowledge used: [count] files
Patterns: [X solutions, Y gotchas]

Safe to proceed with risky changes.
If things break, we can restore from this point.
```

## Quick Usage

```
checkpoint                        # Auto-generates message from knowledge
checkpoint before auth refactor   # Uses provided description
```

## Listing Checkpoints

```bash
ls -lt .claude/knowledge/checkpoints/*.md | head -10
```

## Restoring

Use git to restore:
```bash
# See what changed since checkpoint
git diff [checkpoint-commit]..HEAD

# Hard restore
git checkout [checkpoint-commit] -- .
```

Or use Claude's `/rewind` command to go back in conversation history.
