#!/usr/bin/env python3
"""
PreToolUse Hook for Grep - Search memory before grep operations.

Surfaces relevant facts that might help with the search query.
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for core imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from core.searcher import Searcher
    from core.config import Config
    from core.models import FactType
    CORE_AVAILABLE = True
except ImportError:
    CORE_AVAILABLE = False


def format_fact(fact, score: float) -> str:
    """Format a fact for display."""
    type_icons = {
        FactType.SOLUTION: "[OK]",
        FactType.GOTCHA: "[!]",
        FactType.TRIED_FAILED: "[X]",
        FactType.DECISION: "[D]",
        FactType.CONTEXT: "[C]",
    }

    icon = type_icons.get(fact.fact_type, "*")
    text = fact.text[:80] + "..." if len(fact.text) > 80 else fact.text

    return f"  {icon} {text}"


def search_memory(query: str) -> list:
    """Search memory for relevant facts."""
    if not CORE_AVAILABLE:
        return []

    try:
        config = Config.load()
        searcher = Searcher(config=config)

        # Search with smaller result set for pre-tool context
        results = searcher.search(query, top_k=3)

        formatted = []
        for fact, score in results:
            formatted.append(format_fact(fact, score))

        return formatted
    except Exception:
        return []


def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        print(json.dumps({}))
        return

    # Get the search pattern from tool input
    tool_input = input_data.get('tool_input', {})
    pattern = tool_input.get('pattern', '')

    # Skip very short patterns
    if not pattern or len(pattern) < 2:
        print(json.dumps({}))
        return

    # Search memory for related facts
    matches = search_memory(pattern)

    if not matches:
        print(json.dumps({}))
        return

    # Build message
    msg_parts = [f">> Memory hints for '{pattern}':"]
    msg_parts.extend(matches)

    print(json.dumps({
        "message": "\n".join(msg_parts)
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({}))
