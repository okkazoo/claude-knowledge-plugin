---
name: wip
description: Autonomous work-in-progress capture or quick fact save. Auto-detects if input is a fact or topic name.
allowed-tools: Read, Write, Bash, Grep, Glob
argument-hint: [text] | -list | -f <fact>
model: sonnet
---

# Work In Progress Capture

## Usage

- `/knowledge-base:wip` - Auto-categorize and save progress based on conversation
- `/knowledge-base:wip <text>` - AI detects if text is a fact or topic name
- `/knowledge-base:wip -f <text>` - Save a fact directly
- `/knowledge-base:wip -list` - List existing journey topics

## Instructions

### First: Ensure Knowledge Base Exists

```bash
if [ ! -d ".claude/knowledge" ]; then
  echo "Knowledge base not initialized. Run /knowledge-base:init first."
  exit 1
fi
```

### No Arguments (Autonomous Mode)

1. Analyze the current conversation to determine what work was done
2. Create or append to an appropriate journey folder
3. Save progress with context, code changes, and TODOs

### With Text Argument (-f flag)

Save a fact directly:
```bash
python .claude/knowledge/journey/_wip_helpers.py save_fact "<text>"
```

### -list Argument

```bash
ls -la .claude/knowledge/journey/
```

Show existing journeys and suggest which might be relevant.

## Journey File Structure

Entries go in: `.claude/knowledge/journey/<category>/<topic>/YYYY-MM-DD-HH-MM-<slug>.md`

```markdown
# WIP: <Brief Title>

## Date: YYYY-MM-DD HH:MM
## Session Context
[What we were working on]

## Progress Made
- [Change 1]
- [Change 2]

## Code Changes
```[language]
[key snippets]
```

## Still TODO
- [ ] [Pending item 1]

## Files Modified
- path/to/file1.py
```
