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

If the description is unclear or could go multiple directions, ask follow-up questions about the **goal and use case** - NOT about technical choices.

**Good questions (about what they want):**
- "How will people use this - through a browser, command line, or something else?"
- "Is this for just you, or will others use it too?"
- "Does it need to remember data between uses?"
- "Will it need to connect to any external services?"
- "Should it run continuously or just when triggered?"

**Bad questions (technical - don't ask these):**
- "Should we use Flask or FastAPI?"
- "Do you want REST or GraphQL?"
- "Should we use SQLite or PostgreSQL?"
- "What testing framework do you prefer?"

**When to ask follow-ups:**
- Description is very short (under 10 words)
- Multiple very different implementations could fit
- Key usage pattern is unclear

**When NOT to ask follow-ups:**
- Description is clear and specific
- User mentioned how it will be used
- Only one reasonable implementation approach

Limit to 3 follow-up questions maximum.

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

How will you use this - through a browser, command line, or desktop app?
User: Command line, I want to organize photos into folders by date

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
