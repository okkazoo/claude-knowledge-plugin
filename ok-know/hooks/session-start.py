#!/usr/bin/env python3
"""
SessionStart Hook - Injects project state and recent facts from memory.

Runs once at the start of each Claude Code session.
"""

import json
import sys
import subprocess
from pathlib import Path

# Add parent directory to path for core imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from core.database import Database
    from core.config import Config
    from core.models import FactType
    CORE_AVAILABLE = True
except ImportError:
    CORE_AVAILABLE = False


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


def get_memory_stats():
    """Get statistics from the memory database."""
    if not CORE_AVAILABLE:
        return None

    try:
        config = Config.load()
        db = Database(config)
        stats = db.get_stats()
        db.close()
        return stats
    except Exception:
        return None


def get_recent_facts(limit: int = 5):
    """Get most recent facts from memory."""
    if not CORE_AVAILABLE:
        return []

    try:
        config = Config.load()
        db = Database(config)
        facts = db.get_recent_facts(limit)
        db.close()

        type_icons = {
            FactType.SOLUTION: "[OK]",
            FactType.GOTCHA: "[!]",
            FactType.TRIED_FAILED: "[X]",
            FactType.DECISION: "[D]",
            FactType.CONTEXT: "[C]",
        }

        result = []
        for fact in facts:
            icon = type_icons.get(fact.fact_type, "*")
            text = fact.text[:80] + "..." if len(fact.text) > 80 else fact.text
            result.append(f"  {icon} {text}")

        return result
    except Exception:
        return []


def get_important_gotchas(limit: int = 3):
    """Get important gotchas that should always be shown."""
    if not CORE_AVAILABLE:
        return []

    try:
        config = Config.load()
        db = Database(config)
        gotchas = db.get_recent_facts(limit, FactType.GOTCHA)
        db.close()

        return [f"  [!] {g.text[:100]}" for g in gotchas]
    except Exception:
        return []


def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        input_data = {}

    try:
        context_parts = []

        # Git status
        git = get_git_status()
        if "error" not in git:
            context_parts.append(f"""## Current State
- **Branch:** {git['branch']}
- **Last commit:** {git['last_commit']}
- **Uncommitted changes:** {git['modified_count']} files
""")
            if git['modified_count'] > 0:
                context_parts.append(f"```\n{git['modified_files']}\n```")

        # Memory stats
        stats = get_memory_stats()
        if stats and stats.get("total_facts", 0) > 0:
            by_type = stats.get("by_type", {})
            type_summary = ", ".join(f"{k}: {v}" for k, v in by_type.items())
            context_parts.append(f"""## Memory
- **Total facts:** {stats['total_facts']} ({type_summary})
- **With embeddings:** {stats.get('with_embeddings', 0)}
""")

        # Important gotchas (always show these)
        gotchas = get_important_gotchas()
        if gotchas:
            context_parts.append("## Important Gotchas")
            context_parts.extend(gotchas)
            context_parts.append("")

        # Recent facts
        recent = get_recent_facts(5)
        if recent:
            context_parts.append("## Recent Facts")
            context_parts.extend(recent)
            context_parts.append("\n*Use `/ok-know:knowledge` for more, `/ok-know:wip` to add facts.*")

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
