#!/usr/bin/env python3
"""
context_builder.py - Autonomous context injection on every UserPromptSubmit

Searches ALL echo data sources (structures, searches, index, logs, auto memory)
and injects relevant context before Claude starts thinking.

Replaces search_structures.py with comprehensive multi-source search.
"""

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Tuple

from config import get_worklog_dir, log_verbose


# Words to skip when extracting keywords
STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "need", "to", "of",
    "in", "for", "on", "with", "at", "by", "from", "as", "into", "through",
    "and", "or", "but", "if", "then", "else", "when", "where", "why", "how",
    "all", "each", "every", "both", "few", "more", "most", "other", "some",
    "such", "no", "not", "only", "same", "so", "than", "too", "very", "just",
    "also", "now", "here", "there", "this", "that", "these", "those", "it",
    "its", "i", "me", "my", "we", "our", "you", "your", "he", "she", "they",
    "them", "what", "which", "who", "whom", "get", "make", "like", "want",
    "please", "thanks", "help", "show", "tell", "explain", "look", "see",
    "file", "files", "code", "function", "class", "method", "work", "works",
}

MAX_OUTPUT_CHARS = 2000
MIN_SCORE = 2


def extract_keywords(text: str) -> Set[str]:
    """Extract meaningful keywords from text."""
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    return {w for w in words if w not in STOP_WORDS}


def load_jsonl(file_path: Path) -> List[Dict]:
    """Load entries from a JSONL file."""
    entries = []
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception:
            pass
    return entries


# --- Source 1: structures.jsonl ---

def search_structures(worklog_dir: Path, keywords: Set[str]) -> List[Tuple[int, Dict]]:
    """
    Search structures.jsonl for keyword matches.
    Score: +3 name match, +2 path segment match, +1 task_hint match.
    """
    entries = load_jsonl(worklog_dir / "structures.jsonl")
    if not entries or not keywords:
        return []

    scored = []
    seen = set()  # deduplicate by (file, name)

    for entry in entries:
        name = entry.get("name", "")
        file_path = entry.get("file", "")
        task_hint = entry.get("task_hint", "")
        path_keywords = entry.get("path_keywords", [])

        key = (file_path, name)
        if key in seen:
            continue
        seen.add(key)

        # Build path segments for matching
        path_parts = set()
        for part in Path(file_path).parts:
            # Strip extension from filename
            stem = Path(part).stem.lower()
            if stem:
                path_parts.add(stem)
        # Also include stored path_keywords
        for pk in path_keywords:
            path_parts.add(pk.lower())

        score = 0
        for kw in keywords:
            if kw in name.lower():
                score += 3
            if kw in path_parts:
                score += 2
            if task_hint and kw in task_hint.lower():
                score += 1

        if score >= MIN_SCORE:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:8]


# --- Source 2: searches.jsonl ---

def search_past_searches(worklog_dir: Path, keywords: Set[str]) -> List[str]:
    """
    Find past search patterns related to the topic.
    Returns directory hints where keywords were found.
    """
    entries = load_jsonl(worklog_dir / "searches.jsonl")
    if not entries or not keywords:
        return []

    matching_dirs = defaultdict(int)

    for entry in entries:
        pattern = entry.get("pattern", "").lower()
        directories = entry.get("directories", [])

        # Check if any keyword matches the search pattern or its directories
        matched = False
        for kw in keywords:
            if kw in pattern:
                matched = True
                break
            for d in directories:
                if kw in d.lower():
                    matched = True
                    break
            if matched:
                break

        if matched:
            for d in directories:
                matching_dirs[d] += 1

    if not matching_dirs:
        return []

    # Sort by frequency, return top dirs
    sorted_dirs = sorted(matching_dirs.items(), key=lambda x: x[1], reverse=True)
    return [d for d, _ in sorted_dirs[:5]]


# --- Source 3: index.md ---

