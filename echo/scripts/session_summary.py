#!/usr/bin/env python3
"""
session_summary.py - Generates session summary on Stop hook

Combines current tasks with today's file changes to create a
human-readable summary prepended to the index file.
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Set

from config import get_worklog_dir, log_verbose


def get_logs_dir() -> Path:
    """Get the logs subdirectory."""
    return get_worklog_dir() / "logs"


def load_current_tasks(worklog_dir: Path) -> List[Dict[str, Any]]:
    """Load tasks from .current_tasks file."""
    tasks_file = worklog_dir / ".current_tasks"
    tasks = []

    if tasks_file.exists():
        with open(tasks_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        tasks.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    return tasks


def load_todays_edits(logs_dir: Path) -> List[Dict[str, Any]]:
    """Load today's edits from the daily log file."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = logs_dir / f"{today}.jsonl"
    edits = []

    if log_file.exists():
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        edits.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    return edits


def load_processed_entries(worklog_dir: Path) -> set:
    """Load set of already processed entry timestamps."""
    processed_file = worklog_dir / ".processed"
    processed = set()

    if processed_file.exists():
        with open(processed_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    processed.add(line)

    return processed


def save_processed_entries(worklog_dir: Path, processed: set):
    """Save processed entry timestamps."""
    processed_file = worklog_dir / ".processed"
    with open(processed_file, "w", encoding="utf-8") as f:
        for ts in sorted(processed):
            f.write(ts + "\n")


def generate_summary(tasks: List[Dict], edits: List[Dict], processed: set) -> tuple:
    """Generate markdown summary from tasks and edits, skipping already processed."""
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M")

    # Filter out already processed entries
    new_tasks = [t for t in tasks if t.get("ts") not in processed]
    new_edits = [e for e in edits if e.get("ts") not in processed]

    # If nothing new to report, return empty
    if not new_tasks and not new_edits:
        return "", set()

    lines = [f"## {timestamp}"]

    # Add task prompts
    if new_tasks:
        # Use the most recent task as the main task description
        main_task = new_tasks[-1].get("prompt", "")
        if len(main_task) > 100:
            main_task = main_task[:100] + "..."
        lines.append(f"**Task**: {main_task}")

    # Group edits by operation type (use sets to deduplicate)
    created = set()
    modified = set()

    for edit in new_edits:
        file_path = edit.get("file_path", "")
        operation = edit.get("operation", "modified")

        # Make path relative if possible
        try:
            project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
            rel_path = os.path.relpath(file_path, project_dir)
            if not rel_path.startswith(".."):
                file_path = rel_path
        except ValueError:
            pass

        if operation == "created":
            created.add(file_path)
        else:
            modified.add(file_path)

    # Add file changes (sorted for consistent output)
    for item in sorted(created):
        lines.append(f"- **Created**: `{item}`")

    for item in sorted(modified):
        lines.append(f"- **Modified**: `{item}`")

    lines.append("")  # Blank line after entry

    # Track which entries we've now processed
    newly_processed = set()
    for t in new_tasks:
        newly_processed.add(t.get("ts", ""))
    for e in new_edits:
        newly_processed.add(e.get("ts", ""))

    return "\n".join(lines), newly_processed


def prepend_to_index(worklog_dir: Path, summary: str):
    """Prepend summary to index.md, creating if needed."""
    index_file = worklog_dir / "index.md"

    existing_content = ""
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            existing_content = f.read()

    # Add header if new file
    if not existing_content.strip():
        header = "# Worklog\n\nAutomatically generated activity log.\n\n"
        new_content = header + summary
    else:
        # Find where to insert (after the header, before first ## entry)
        # Look for first "## " which marks the first date entry
        if "## " in existing_content:
            # Insert new summary after header but before first entry
            parts = existing_content.split("## ", 1)
            if len(parts) == 2:
                new_content = parts[0] + summary + "## " + parts[1]
            else:
                new_content = existing_content + "\n" + summary
        else:
            new_content = existing_content + "\n" + summary

    with open(index_file, "w", encoding="utf-8") as f:
        f.write(new_content)


def clear_current_tasks(worklog_dir: Path):
    """Clear the current tasks file after summarizing."""
    tasks_file = worklog_dir / ".current_tasks"
    if tasks_file.exists():
        tasks_file.unlink()


def get_project_memory_dir() -> Path:
    """Get the project auto memory directory using Claude Code's convention."""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    # Claude Code encodes project paths: C:\Users\craig\project -> C--Users-craig-project
    # Replace path separators and colon with dashes
    encoded = project_dir.replace("\\", "-").replace("/", "-").replace(":", "")
    # Remove leading dash if present
    encoded = encoded.lstrip("-")

    home = Path.home()
    projects_dir = home / ".claude" / "projects"

    # Try exact match first
    candidate = projects_dir / encoded / "memory"
    if candidate.parent.exists():
        return candidate

    # Search for matching project directory
    if projects_dir.exists():
        try:
            for d in projects_dir.iterdir():
                if d.is_dir():
                    # Check if directory name matches our project
                    dir_name = d.name
                    if encoded.lower().startswith(dir_name.lower()[:30]) or \
                       dir_name.lower().startswith(encoded.lower()[:30]):
                        return d / "memory"
        except Exception:
            pass

    return candidate  # Fall back to constructed path


def load_existing_structure_names(worklog_dir: Path) -> Set[str]:
    """Load all previously known structure names from structures.jsonl."""
    structures_file = worklog_dir / "structures.jsonl"
    names = set()

    if structures_file.exists():
        try:
            with open(structures_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            names.add(entry.get("name", ""))
                        except json.JSONDecodeError:
                            continue
        except Exception:
            pass

    return names


def write_auto_memory(worklog_dir: Path, edits: List[Dict], newly_processed: set):
    """Write key findings to auto memory MEMORY.md if significant work was done.

    'Significant' = 3+ file edits or structures captured this session.
    """
    # Count new edits in this session
    new_edits = [e for e in edits if e.get("ts") in newly_processed]
    if len(new_edits) < 3:
        return

    try:
        memory_dir = get_project_memory_dir()
        memory_dir.mkdir(parents=True, exist_ok=True)
        memory_file = memory_dir / "MEMORY.md"

        # Load existing memory content
        existing = ""
        if memory_file.exists():
            existing = memory_file.read_text(encoding="utf-8", errors="ignore")

        # Gather insights to write
        insights = []
        today = datetime.now().strftime("%Y-%m-%d")

        # Find most active directories
        dir_counts: Dict[str, int] = {}
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
        for edit in new_edits:
            file_path = edit.get("file_path", "")
            try:
                rel = os.path.relpath(file_path, project_dir)
                if not rel.startswith(".."):
                    parent = str(Path(rel).parent)
                    if parent != ".":
                        dir_counts[parent] = dir_counts.get(parent, 0) + 1
            except ValueError:
                pass

        if dir_counts:
            top_dirs = sorted(dir_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            dirs_str = ", ".join(f"`{d}`" for d, _ in top_dirs)
            insights.append(f"- Active directories ({today}): {dirs_str}")

        # Find new structures from this session
        structures_file = worklog_dir / "structures.jsonl"
        if structures_file.exists():
            new_structs = []
            try:
                with open(structures_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                entry = json.loads(line)
                                ts = entry.get("ts", "")
                                if ts.startswith(today) and ts in newly_processed or \
                                   entry.get("operation") == "created":
                                    name = entry.get("name", "")
                                    fpath = entry.get("file", "")
                                    stype = entry.get("type", "")
                                    new_structs.append(f"`{name}` ({stype}) in `{fpath}`")
                            except json.JSONDecodeError:
                                continue
            except Exception:
                pass

            if new_structs:
                structs_str = ", ".join(new_structs[:5])
                if len(new_structs) > 5:
                    structs_str += f" +{len(new_structs) - 5} more"
                insights.append(f"- Key structures ({today}): {structs_str}")

        if not insights:
            return

        # Build the new memory section
        section_header = f"\n## Echo session {today}\n"
        section_content = "\n".join(insights) + "\n"

        # Check if we already have an entry for today — replace it
        if section_header.strip() in existing:
            # Replace existing section for today
            pattern = re.escape(section_header.strip()) + r"\n(?:- .*\n)*"
            existing = re.sub(pattern, "", existing)

        # Append new section
        updated = existing.rstrip() + "\n" + section_header + section_content

        # Keep memory file reasonable — trim to last 50 lines
        lines = updated.split("\n")
        if len(lines) > 50:
            updated = "\n".join(lines[-50:])

        memory_file.write_text(updated, encoding="utf-8")
        log_verbose("✓ Echo: updated auto memory")

    except Exception:
        # Fail silently
        pass


def main():
    try:
        worklog_dir = get_worklog_dir()
        logs_dir = get_logs_dir()

        # Load data
        tasks = load_current_tasks(worklog_dir)
        edits = load_todays_edits(logs_dir)
        processed = load_processed_entries(worklog_dir)

        # Generate and save summary
        summary, newly_processed = generate_summary(tasks, edits, processed)

        if summary:
            prepend_to_index(worklog_dir, summary)

            # Update processed entries
            processed.update(newly_processed)
            save_processed_entries(worklog_dir, processed)

            # Write to auto memory if significant work
            write_auto_memory(worklog_dir, edits, newly_processed)

            # Verbose output
            task_count = len([t for t in tasks if t.get("ts") in newly_processed])
            edit_count = len([e for e in edits if e.get("ts") in newly_processed])
            log_verbose(f"✓ Session saved: {task_count} tasks, {edit_count} edits")

        # Clear current tasks
        clear_current_tasks(worklog_dir)

    except Exception:
        # Fail silently - never break the workflow
        pass


if __name__ == "__main__":
    main()
