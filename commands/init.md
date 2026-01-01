---
name: init
description: Initialize knowledge base structure and CLAUDE.md in current project
allowed-tools: Bash, Write, Read
argument-hint: (no arguments)
---

# Initialize Knowledge Base

Sets up the `.claude/knowledge/` directory structure and CLAUDE.md for persistent project knowledge.

## Instructions

### 1. Create Directory Structure

```bash
mkdir -p .claude/knowledge/journey .claude/knowledge/facts .claude/knowledge/patterns .claude/knowledge/checkpoints .claude/knowledge/versions
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

### 3. Create Helper Script

**CRITICAL:** Read the `_wip_helpers.py` from THIS PLUGIN's `scripts/` directory and write it to `.claude/knowledge/journey/_wip_helpers.py`.

The plugin's script location is: `<plugin-dir>/scripts/_wip_helpers.py`

This script (~2700 lines) provides essential CLI commands:
- `scan_categories` - List journey categories
- `save_fact` - Save a fact file
- `find_similar_facts` - Check for duplicates before saving
- `create_entry` - Create journey entry with auto-timestamp
- `knowledge_status` - Show knowledge base status
- `search_patterns` - Search indexed patterns
- `reset_knowledge` - Reset to factory defaults
- ... and 25+ more utilities

**You MUST copy the ENTIRE script.** Do not create a simplified version.

```bash
# Verify the script was created
[ -f ".claude/knowledge/journey/_wip_helpers.py" ] && echo "Helper script installed" || echo "ERROR: Helper script missing"
```

### 4. Create or Augment CLAUDE.md

**Check if CLAUDE.md exists:**
```bash
[ -f "CLAUDE.md" ] && echo "exists" || echo "missing"
```

**If CLAUDE.md does NOT exist**, create it with this template:

```markdown
# Project: [Project Name]

> **Bootstrap Manifest** - Claude reads this first every session.
> Keep concise. Details live in .claude/knowledge/ and are loaded on-demand.

## Project Overview

**Purpose:** [Brief description of what this project does]

**Stack:** [Your tech stack]

**Status:** [Development stage]

## Quick Reference

| Area | Location | Notes |
|------|----------|-------|
| Source | `/src/` | Main application code |
| Tests | `/tests/` | Test suite |
| Config | `.env` | Never commit secrets |

## Available Tools

### Built-in Agents (via Task tool)

| Agent | Use When |
|-------|----------|
| `Explore` | Codebase exploration, finding patterns, "how does X work?" |
| `Plan` | Implementation planning, architecture design |
| `feature-dev:code-architect` | Feature architecture, design decisions |
| `feature-dev:code-explorer` | Tracing execution paths, mapping dependencies |
| `feature-dev:code-reviewer` | Code review, finding bugs/issues |
| `general-purpose` | Multi-step tasks with full tool access |

### Skills (Auto-invoked)

| Skill | Triggers When |
|-------|---------------|
| `context-manager` | Large files or outputs detected |
| `code-patterns` | Writing new code |
| `knowledge-search` | Looking for project-specific patterns/solutions |

### Hooks (Automatic)

| Hook | Triggers |
|------|----------|
| `session-start` | On startup - injects git status, knowledge stats |
| `pre-search` | Before Grep/Glob - shows patterns first |
| `pre-read` | Before Read - warns on large files |
| `auto-index` | After Edit/Write - updates indexes |

### Commands (User-triggered)

| Command | Purpose |
|---------|---------|
| `/ok:wip` | Save work-in-progress with auto-extracted patterns |
| `/ok:wip -f <text>` | Save a fact/gotcha directly |
| `/ok:checkpoint [desc]` | Save state, auto-bump VERSION |
| `/ok:knowledge` | Show knowledge base status |
| `/ok:version -patch\|-minor\|-major` | Bump version and changelog |

## Knowledge Base

**CRITICAL: Pre-search hook shows patterns BEFORE you try solutions.**

When you Grep/Glob, the hook automatically shows:
1. **PATTERNS** - Solutions, tried-failed, gotchas (check these FIRST!)
2. Code refs - Function/class locations
3. Knowledge - Journeys and facts

### Pattern Types

| Type | Meaning |
|------|---------|
| solution | What worked - USE THIS |
| tried-failed | What didn't work - DON'T REPEAT |
| gotcha | Trap to avoid |
| best-practice | Recommended approach |

### Workflow

1. **Before trying anything** - Search for related patterns
2. **Check tried-failed** - Don't repeat documented failures
3. **Use solutions** - Apply what already worked
4. **After solving** - `/ok:wip` captures patterns automatically

## Project-Specific Notes

### Development Environment
```bash
# Add your setup instructions here
```

### Architecture Principles
[Document your key architecture decisions]

### Known Gotchas
[Document common pitfalls]

---
*Initialized with ok plugin*
```

**If CLAUDE.md already exists**, check if it has a Knowledge Base section:

```bash
grep -q "Knowledge Base" CLAUDE.md && echo "has-kb" || echo "no-kb"
```

If no Knowledge Base section, append this to the existing CLAUDE.md:

```markdown

---

## Knowledge Base (ok plugin)

Project uses the `ok` knowledge management plugin.

### Commands

| Command | Purpose |
|---------|---------|
| `/ok:wip` | Save work-in-progress with auto-extracted patterns |
| `/ok:wip -f <text>` | Save a fact/gotcha directly |
| `/ok:checkpoint [desc]` | Save state, auto-bump VERSION |
| `/ok:knowledge` | Show knowledge base status |

### Hooks

- `pre-search` shows relevant patterns before Grep/Glob searches
- `session-start` injects context on startup
- `auto-index` updates indexes after file changes

### Pattern Workflow

1. Before trying anything - search for related patterns
2. Check tried-failed patterns - don't repeat failures
3. Use documented solutions
4. After solving - `/ok:wip` captures patterns
```

### 5. Create VERSION file if missing

```bash
[ -f "VERSION" ] || echo "0.1.0" > VERSION
```

### 6. Confirm

```
Knowledge base initialized!

Structure created:
  .claude/knowledge/
  ├── journey/      (work-in-progress entries)
  ├── facts/        (quick facts, gotchas)
  ├── patterns/     (extracted solutions)
  ├── checkpoints/  (state snapshots)
  └── versions/     (version history)

CLAUDE.md: [created/augmented/unchanged]
VERSION: [created at 0.1.0 / already exists at X.Y.Z]

Next steps:
  1. Review and customize CLAUDE.md for your project
  2. Use /ok:wip to save progress as you work
  3. Use /ok:checkpoint before risky changes
```
