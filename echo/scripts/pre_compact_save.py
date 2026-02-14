#!/usr/bin/env python3
"""
pre_compact_save.py - Save working context before auto-compaction

When Claude auto-compacts the conversation, all injected context is lost.
This script saves a handover file so compact_restore.py can re-inject it.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from config import get_worklog_dir, log_verbose


def load_current_tasks(worklog_dir: Path) -> List[str]:
    """Load task prompts from .current_tasks."""
    tasks_file = worklog_dir / ".current_tasks"
    prompts = []

    if tasks_file.exists():
        try:
            with open(tasks_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            prompt = entry.get("prompt", "")
                            if prompt:
                                prompts.append(prompt)
                        except json.JSONDecodeError:
                            continue
        except Exception:
            pass

    return prompts


def load_todays_files(worklog_dir: Path) -> List[str]:
    """Load files touched today from daily logs."""
    logs_dir = worklog_dir / "logs"
    if not logs_dir.exists():
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    log_file = logs_dir / f"{today}.jsonl"

    if not log_file.exists():
        return []

    files = set()
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        file_path = entry.get("file_path", "")
                        if file_path:
                            # Make relative
                            try:
                                rel = os.path.relpath(file_path, project_dir)
                                if not rel.startswith(".."):
                                    file_path = rel
                            except ValueError:
                                pass
                            files.add(file_path)
                    except json.JSONDecodeError:
                        continue
    except Exception:
        pass

    return sorted(files)


def load_recent_structures(worklog_dir: Path) -> List[Dict]:
    """Load structures captured today."""
    structures_file = worklog_dir / "structures.jsonl"
    if not structures_file.exists():
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    structures = []
    seen = set()

    try:
        with open(structures_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        key = (entry.get("f", entry.get("file", "")), entry.get("n", entry.get("name", "")))
                        if key not in seen:
                            seen.add(key)
                            structures.append(entry)
                    except json.JSONDecodeError:
                        continue
    except Exception:
        pass

    return structures


def load_search_hints(worklog_dir: Path) -> List[str]:
    """Load recent search directory hints."""
    searches_file = worklog_dir / "searches.jsonl"
    if not searches_file.exists():
        return []

    dirs = set()
    try:
        with open(searches_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        for d in entry.get("directories", []):
                            dirs.add(d)
                    except json.JSONDecodeError:
                        continue
    except Exception:
        pass

    return sorted(dirs)[:5]


def main():
    try:
        # Read stdin (PreCompact hook data, may be empty)
        sys.stdin.read()

        worklog_dir = get_worklog_dir()

        # Gather session state
        tasks = load_current_tasks(worklog_dir)
        files = load_todays_files(worklog_dir)
        structures = load_recent_structures(worklog_dir)
        search_dirs = load_search_hints(worklog_dir)

        # Build handover content
        lines = ["## Session handover (auto-saved before compaction)"]

        if tasks:
            # Use the most recent task
            latest = tasks[-1]
            if len(latest) > 100:
                latest = latest[:100] + "..."
            lines.append(f"**Working on**: {latest}")

        if files:
            files_str = ", ".join(files[:10])
            if len(files) > 10:
                files_str += f" +{len(files) - 10} more"
            lines.append(f"**Files touched this session**: {files_str}")

        if structures:
            struct_strs = []
            for s in structures[:8]:
                struct_strs.append(f"{s.get('name', '')} ({s.get('type', '')})")
            structs_str = ", ".join(struct_strs)
            if len(structures) > 8:
                structs_str += f" +{len(structures) - 8} more"
            lines.append(f"**Key structures**: {structs_str}")

        if search_dirs:
            dirs_str = ", ".join(search_dirs)
            lines.append(f"**Search hints**: code in {dirs_str}")

        # Only write if we have meaningful content
        if len(lines) <= 1:
            log_verbose("✓ Compact: no session data to save")
            return

        handover_content = "\n".join(lines) + "\n"

        # Truncate to ~500 chars
        if len(handover_content) > 500:
            handover_content = handover_content[:497] + "...\n"

        handover_file = worklog_dir / ".compact_handover.md"
        with open(handover_file, "w", encoding="utf-8") as f:
            f.write(handover_content)

        log_verbose(f"✓ Compact: saved handover ({len(lines) - 1} sections)")

    except Exception:
        # Fail silently
        pass


if __name__ == "__main__":
    main()
