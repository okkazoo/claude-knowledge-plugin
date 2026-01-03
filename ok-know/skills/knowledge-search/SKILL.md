---
name: knowledge-search
description: Search project knowledge base for journeys, memory (facts/learnings), patterns, and anti-patterns. Use when you need project-specific context about how things work, why decisions were made, or what not to do.
allowed-tools: Read, Grep, Bash
model: sonnet
---

# Knowledge Search

## CRITICAL: Always Search First

**BEFORE tackling any problem or suggesting an approach, ALWAYS search the knowledge base first.**

The PreToolUse hook automatically displays relevant patterns before your Grep/Glob searches.

This is not optional - it prevents:
- Repeating mistakes already documented
- Missing known solutions
- Ignoring established patterns
- Wasting time on approaches that don't work

## When This Skill Activates

- **ALWAYS before starting work** on any problem
- You need project-specific information
- Looking for "how do we do X"
- Checking for past solutions or patterns
- Before suggesting an approach (check anti-patterns)
- After an error (check completed journeys)

## Knowledge Structure

```
.claude/knowledge/
├── knowledge.json    # Pattern + keyword index (auto-searched by hooks)
├── facts/            # Quick facts and learnings (.wip -f)
│   └── *.md          # Individual fact entries
├── journey/          # Development journeys
│   └── <category>/   # Journey categories
│       └── <topic>/  # Journey topics
│           ├── _meta.md  # Keywords, timestamps
│           └── *.md      # Progress entries
├── patterns/         # How-to guides
└── savepoints/       # Saved states
```

## How to Search

### Step 1: Check knowledge.json (Auto-handled by hooks)

The PreToolUse hook automatically checks `knowledge.json` before your Grep/Glob searches and displays relevant patterns. You can also manually check:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/_wip_helpers.py" search_patterns "your query"
```

Patterns are indexed by keywords and context:
```json
{
  "pattern": "Use relative paths for file tools",
  "type": "gotcha",
  "context": "windows, paths, race-condition"
}
```

### Step 2: Find Relevant Entries

Search for keywords matching the current task.
Look in multiple sections:
- Journeys (ongoing work-in-progress, searchable library)
- Facts (quick facts and learnings in `facts/` folder)
- Patterns (in `knowledge.json`)
- Anti-patterns

### Step 3: Check Journey Entries

For journeys, check `_meta.md` for context:
```bash
cat .claude/knowledge/journey/<category>/<topic>/_meta.md
```

Then check the latest entry files for current state.

### Step 4: Read the Relevant Files

Read the files found in knowledge.json or journey folders:
```bash
cat .claude/knowledge/facts/2024-01-16-git-bash-paths.md
cat .claude/knowledge/journey/docker/docker-issues/2024-01-16-progress.md
```

**Only read the specific files relevant to your task.**

## Search Priority

1. **knowledge.json patterns** - Auto-displayed by PreToolUse hook
2. **facts/** - Quick facts and gotchas
3. **journey/** - Ongoing work entries, searchable reference library
4. **patterns/** - How-to guides

## Usage Examples

### Before Starting Any Task

```
User: "Let's add async downloads"

1. FIRST: Search knowledge.json patterns or grep for "async", "download"
2. Find: "aiohttp fails on large files -> journey/..."
3. Read the referenced files
4. Say: "Before we go async, I found in our knowledge base
        that we tried aiohttp before and hit timeout issues..."
```

### After Getting an Error

```
Error: Connection reset during file transfer

1. Search knowledge.json patterns or grep for "connection reset", "file transfer"
2. Find relevant journey entry or fact
3. Apply known solution
```

### Looking for Patterns

```
User: "How should I structure this API endpoint?"

1. Search knowledge.json patterns or grep for "API", "endpoint"
2. Find: "API patterns -> patterns/api-conventions.md"
3. Read the referenced file
4. Apply project conventions
```

## Remember

- **PreToolUse hook shows patterns automatically** - pay attention to the hints before searches
- Read relevant facts and journey entries when needed
- Anti-patterns are as valuable as patterns
- Journeys stay active as a searchable library
- Facts folder contains quick facts and learnings
