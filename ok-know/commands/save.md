---
name: save
description: Save working state with auto-generated commit message from knowledge.
allowed-tools:
  - Read
  - Write
  - Bash
  - Grep
  - Glob
  - AskUserQuestion
argument-hint: [description]
model: sonnet
---

# Save

## When to Use

Before:
- Major refactoring
- Risky changes to core files
- Experimenting with something uncertain
- Any change affecting 3+ files

## Instructions

### 0. Check for Git Repository

First, verify this is a git repository:

```bash
git rev-parse --git-dir 2>/dev/null || echo "NOT_A_GIT_REPO"
```

If the output is `NOT_A_GIT_REPO`, use AskUserQuestion:
```json
{
  "questions": [{
    "question": "This directory is not a git repository. The /save command requires git. What would you like to do?",
    "header": "No Git Repo",
    "multiSelect": false,
    "options": [
      {"label": "Initialize git", "description": "Run 'git init' to create a repository here"},
      {"label": "Skip save", "description": "Cancel the save operation"}
    ]
  }]
}
```

- If "Initialize git": Run `git init` and continue with the save
- If "Skip save": End with message "Save cancelled - no git repository"

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
Parse git history for previously consumed knowledge:
```bash
git log --all --grep="Knowledge-used:" --format="%b" | grep "Knowledge-used:" | sed 's/Knowledge-used: //'
```
This extracts all knowledge files that have been embedded in previous commits.

#### Step 2d: Filter to unused knowledge
1. Get list of knowledge files from git history (Step 2c)
2. **Verify each file still exists** - if deleted, it can be reused
3. Only use knowledge files NOT in the consumed list

#### Step 2e: Generate message
Read the unused knowledge files and summarize what was accomplished:
- Focus on the "what" and "why" from journey progress
- Keep it concise (1-2 sentences)
- Format: `[summary from knowledge]`

If no unused knowledge found, fall back to: `work in progress on [changed-files]`

### 3. Create Save Point File

Save to: `.claude/knowledge/savepoints/YYYY-MM-DD-HH-MM-[description-slug].md`

```markdown
# Save: [Description]

## Date: YYYY-MM-DD HH:MM
## Git Branch: [branch name]
## Git Commit: [short hash]

## Description
[User's description or auto-generated from knowledge]

## Knowledge Used
- [list of knowledge files used to generate this message]

## State at Save

### Modified Files
- [file1.py]
- [file2.jsx]

### Recent Changes
[Summary of what was done before save]

### Git Diff Summary
```
[output of git diff --stat]
```

## To Restore

If things break after this save:

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

### 4. Stage and Commit

Use AskUserQuestion:
```json
{
  "questions": [{
    "question": "Commit current changes?",
    "header": "Commit",
    "multiSelect": false,
    "options": [
      {"label": "Yes", "description": "Stage and commit all changes"},
      {"label": "No", "description": "Skip commit, just save the file"}
    ]
  }]
}
```

If Yes, commit with knowledge embedded in message:
```bash
git add -A
git commit -m "[description]

[optional longer description]

Knowledge-used: [comma-separated list of knowledge file paths]"
```

**Example commit message:**
```
Implemented JWT auth with refresh tokens

Added token refresh logic and fixed session expiry bug.

Knowledge-used: journey/2026-01-02-auth-flow.md, facts/jwt-refresh-gotcha.md
```

The `Knowledge-used:` line is parsed by future saves to avoid reusing the same knowledge.

### 5. Confirm

```
Saved: [description]

File: .claude/knowledge/savepoints/YYYY-MM-DD-HH-MM-description.md
Git: [committed/not committed]
Commit: [hash if committed]
Knowledge used: [count] files

Safe to proceed with risky changes.
```

## Quick Usage

```
save                        # Auto-generates message from knowledge
save before auth refactor   # Uses provided description
```

## Listing Save Points

```bash
ls -lt .claude/knowledge/savepoints/*.md | head -10
```

## Restoring

Use git to restore:
```bash
# See what changed since save
git diff [save-commit]..HEAD

# Hard restore
git checkout [save-commit] -- .
```

Or use Claude's `/rewind` command to go back in conversation history.
