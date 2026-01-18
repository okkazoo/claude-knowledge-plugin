#!/usr/bin/env python3
"""
PreToolUse Hook for Task - Search memory before launching agents.

When Claude launches exploration or planning agents, first search
the local knowledge base for relevant context. This saves API costs
by surfacing existing knowledge before expensive agent searches.
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


# Agent types that benefit from knowledge context
KNOWLEDGE_RELEVANT_AGENTS = {
    'explore', 'plan', 'general-purpose',
    'feature-dev:code-architect', 'feature-dev:code-explorer'
}

STOP_WORDS = {
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'can', 'need', 'to', 'of', 'in',
    'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through',
    'this', 'that', 'these', 'those', 'it', 'its', 'i', 'me', 'my', 'you',
    'your', 'we', 'our', 'they', 'them', 'their', 'what', 'which', 'who',
    'how', 'why', 'when', 'where', 'and', 'but', 'or', 'if', 'then',
    'use', 'using', 'find', 'search', 'look', 'check', 'get', 'make',
    'help', 'want', 'need', 'please', 'agent', 'explore', 'codebase'
}


def extract_keywords(text):
    """Extract meaningful keywords from prompt."""
    words = re.findall(r'[a-zA-Z0-9_-]+', text.lower())
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
    files = f" ({', '.join(fact.file_refs[:2])})" if fact.file_refs else ""

    return f"  {icon} {text}{files}"


def search_memory(query: str) -> list:
    """Search memory for relevant facts."""
    if not CORE_AVAILABLE:
        return []

    try:
        config = Config.load()
        searcher = Searcher(config=config)

        # More results for task agents
        results = searcher.search(query, top_k=5)

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
    agent_type = tool_input.get('subagent_type', '').lower()
    prompt = tool_input.get('prompt', '')

    # Only intercept relevant agent types
    if agent_type not in KNOWLEDGE_RELEVANT_AGENTS:
        print(json.dumps({}))
        return

    keywords = extract_keywords(prompt)

    if len(keywords) < 2:
        print(json.dumps({}))
        return

    matches = search_memory(prompt)

    if not matches:
        print(json.dumps({}))
        return

    msg_parts = [">> EXISTING KNOWLEDGE (check before exploring):"]
    msg_parts.extend(matches)
    msg_parts.append("\n(Read these first - may have the answer already)")

    print(json.dumps({
        "message": "\n".join(msg_parts)
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({}))
