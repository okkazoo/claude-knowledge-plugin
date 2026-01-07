---
name: context-manager
description: Handle large files and outputs efficiently. Summarizes data before it enters main context. Use when dealing with log files, large API responses, or bulk file reading.
allowed-tools:
  - Read
  - Bash
model: sonnet
context: fork
---

# Context Manager (Efficient Large Data Handling)

## When This Skill Activates

- Reading files larger than 500 lines
- Processing log files
- Handling large API responses
- Analyzing multiple files at once
- Any situation where raw data would bloat context

## Core Principle

**Process data in code, only show results.**

- Bad: Dump 1000 lines of logs into conversation
- Good: "Found 3 errors in 1000 log entries: [summary]"

## Techniques

### 1. Summarize Before Reading

```python
# Instead of reading entire file:
with open('huge_log.txt') as f:
    content = f.read()  # 10MB into context

# Process and summarize:
errors = []
with open('huge_log.txt') as f:
    for line in f:
        if 'ERROR' in line:
            errors.append(line.strip())
print(f"Found {len(errors)} errors:")
for e in errors[:5]:  # Show top 5 only
    print(f"  - {e[:100]}")  # ~500 bytes into context
```

### 2. Use Bash for Filtering

```bash
# Count and sample, don't dump
echo "=== Log Summary ==="
echo "Total lines: $(wc -l < logfile.log)"
echo "Errors: $(grep -c ERROR logfile.log)"
echo "Warnings: $(grep -c WARN logfile.log)"
echo ""
echo "=== Recent Errors ==="
grep ERROR logfile.log | tail -5
```

### 3. Delegate to Explore Agent

For multi-file analysis, use the built-in `Explore` agent via the Task tool:
```
Task(subagent_type="Explore", prompt="Find all error handling patterns in src/")
```
It reads in its own context and returns only synthesis.

## Output Guidelines

### For Log Files

```
## Log Analysis: [filename]

- Total entries: [N]
- Errors: [N]
- Warnings: [N]
- Time range: [start] to [end]

### Top Errors
1. [error type] - [count] occurrences
2. [error type] - [count] occurrences

### Sample Error
```
[single representative error message]
```

### Recommendation
[What action to take]
```

### For API Responses

```
## API Response: [endpoint]

- Status: [code]
- Items returned: [N]
- Relevant fields extracted: [list]

### Key Data
- [extracted field 1]: [value]
- [extracted field 2]: [value]

### Full response available at: [how to access if needed]
```

### For Multiple Files

```
## Analysis: [N] files in [directory]

### Files Examined
- [pattern matched]: [count] files

### Findings
1. [finding with file:line reference]
2. [finding with file:line reference]

### Details available
- `file1.py:10-20` - [what's there]
- `file2.py:30-40` - [what's there]
```

## Remember

- Your job is to REDUCE context, not add to it
- Process data with code when possible
- Return insights, not data dumps
- Reference line numbers for drill-down
- Use `Explore` agent (via Task tool) for multi-file operations
