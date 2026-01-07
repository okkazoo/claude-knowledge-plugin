---
name: knowledge
description: Show knowledge base status, recent entries, and project state.
allowed-tools:
  - Bash
  - AskUserQuestion
argument-hint: -audit  -reset
model: sonnet
context: fork
---

# Knowledge Base Status

## Arguments

- No argument: Show knowledge base status (tree view with details)
- `-audit`: Audit knowledge base for issues (redundant facts, consolidation opportunities, orphaned references)
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

**If argument is `-audit`:**
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/_wip_helpers.py" audit_knowledge
```
Display the audit report EXACTLY as returned, then if issues were found, use **AskUserQuestion** to ask if user wants to:
- **Fix automatically** - Merge redundant facts, consolidate journeys, clean orphaned refs
- **Show details** - Explain each issue in more detail
- **Cancel** - Take no action

---

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

Open knowledge status in a separate window to minimize context usage:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/_wip_helpers.py" knowledge_window
```

This opens a new terminal window with the knowledge status. Only respond with:
"Knowledge base opened in external window."

Do NOT summarize, interpret, or add any other commentary.

---

## Notes

- The Python script returns pre-formatted markdown output
- Archives are saved to `.claude/knowledge-archive-{timestamp}/`
- Factory defaults preserve folder structure but clear all content
