#!/usr/bin/env python3
"""
SessionStart Hook
Injects current project state and context from previous sessions.
"""

import json
import sys
import subprocess
from pathlib import Path


def get_git_status():
    """Get current git status."""
    try:
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()

        last_commit = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()

        status = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()

        modified_count = len([l for l in status.split('\n') if l.strip()])

        return {
            "branch": branch,
            "last_commit": last_commit,
            "modified_count": modified_count,
            "modified_files": status[:500] if status else "No uncommitted changes"
        }
    except Exception as e:
        return {"error": str(e)}


def get_active_journeys():
    """Get list of active (non-completed) journeys."""
    try:
        journey_dir = Path(".claude/knowledge/journey")
        if not journey_dir.exists():
            return []

        active_journeys = []
        for category_folder in journey_dir.iterdir():
            if not category_folder.is_dir() or category_folder.name.startswith(('_', '.')):
                continue
            for topic_folder in category_folder.iterdir():
                if not topic_folder.is_dir() or topic_folder.name.startswith(('_', '.')):
                    continue
                meta_file = topic_folder / "_meta.md"
                if meta_file.exists():
                    with open(meta_file) as f:
                        content = f.read()
                    if "status: completed" not in content:
                        category = category_folder.name
                        topic = topic_folder.name
                        entries = len(list(topic_folder.glob("*.md"))) - 1
                        active_journeys.append(f"- **{category}/{topic}** ({entries} entries)")
        return active_journeys
    except Exception:
        return []


def get_knowledge_stats():
    """Get quick stats about knowledge base."""
    try:
        knowledge_dir = Path(".claude/knowledge")
        if not knowledge_dir.exists():
            return None

        completed_count = 0
        active_count = 0
        journey_dir = knowledge_dir / "journey"
        if journey_dir.exists():
            for category_dir in journey_dir.iterdir():
                if not category_dir.is_dir() or category_dir.name.startswith(('_', '.')):
                    continue
                for topic_dir in category_dir.iterdir():
                    if not topic_dir.is_dir() or topic_dir.name.startswith(('_', '.')):
                        continue
                    meta_file = topic_dir / "_meta.md"
                    if meta_file.exists():
                        with open(meta_file) as f:
                            if "status: completed" in f.read():
                                completed_count += 1
                            else:
                                active_count += 1

        facts_dir = knowledge_dir / "facts"
        facts_count = len([f for f in facts_dir.glob("*.md") if not f.name.startswith('.')]) if facts_dir.exists() else 0

        savepoints_dir = knowledge_dir / "savepoints"
        savepoint_count = len([f for f in savepoints_dir.glob("*.md") if not f.name.startswith('.')]) if savepoints_dir.exists() else 0

        return {
            "completed": completed_count,
            "active": active_count,
            "facts": facts_count,
            "savepoints": savepoint_count,
        }
    except Exception:
        return None


def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        input_data = {}

    try:
        context_parts = []

        git = get_git_status()
        if "error" not in git:
            context_parts.append(f"""## Current State
- **Branch:** {git['branch']}
- **Last commit:** {git['last_commit']}
- **Uncommitted changes:** {git['modified_count']} files
""")
            if git['modified_count'] > 0:
                context_parts.append(f"```\n{git['modified_files']}\n```")

        stats = get_knowledge_stats()
        if stats:
            context_parts.append(f"""## Knowledge Base
- Completed: {stats['completed']} | Active: {stats['active']} | Facts: {stats['facts']} | Savepoints: {stats['savepoints']}
""")

        active_journeys = get_active_journeys()
        if active_journeys:
            context_parts.append(f"""## Active Journeys (Work in Progress)
{chr(10).join(active_journeys)}

*Run `/ok-know:wip` to add progress.*
""")

        if context_parts:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "\n".join(context_parts)
                }
            }
            print(json.dumps(output))
    except Exception:
        pass


if __name__ == "__main__":
    main()
