---
name: knowledge
description: Show knowledge base status, recent entries, and project state.
allowed-tools: Bash, AskUserQuestion
argument-hint: -reset
model: haiku
---

# Knowledge Base Status

## Arguments

- No argument: Show knowledge base status (tree view with details)
- `-reset`: Reset knowledge base to factory defaults (with options)

## Instructions

### First: Ensure Knowledge Base Exists

```bash
if [ ! -d ".claude/knowledge" ]; then
  echo "Knowledge base not initialized. Run /ok-know:install first."
  exit 1
fi
```

### Check argument and run appropriate command

**If argument is `-reset`:**

1. First, show what will be affected (dry run):
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/_wip_helpers.py" reset_knowledge
```

2. Use **AskUserQuestion** tool to ask the user which option they want:
   - **Archive & Reset** - Save current knowledge to timestamped archive, then reset
   - **Full Reset** - Delete all knowledge permanently (cannot be undone)
   - **Cancel** - Abort reset, keep everything

3. Based on user's choice, run the appropriate command.

---

**Otherwise (no argument):**
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/_wip_helpers.py" knowledge_status
```
**IMPORTANT**: Display the command output EXACTLY as returned. Do NOT summarize, interpret, or add any commentary. Just show the raw output with its formatting preserved. The output already contains properly formatted status information.

---

## Notes

- The Python script returns pre-formatted markdown output
- Archives are saved to `.claude/knowledge-archive-{timestamp}/`
- Factory defaults preserve folder structure but clear all content
