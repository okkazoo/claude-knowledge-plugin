#!/usr/bin/env python3
"""
PreToolUse Hook for Glob - Search memory before glob operations.

Surfaces relevant facts that might help with file pattern searches.
"""

import json
import sys
import re
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


STOP_WORDS = {
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'can', 'need', 'to', 'of', 'in',
    'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through',
    'this', 'that', 'these', 'those', 'it', 'its', 'i', 'me', 'my', 'you',
    'your', 'we', 'our', 'they', 'them', 'their', 'what', 'which', 'who',
    'how', 'why', 'when', 'where', 'and', 'but', 'or', 'if', 'then',
    'use', 'using', 'find', 'search', 'look', 'check', 'get', 'make',
    'glob', 'pattern', 'files', 'file', 'src', 'lib', 'test', 'tests'
}


def extract_keywords(text):
    """Extract meaningful keywords from glob pattern."""
    words = re.findall(r'[a-zA-Z][a-zA-Z0-9_-]*', text.lower())
    keywords = set()
    for word in words:
        if len(word) >= 3 and word not in STOP_WORDS:
            keywords.add(word)
    return keywords


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

        results = searcher.search(query, top_k=3)

        formatted = []
        for fact, score in results:
            formatted.append(format_fact(fact, score))

        return formatted
    except Exception:
        return []


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except Exception:
        print(json.dumps({}))
        return

    tool_input = input_data.get('tool_input', {})
    pattern = tool_input.get('pattern', '')

    if not pattern or len(pattern) < 3:
        print(json.dumps({}))
        return

    keywords = extract_keywords(pattern)

    if len(keywords) < 1:
        print(json.dumps({}))
        return

    matches = search_memory(' '.join(keywords))

    if not matches:
        print(json.dumps({}))
        return

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