def search_index(worklog_dir: Path, keywords: Set[str]) -> List[str]:
    """
    Scan recent session summaries in index.md for topic mentions.
    Returns matching session descriptions.
    """
    index_file = worklog_dir / "index.md"
    if not index_file.exists() or not keywords:
        return []

    try:
        content = index_file.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    # Parse entries (each starts with "## 20...")
    entries = []
    current_entry = []

    for line in content.split("\n"):
        if line.startswith("## 20"):
            if current_entry:
                entries.append("\n".join(current_entry))
            current_entry = [line]
        elif current_entry:
            current_entry.append(line)

    if current_entry:
        entries.append("\n".join(current_entry))

    # Search recent entries (max 20) for keyword matches
    matches = []
    for entry in entries[:20]:
        entry_lower = entry.lower()
        for kw in keywords:
            if kw in entry_lower:
                # Extract the date and task line
                lines = entry.strip().split("\n")
                date = lines[0].replace("## ", "").strip() if lines else ""
                task = ""
                for line in lines[1:]:
                    if line.startswith("**Task**:"):
                        task = line.replace("**Task**:", "").strip()
                        break
                if date and task:
                    matches.append(f"{date}: {task}")
                break  # One match per entry is enough

    return matches[:3]


# --- Source 4: logs/*.jsonl ---

def search_recent_logs(worklog_dir: Path, keywords: Set[str]) -> List[str]:
    """
    Find recent file edits matching keywords (last 7 days of logs).
    Returns file paths that were recently modified.
    """
    logs_dir = worklog_dir / "logs"
    if not logs_dir.exists() or not keywords:
        return []

    cutoff = datetime.now() - timedelta(days=7)
    matching_files = defaultdict(int)

    # Check recent log files
    try:
        for log_file in sorted(logs_dir.glob("*.jsonl"), reverse=True):
            # Parse date from filename
            try:
                file_date = datetime.strptime(log_file.stem, "%Y-%m-%d")
                if file_date < cutoff:
                    break
            except ValueError:
                continue

            entries = load_jsonl(log_file)
            for entry in entries:
                file_path = entry.get("file_path", "")
                if not file_path:
                    continue

                path_lower = file_path.lower()
                for kw in keywords:
                    if kw in path_lower:
                        # Make path relative for display
                        try:
                            project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
                            rel = os.path.relpath(file_path, project_dir)
                            if not rel.startswith(".."):
                                file_path = rel
                        except ValueError:
                            pass
                        matching_files[file_path] += 1
                        break
    except Exception:
        pass

    if not matching_files:
        return []

    sorted_files = sorted(matching_files.items(), key=lambda x: x[1], reverse=True)
    return [f for f, _ in sorted_files[:5]]


# --- Source 5: Auto memory MEMORY.md ---

def search_auto_memory(keywords: Set[str]) -> List[str]:
    """
    Search project auto memory MEMORY.md for relevant notes.
    """
    if not keywords:
        return []

    # Try to find the project memory directory
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    # Claude Code uses a hash of the project path for the memory directory
    # Try the direct path convention
    home = Path.home()
    memory_candidates = []

    # Check all project memory directories
    projects_dir = home / ".claude" / "projects"
    if projects_dir.exists():
        try:
            for d in projects_dir.iterdir():
                if d.is_dir():
                    mem_file = d / "memory" / "MEMORY.md"
                    if mem_file.exists():
                        # Check if this project dir name relates to our project
                        # Claude Code encodes paths like C--Users-craig-Documents-...
                        dir_name = d.name.lower().replace("-", " ").replace("_", " ")
                        project_name = Path(project_dir).name.lower()
                        if project_name in dir_name or project_dir.replace("\\", "-").replace("/", "-").replace(":", "-").lower().startswith(d.name.lower()[:20]):
                            memory_candidates.append(mem_file)
        except Exception:
            pass

    if not memory_candidates:
        return []

    matches = []
    for mem_file in memory_candidates[:1]:  # Only check first match
        try:
            content = mem_file.read_text(encoding="utf-8", errors="ignore")
            if not content.strip():
                continue

            # Simple keyword scan - find lines mentioning keywords
            for line in content.split("\n"):
                line_lower = line.lower().strip()
                if not line_lower or line_lower.startswith("#"):
                    continue
                for kw in keywords:
                    if kw in line_lower:
                        clean_line = line.strip()
                        if len(clean_line) > 10:
                            matches.append(clean_line)
                        break

        except Exception:
            continue

    return matches[:3]


