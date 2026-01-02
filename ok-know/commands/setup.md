---
name: setup
description: Bootstrap a new project by filling in CLAUDE.md template
allowed-tools: Read, Write, Grep, Glob, Bash, AskUserQuestion
argument-hint: (no arguments)
model: sonnet
---

# Project Setup - Auto-fill CLAUDE.md Template

Bootstrap a new project by understanding what the user wants to build.

## Instructions

### Step 1: Validate CLAUDE.md Exists

```bash
if [ ! -f "CLAUDE.md" ]; then
  echo "No CLAUDE.md found"
  exit 1
fi
```

If not found, stop with error message.

### Step 2: Ask About Their Project

Ask the user:

```
Describe what you are creating:
```

### Step 3: Ask Clarifying Questions (If Needed)

If the description is unclear or could go multiple directions, use **AskUserQuestion** to gather details about goals and use cases - NOT technical choices.

**When to ask follow-ups:**
- Description is very short (under 10 words)
- Multiple very different implementations could fit
- Key usage pattern is unclear

**When NOT to ask follow-ups:**
- Description is clear and specific
- User mentioned how it will be used
- Only one reasonable implementation approach

**Use AskUserQuestion with relevant questions from this set:**

```json
{
  "questions": [
    {
      "question": "How will people use this?",
      "header": "Interface",
      "multiSelect": false,
      "options": [
        {"label": "Browser/Web", "description": "Access through a web browser"},
        {"label": "Command line", "description": "Run from terminal/shell"},
        {"label": "API", "description": "Other programs will call it"},
        {"label": "Desktop app", "description": "Native application with GUI"}
      ]
    },
    {
      "question": "Who is this for?",
      "header": "Audience",
      "multiSelect": false,
      "options": [
        {"label": "Just me", "description": "Personal tool, minimal polish needed"},
        {"label": "My team", "description": "Shared tool, needs docs and error handling"},
        {"label": "Public users", "description": "Production quality, robust error handling"}
      ]
    },
    {
      "question": "Does it need to save/remember data?",
      "header": "Persistence",
      "multiSelect": false,
      "options": [
        {"label": "No", "description": "Stateless, processes and exits"},
        {"label": "Yes, simple", "description": "Files or simple database"},
        {"label": "Yes, complex", "description": "Relational data, queries, multiple tables"}
      ]
    },
    {
      "question": "How should it run?",
      "header": "Run mode",
      "multiSelect": false,
      "options": [
        {"label": "On-demand", "description": "Run when triggered, then exit"},
        {"label": "Always running", "description": "Background service/daemon"},
        {"label": "Scheduled", "description": "Runs periodically (cron, task scheduler)"}
      ]
    }
  ]
}
```

**Only ask questions that are unclear from the description.** Skip questions where the answer is obvious. Maximum 3 questions.

### Step 4: Auto-Detect Existing Setup

Scan silently (don't show output):

```bash
# Dependencies
[ -f "requirements.txt" ] && cat requirements.txt | grep -v "^#" | grep -v "^$"
[ -f "pyproject.toml" ] && grep -A 20 "dependencies" pyproject.toml

# Python version
python --version 2>/dev/null || python3 --version 2>/dev/null

# Directories
find . -maxdepth 2 -type d | grep -v "^\./\." | grep -v "__pycache__" | grep -v "venv"

# Git status
[ -d ".git" ] && echo "has git"
```

### Step 5: Infer Technical Stack

Based on user's answers (NOT by asking), determine:

| User Says | Infer |
|-----------|-------|
| "browser", "web page", "website" | Web app (Flask/FastAPI) |
| "command line", "terminal", "script" | CLI tool |
| "API", "other apps will call it" | REST API (FastAPI) |
| "convert", "process files" | Script/CLI |
| "runs in background", "always on" | Service/daemon |
| "just for me", "local" | Simple script, minimal deps |
| "others will use", "team" | Better error handling, docs |
| "remember data", "save", "store" | Database (SQLite for simple, Postgres for complex) |
| "Windows right-click", "context menu" | Windows shell integration |

**Project Name:**
- Extract from description or use directory name
- Convert to title case

### Step 6: Fill CLAUDE.md

Replace all placeholders with inferred values:

| Section | Fill With |
|---------|-----------|
| Project Name | Inferred name |
| Purpose | User's description (cleaned up) |
| Stack | Inferred from answers + detected deps |
| Status | From git (New/Initializing/In Development) |
| Quick Reference | Detected + expected directories |
| Development Environment | Based on detected/expected setup |
| Architecture Principles | Based on project type |
| Testing Requirements | pytest (default) |
| Known Gotchas | Relevant to the project type |
| Last Updated | Current date |

Add initialization timestamp after Status.

### Step 7: Show Summary

```
Project configured!

  Name: [Name]
  Purpose: [Description]
  Stack: [Inferred stack]
  Status: [Git status]

  Setup for: [brief explanation of what was configured and why]

  Review CLAUDE.md to customize further.
```

## Examples

### Example: Vague Description
```
User: setup

Describe what you are creating:
User: A tool to manage my photos

[Needs clarification - could be CLI, web app, or desktop app]

[AskUserQuestion appears with "How will people use this?" options]
User selects: Command line

[Now clear - CLI tool for file organization]

Project configured!

  Name: Photo Manager
  Purpose: CLI tool to organize photos into folders by date
  Stack: Python 3.12, Click (CLI)
  Status: New

  Setup for: Command-line tool with file system operations
```

### Example: Clear Description
```
User: setup

Describe what you are creating:
User: Windows right-click context menu to convert images between formats like PNG to JPG

[Clear enough - no follow-up needed]

Project configured!

  Name: Image Converter
  Purpose: Windows right-click context menu to convert images between formats
  Stack: Python 3.12, Pillow, Windows Registry
  Status: New

  Setup for: Windows shell integration with image processing
```

## Notes

- Ask about goals, not implementation
- Maximum 3 follow-up questions
- Make all technical decisions yourself
- If CLAUDE.md already configured, overwrite silently
- Keep everything concise
