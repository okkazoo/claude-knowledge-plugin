---
name: wip
description: Save work-in-progress or facts. Use -f/-fact for gotchas/learnings, or no args for autonomous journey detection with multi-topic support.
allowed-tools: Read, Write, Bash, Grep, Glob, AskUserQuestion
argument-hint: -[f]act <text>
model: sonnet
---

# Work In Progress Capture

## CRITICAL: Context Analysis

**IMPORTANT**: Always analyze the ENTIRE conversation context, not just recent messages.
This includes any compacted/summarized content from earlier in the session.
The goal is to capture the complete journey to prevent repeating mistakes.

## Argument Detection

**Check what argument was provided:**

1. **`-f <text>` or `-fact <text>`** → Go to "Fact Flag" section (direct save to facts/)
2. **No argument / empty / just "wip"** → Go to "No Arguments (Autonomous Mode)" section

---

## Usage

```
wip -f <text>        Save fact/gotcha directly to knowledge/facts/
wip -fact <text>     Same as -f

wip                  Autonomous mode - analyzes FULL conversation context
                     - Detects all topics discussed (even across compacted context)
                     - Presents clickable options to select which to save
                     - Supports multi-select for saving multiple items at once
```

---

## Fact Flag (`-f` or `-fact`)

**Direct save to `knowledge/facts/` - no AI detection needed.**

### Usage
- `wip -f On Windows use python not python3`
- `wip -fact API rate limit is 100 requests per minute`

### Instructions

1. **Extract the text** after `-f` or `-fact`

2. **Duplicate Check** (quick dupe-check before saving):
   ```bash
   python .claude/knowledge/journey/_wip_helpers.py find_similar_facts "<text>"
   ```

   **If similar facts found (count > 0):**
   - Display the similar facts to the user
   - Use AskUserQuestion:
     ```json
     {
       "questions": [{
         "question": "Similar fact(s) already exist. What would you like to do?",
         "header": "Duplicate?",
         "multiSelect": false,
         "options": [
           {"label": "Save anyway", "description": "Create new fact (may be redundant)"},
           {"label": "Update existing", "description": "Replace the most similar fact with this one"},
           {"label": "Cancel", "description": "Don't save - existing fact is sufficient"}
         ]
       }]
     }
     ```
   - If "Save anyway" → continue to step 3
   - If "Update existing" → delete the most similar fact file, then continue to step 3
   - If "Cancel" → exit without saving

3. **Create fact file** (use stdin to avoid shell escaping issues):
   ```bash
   echo '{"text": "<text>"}' | python .claude/knowledge/journey/_wip_helpers.py save_fact_stdin
   ```

   Note: Escape any quotes in `<text>` for JSON (e.g., `\"` for literal quotes).

   This creates: `.claude/knowledge/facts/YYYY-MM-DD-<slug>.md`

   File format:
   ```markdown
   # Fact: <brief preview>

   ## Date: YYYY-MM-DD HH:MM

   <full fact text>
   ```

4. **Confirm to user:**
   ```
   Saved to facts/YYYY-MM-DD-<slug>.md
   ```

---

## No Arguments (Autonomous Mode)

**Analyzes the ENTIRE conversation (including compacted context) and detects all topics.**

### Step 1: Analyze Full Conversation Context

**CRITICAL**: Analyze the ENTIRE conversation, not just recent messages.
This includes any compacted/summarized content visible in your context.

Scan for:

**Facts** (standalone learnings):
- Gotchas discovered ("X doesn't work because Y")
- Rules learned ("Always use X", "Never do Y")
- Configuration values, platform-specific behaviors

**Journey topics** (work-in-progress areas):
- Features being implemented
- Bugs being investigated/fixed
- Refactoring efforts
- Any distinct area of work

### Step 2: Detect All Topics

Identify ALL distinct topics/work areas from the full conversation.

A "topic" is a separable piece of work that could be its own journey entry.
Look for topic boundaries like:
- Switching from one feature to another
- Moving from bug X to bug Y
- Different areas of the codebase
- Distinct problem domains

### Step 3: Display Items and Present Options

**First, display detected items as formatted text:**

```
Analyzing full conversation...

FACTS
----------------------------------
[F1] API rate limit is 100 req/min
[F2] Windows needs Python313 in PATH first


JOURNEYS
----------------------------------
[J1] wip-command-ui-improvements
     Removed -j flag, added AskUserQuestion

[J2] hook-error-debugging
     Debugged PreToolUse:Grep hook error
```

**Then, use AskUserQuestion for selection:**

```json
{
  "questions": [{
    "question": "Type F1,J2 in Other to select specific items:",
    "header": "Save WIP",
    "multiSelect": false,
    "options": [
      {"label": "Save ALL", "description": "Save all 2 facts and 2 journeys"},
      {"label": "Cancel", "description": "Exit without saving"}
    ]
  }]
}
```

