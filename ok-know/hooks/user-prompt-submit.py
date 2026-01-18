#!/usr/bin/env python3
"""
UserPromptSubmit Hook - Search memory before Claude responds.

Features:
- Hybrid search (keyword + semantic) for relevant facts
- Injects matches into context for Claude to consider
- Fast-path for simple queries

Note: Deferred extraction is handled separately via /memory extract command
since Claude Code hooks don't support PostToolUse or state between turns.
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


# Common words to skip when extracting keywords
STOP_WORDS = {
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
    'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
    'from', 'as', 'into', 'through', 'during', 'before', 'after', 'above',
    'below', 'between', 'under', 'again', 'further', 'then', 'once',
    'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each', 'few',
    'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
    'own', 'same', 'so', 'than', 'too', 'very', 'just', 'and', 'but',
    'if', 'or', 'because', 'until', 'while', 'this', 'that', 'these',
    'those', 'am', 'it', 'its', 'i', 'me', 'my', 'you', 'your', 'we', 'our',
    'they', 'them', 'their', 'what', 'which', 'who', 'whom', 'any', 'both',
    'let', 'get', 'got', 'make', 'made', 'want', 'please', 'help', 'try',
    'also', 'like', 'using', 'use', 'about', 'know', 'think',
    'yes', 'yeah', 'okay', 'sure', 'thanks', 'thank', 'hello', 'hey', 'hi'
}


def extract_keywords(text: str, min_length: int = 3) -> set:
    """Extract meaningful keywords from user prompt."""
    words = re.findall(r'[a-zA-Z0-9_-]+', text.lower())
    keywords = set()
    for word in words:
        if len(word) >= min_length and word not in STOP_WORDS:
            keywords.add(word)
    return keywords


def is_trivial_prompt(prompt: str) -> bool:
    """Check if prompt is too simple to search."""
    prompt_lower = prompt.lower().strip()

    # Skip greetings and simple responses
    trivial = {
        'yes', 'no', 'ok', 'okay', 'thanks', 'thank you',
        'hi', 'hello', 'hey', 'sure', 'got it', 'sounds good',
        'continue', 'go ahead', 'proceed', 'next', 'done'
    }

    if prompt_lower in trivial:
        return True

    # Skip very short prompts
    if len(prompt) < 15:
        return True

    return False


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
    text = fact.text[:100] + "..." if len(fact.text) > 100 else fact.text

    return f"  {icon} {text}"


def search_memory(prompt: str) -> list:
    """Search memory for relevant facts."""
    if not CORE_AVAILABLE:
        return []

    try:
        config = Config.load()
        searcher = Searcher(config=config)

        # Hybrid search
        results = searcher.search(prompt, top_k=5)

        # Format results
        formatted = []
        for fact, score in results:
            formatted.append(format_fact(fact, score))

        return formatted
    except Exception as e:
        return []


def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        print(json.dumps({}))
        return

    # Get user's prompt
    prompt = input_data.get('prompt', '')

    # Quick exit for trivial prompts
    if not prompt or is_trivial_prompt(prompt):
        print(json.dumps({}))
        return

    # Extract keywords - skip if not enough
    keywords = extract_keywords(prompt)
    if len(keywords) < 2:
        print(json.dumps({}))
        return

    # Search memory
    matches = search_memory(prompt)

    if not matches:
        print(json.dumps({}))
        return

    # Build message
    msg_parts = [">> MEMORY MATCHES:"]
    msg_parts.extend(matches)
    msg_parts.append("\n(Consider these before responding)")

    print(json.dumps({
        "message": "\n".join(msg_parts)
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({}))
