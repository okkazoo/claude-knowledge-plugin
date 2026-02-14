#!/usr/bin/env python3
"""
consolidate_structure.py - SessionStart consolidation of captured knowledge

Reads accumulated structures and search patterns, verifies they still exist,
and outputs a consolidated structure.md for the session.
"""

import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Tuple

from config import get_worklog_dir, log_verbose


def load_jsonl(file_path: Path) -> List[Dict]:
    """Load entries from a JSONL file."""
    entries = []
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    return entries


def file_exists(file_path: str) -> bool:
    """Check if a file exists relative to project directory."""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    full_path = Path(project_dir) / file_path
    return full_path.exists()


def grep_exists(file_path: str, name: str) -> bool:
    """Quick check if a name still exists in a file."""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    full_path = Path(project_dir) / file_path

    if not full_path.exists():
        return False

    try:
        content = full_path.read_text(encoding="utf-8", errors="ignore")
        return name in content
    except Exception:
        return False


def consolidate_structures(entries: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Consolidate structure entries by file, keeping only verified ones.
    Returns: {file_path: [{name, type, task_hint}, ...]}
    """
    # Group by file, keeping task hints
    # Key: (file_path, name) -> {type, task_hint}
    by_file: Dict[str, Dict[str, Dict]] = defaultdict(dict)

    for entry in entries:
        file_path = entry.get("file", "")
        name = entry.get("name", "")
        struct_type = entry.get("type", "")
        task_hint = entry.get("task_hint", "")

        if file_path and name:
            # Keep the most recent task_hint if one exists
            existing = by_file[file_path].get(name, {})
            by_file[file_path][name] = {
                "type": struct_type,
                "task_hint": task_hint or existing.get("task_hint", "")
            }

    # Verify and consolidate
    verified: Dict[str, List[Dict]] = {}

    for file_path, structures in by_file.items():
        if not file_exists(file_path):
            continue

        valid_structures = []
        for name, info in structures.items():
            if grep_exists(file_path, name):
                valid_structures.append({
                    "name": name,
                    "type": info["type"],
                    "task_hint": info["task_hint"]
                })

        if valid_structures:
            verified[file_path] = valid_structures

    return verified


def consolidate_searches(entries: List[Dict]) -> Dict[str, Set[str]]:
    """
    Consolidate search patterns by directory.
    Returns: {directory: {pattern1, pattern2, ...}}
    """
    # Only keep recent searches (last 7 days)
    cutoff = datetime.now() - timedelta(days=7)

    by_dir: Dict[str, Set[str]] = defaultdict(set)

    for entry in entries:
        ts_str = entry.get("ts", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts < cutoff:
                continue
        except ValueError:
            continue

        pattern = entry.get("pattern", "")
        directories = entry.get("directories", [])

        for directory in directories:
            if pattern:
                by_dir[directory].add(pattern)

    return by_dir


MAX_STRUCTURE_MD_CHARS = 3000


def generate_structure_md(
    structures: Dict[str, List[Dict]],
    searches: Dict[str, Set[str]]
) -> str:
    """Generate the structure.md content, capped at MAX_STRUCTURE_MD_CHARS."""
    lines = [
        "# Project Structure (auto-generated)",
        f"*Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
    ]

    # Group structures by directory
    by_dir: Dict[str, List[Tuple[str, str, str, str]]] = defaultdict(list)
    for file_path, structs in structures.items():
        directory = str(Path(file_path).parent)
        if directory == ".":
            directory = "(root)"
        for s in structs:
            # Include task context if available
            task_hint = s.get("task_hint", "")
            by_dir[directory].append((Path(file_path).name, s["name"], s["type"], task_hint))

    if by_dir:
        lines.append("## Known Structures")
        lines.append("")

        for directory in sorted(by_dir.keys()):
            items = by_dir[directory]
            lines.append(f"### `{directory}/`")

            # Group by file
            by_file: Dict[str, List[Tuple[str, str, str]]] = defaultdict(list)
            for filename, name, struct_type, task_hint in items:
                by_file[filename].append((name, struct_type, task_hint))

            for filename in sorted(by_file.keys()):
                structs = by_file[filename]
                # Format: name (type) [task keywords if available]
                parts = []
                for name, t, hint in structs[:5]:
                    entry = f"{name} ({t})"
                    if hint:
                        entry += f" [{hint}]"
                    parts.append(entry)
                struct_str = ", ".join(parts)
                if len(structs) > 5:
                    struct_str += f" +{len(structs) - 5} more"
                lines.append(f"- `{filename}`: {struct_str}")

            lines.append("")

    if searches:
        lines.append("## Search Hints")
        lines.append("*Patterns that found results in these directories:*")
        lines.append("")

        for directory in sorted(searches.keys())[:10]:
            patterns = searches[directory]
            pattern_str = ", ".join(f'"{p}"' for p in sorted(patterns)[:5])
            if len(patterns) > 5:
                pattern_str += f" +{len(patterns) - 5} more"
            lines.append(f"- `{directory}/`: {pattern_str}")

        lines.append("")

    if not by_dir and not searches:
        lines.append("*No structural knowledge captured yet. Will build as you work.*")
        lines.append("")

    result = "\n".join(lines)

    # Cap output to avoid bloating SessionStart context
    if len(result) > MAX_STRUCTURE_MD_CHARS:
        struct_count = sum(len(s) for s in structures.values())
        result = result[:MAX_STRUCTURE_MD_CHARS - 80]
        # Find last complete line
        last_newline = result.rfind("\n")
        if last_newline > 0:
            result = result[:last_newline]
        result += f"\n\n*... truncated ({struct_count} total structures, showing top entries)*\n"

    return result


def load_recent_activity(worklog_dir: Path, max_entries: int = 5) -> str:
    """Load recent activity from index.md."""
    index_file = worklog_dir / "index.md"
    if not index_file.exists():
        return ""

    content = index_file.read_text(encoding="utf-8", errors="ignore")

    # Extract recent entries
    entries = []
    current_entry = []

    for line in content.split("\n"):
        if line.startswith("## 20"):  # Date header
            if current_entry:
                entries.append("\n".join(current_entry))
            current_entry = [line]
        elif current_entry:
            current_entry.append(line)

    if current_entry:
        entries.append("\n".join(current_entry))

    # Take most recent
    recent = entries[:max_entries]
    return "\n".join(recent)


def save_verified_structures(worklog_dir: Path, structures: Dict[str, List[Dict]]):
    """Save verified structures back, replacing the old file."""
    structures_file = worklog_dir / "structures.jsonl"
    temp_file = worklog_dir / "structures.jsonl.new"

    with open(temp_file, "w", encoding="utf-8") as f:
        for file_path, structs in structures.items():
            for s in structs:
                entry = {
                    "file": file_path,
                    "name": s["name"],
                    "type": s["type"],
                    "task_hint": s.get("task_hint", ""),
                    "verified": True,
                }
                f.write(json.dumps(entry) + "\n")

    # Replace old file
    if temp_file.exists():
        if structures_file.exists():
            structures_file.unlink()
        temp_file.rename(structures_file)


def main():
    try:
        worklog_dir = get_worklog_dir()

        # Load captured data
        structures_raw = load_jsonl(worklog_dir / "structures.jsonl")
        searches_raw = load_jsonl(worklog_dir / "searches.jsonl")

        # Consolidate and verify
        structures = consolidate_structures(structures_raw)
        searches = consolidate_searches(searches_raw)

        # Generate structure.md (no longer includes recent activity - that's in index.md)
        structure_content = generate_structure_md(structures, searches)

        structure_file = worklog_dir / "structure.md"
        with open(structure_file, "w", encoding="utf-8") as f:
            f.write(structure_content)

        # Save verified structures (prunes stale ones)
        if structures:
            save_verified_structures(worklog_dir, structures)

        # Output context for Claude
        context_parts = []

        if structures:
            struct_count = sum(len(s) for s in structures.values())
            file_count = len(structures)
            context_parts.append(f"{struct_count} structures in {file_count} files")

        if searches:
            search_count = sum(len(p) for p in searches.values())
            context_parts.append(f"{search_count} search patterns")

        if context_parts:
            summary = f"Worklog: {', '.join(context_parts)} tracked"
            log_verbose(f"✓ {summary}")

            # Include structure.md content as context
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": f"Project structure (from worklog):\n\n{structure_content}"
                }
            }
        else:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": ""
                }
            }

        print(json.dumps(output))

    except Exception as e:
        # On error, output empty context
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": ""
            }
        }
        print(json.dumps(output))


if __name__ == "__main__":
    main()