# --- Output formatting ---

def format_output(
    structure_matches: List[Tuple[int, Dict]],
    search_dirs: List[str],
    index_matches: List[str],
    recent_files: List[str],
    memory_matches: List[str],
) -> str:
    """Format all matches into a concise context string."""
    sections = []

    if structure_matches:
        lines = ["**Relevant code structures:**"]
        for _, struct in structure_matches:
            name = struct.get("name", "")
            stype = struct.get("type", "")
            fpath = struct.get("file", "")
            hint = struct.get("task_hint", "")
            line = f"- `{name}` ({stype}) in `{fpath}`"
            if hint:
                line += f" — context: {hint}"
            lines.append(line)
        sections.append("\n".join(lines))

    if search_dirs:
        dirs_str = ", ".join(f"`{d}/`" for d in search_dirs)
        sections.append(f"**Past search hints:**\n- Code found in: {dirs_str}")

    if index_matches:
        lines = ["**Recent activity:**"]
        for m in index_matches:
            lines.append(f"- {m}")
        sections.append("\n".join(lines))

    if recent_files:
        lines = ["**Recently changed files:**"]
        for f in recent_files:
            lines.append(f"- `{f}`")
        sections.append("\n".join(lines))

    if memory_matches:
        lines = ["**From memory:**"]
        for m in memory_matches:
            lines.append(f"- {m}")
        sections.append("\n".join(lines))

    if not sections:
        return ""

    result = "**Echo context for your question:**\n\n" + "\n\n".join(sections)

    # Truncate to max output chars
    if len(result) > MAX_OUTPUT_CHARS:
        result = result[:MAX_OUTPUT_CHARS - 3] + "..."

    return result


def main():
    try:
        # Read hook input
        input_data = sys.stdin.read()
        if not input_data.strip():
            print(json.dumps({}))
            return

        data = json.loads(input_data)

        # Get user's prompt
        prompt = data.get("prompt", "").strip()
        if not prompt:
            print(json.dumps({}))
            return

        # Skip trivial/affirmative prompts — no useful context to inject
        if len(prompt) < 20 and prompt.lower().rstrip("!. ") in {
            "yes", "no", "ok", "okay", "do it", "go ahead", "sure",
            "looks good", "lgtm", "thanks", "continue", "proceed",
            "commit this", "push it", "yep", "nope", "correct",
        }:
            print(json.dumps({}))
            return

        # Extract keywords
        keywords = extract_keywords(prompt)
        if not keywords:
            print(json.dumps({}))
            return

        worklog_dir = get_worklog_dir()

        # Search all sources
        structure_matches = search_structures(worklog_dir, keywords)
        search_dirs = search_past_searches(worklog_dir, keywords)
        index_matches = search_index(worklog_dir, keywords)
        recent_files = search_recent_logs(worklog_dir, keywords)
        memory_matches = search_auto_memory(keywords)

        # Check if we have enough signal
        total_score = sum(s for s, _ in structure_matches)
        total_matches = (
            len(structure_matches)
            + len(search_dirs)
            + len(index_matches)
            + len(recent_files)
            + len(memory_matches)
        )

        if total_matches == 0:
            print(json.dumps({}))
            return

        # Format output
        context = format_output(
            structure_matches, search_dirs, index_matches,
            recent_files, memory_matches
        )

        if not context:
            print(json.dumps({}))
            return

        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context
            }
        }

        log_verbose(f"✓ Echo: {total_matches} matches from {sum(1 for x in [structure_matches, search_dirs, index_matches, recent_files, memory_matches] if x)} sources")
        print(json.dumps(output))

    except Exception:
        # Fail silently
        print(json.dumps({}))


if __name__ == "__main__":
    main()