**Handling responses:**
- User selects "Save ALL" → Save all detected items
- User selects "Cancel" → Exit without saving
- User selects "Other" and types `F1,J2` → Save only those items
- User selects "Other" and types `all` → Save all items

**Edge cases:**

**Single item detected:** Use confirmation-style question:
```json
{
  "questions": [{
    "question": "Save this entry?",
    "header": "Save WIP",
    "multiSelect": false,
    "options": [
      {"label": "Yes, save it", "description": "<item-type>: <brief summary>"},
      {"label": "No, cancel", "description": "Exit without saving"}
    ]
  }]
}
```

**Only facts OR only journeys:** Skip the empty section header, just show what exists.

### Step 4: For Each Selected Topic

For each journey topic selected:

1. **Find existing categories** (to choose appropriate one):
   ```bash
   python .claude/knowledge/journey/_wip_helpers.py scan_categories
   ```

2. **Extract content for THIS topic** from full conversation:
   - What was tried (including failures)
   - What worked
   - Mistakes made and lessons learned
   - Current state
   - What's still pending
   - Key code changes
   - Open questions

3. **Build the entry content** following this template:

   ```markdown
   # WIP: <Brief Title>

   ## Date: YYYY-MM-DD HH:MM

   ## What Was Tried
   - [Approach 1] - [result: worked/failed] - [why]
   - [Approach 2] - [result: worked/failed] - [why]

   ## Mistakes & Learnings
   - [What went wrong] → [Lesson learned]
   - [Another mistake] → [What to do instead]

   ## Progress Made
   - [x] [Completed item 1]
   - [x] [Completed item 2]

   ## Current State
   [Where things stand now]

   ## Still TODO
   - [ ] [Pending item 1]
   - [ ] [Pending item 2]

   ### Solutions Found
   - **[Pattern that worked]** - context: keyword1, keyword2, keyword3

   ### Tried But Failed
   - **[What didn't work]** - Failed because: [reason] - context: keyword1, keyword2

   ### Gotchas
   - **[Unexpected issue discovered]** - context: keyword1, keyword2

   ### Best Practices
   - **[Practice to follow]** - context: keyword1, keyword2

   ## Code Changes
   ```[language]
   [key snippets - especially patterns that worked or failed]
   ```

   ## Files Modified
   - path/to/file1.py
   - path/to/file2.jsx
   ```

4. **Create the entry using the helper** (use stdin to avoid shell escaping issues):
   ```bash
   echo '{"category": "<category>", "topic": "<topic>", "content": "<content>"}' | python .claude/knowledge/journey/_wip_helpers.py create_entry_stdin
   ```

   Note: Escape any quotes in values for JSON (e.g., `\"` for literal quotes).

   Returns JSON with: `success`, `file`, `category`, `topic`, `patterns_indexed`

### Step 5: Show Summary

After saving all selected items:

```
Saved:

  [F1] Fact: "On Windows use python not python3"
        → facts/2024-12-21-windows-python.md

  [1] auth-token-refresh
        → authentication/token-refresh/2024-12-21-15-30-oauth-cookies.md
        Key learnings: JWT failed (CORS), HTTP-only cookies work

  [2] database-migration
        → infrastructure/database-migration/2024-12-21-15-30-user-prefs.md

Total: 1 fact, 2 journeys saved
```

---

## Examples

### Direct Fact Save
```
User: wip -f On Windows use python not python3 in shebangs

Claude:
Saved to facts/2024-12-21-windows-python-shebang.md

Total facts: 1
```

### Autonomous Mode Example
```
User: wip

Claude:
Analyzing full conversation...

FACTS
----------------------------------
[F1] API rate limit is 100 req/min


JOURNEYS
----------------------------------
[J1] auth-token-refresh
     OAuth token refresh. Tried JWT (failed - CORS), switched to cookies.

[J2] database-migration
     Added user_preferences table. Pending: backfill.

[AskUserQuestion appears]
User selects: Save ALL

Saved:

[F1] API rate limit is 100 req/min
  → facts/2024-12-21-api-rate-limit.md

[J1] auth-token-refresh
  → authentication/token-refresh/2024-12-21-15-30-oauth-cookies.md

[J2] database-migration
  → infrastructure/database-migration/2024-12-21-15-30-user-prefs.md

Total: 1 fact, 2 journeys saved
```

### Selecting Specific Items
```
User: wip

Claude:
Analyzing full conversation...

FACTS
----------------------------------
[F1] API rate limit is 100 req/min
[F2] Windows needs Python313 first in PATH


JOURNEYS
----------------------------------
[J1] wip-command-refactor
     Removed -j flag, added AskUserQuestion UI

[AskUserQuestion appears]
User selects: Other → types "F1,J1"

Saved:

[F1] API rate limit is 100 req/min
  → facts/2024-12-21-api-rate-limit.md

[J1] wip-command-refactor
  → wip-command-refactor/2024-12-21-15-30-askuserquestion-ui.md

Total: 1 fact, 1 journey saved
```
