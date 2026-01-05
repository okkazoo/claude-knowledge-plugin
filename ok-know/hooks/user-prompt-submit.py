#!/usr/bin/env python3
"""
UserPromptSubmit Hook: Search knowledge.json before Claude responds

Extracts keywords from user's prompt and searches knowledge.json for:
- Matching patterns (solutions, gotchas, tried-failed, best-practices)
- Relevant journey files and facts

This helps Claude learn from past mistakes and not reinvent the wheel.
"""

import json
import sys
import re
from pathlib import Path

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
    'if', 'or', 'because', 'until', 'while', 'of', 'this', 'that', 'these',
    'those', 'am', 'it', 'its', 'i', 'me', 'my', 'you', 'your', 'we', 'our',
    'they', 'them', 'their', 'what', 'which', 'who', 'whom', 'any', 'both',
    'let', 'get', 'got', 'make', 'made', 'want', 'please', 'help', 'try',
    'also', 'like', 'using', 'use', 'used', 'about', 'know', 'think'
}

# Minimum word length to consider
MIN_WORD_LENGTH = 3


def extract_keywords(text):
    """Extract meaningful keywords from user prompt."""
    # Lowercase and split on non-alphanumeric
    words = re.findall(r'[a-zA-Z0-9_-]+', text.lower())

    # Filter out stop words and short words
    keywords = set()
    for word in words:
        if len(word) >= MIN_WORD_LENGTH and word not in STOP_WORDS:
            keywords.add(word)

    return keywords


def search_patterns(keywords, patterns):
    """Search patterns for keyword matches."""
    matches = []
    type_icons = {
        'solution': '[OK]',
        'tried-failed': '[X]',
        'gotcha': '[!]',
        'best-practice': '[*]'
    }

    for p in patterns:
        # Get pattern text and context
        pattern_text = p.get('pattern', p.get('text', '')).lower()
        context = p.get('context', [])
        if isinstance(context, str):
            context = context.lower().replace(',', ' ').split()
        else:
            context = [c.lower() for c in context]

        # Combine all searchable text
        all_text = set(pattern_text.split()) | set(context)

        # Count keyword overlap
        overlap = len(keywords & all_text)

        # Also check for substring matches in pattern text
        for kw in keywords:
            if kw in pattern_text:
                overlap += 1

        if overlap >= 2:  # Require at least 2 keyword matches
            ptype = p.get('type', 'other')
            icon = type_icons.get(ptype, '*')
            display_text = p.get('pattern', p.get('text', ''))[:100]
            matches.append((overlap, ptype, f"  {icon} {display_text}"))

    # Sort by overlap score, then by type priority
    type_priority = {'gotcha': 0, 'tried-failed': 1, 'best-practice': 2, 'solution': 3}
    matches.sort(key=lambda x: (-x[0], type_priority.get(x[1], 4)))

    return [m[2] for m in matches[:5]]


def search_files(keywords, files):
    """Search files index for keyword matches."""
    matches = []

    for filepath, info in files.items():
        title = info.get('title', filepath).lower()
        file_keywords = [kw.lower() for kw in info.get('keywords', [])]
        category = info.get('category', '').lower()

        # Combine searchable text
        all_text = set(title.split()) | set(file_keywords) | {category}

        # Count keyword overlap
        overlap = len(keywords & all_text)

        # Also check for substring matches in title
        for kw in keywords:
            if kw in title:
                overlap += 1

        if overlap >= 2:  # Require at least 2 keyword matches
            display_title = info.get('title', filepath)[:60]
            matches.append((overlap, f"  - {display_title}"))

    matches.sort(key=lambda x: -x[0])
    return [m[1] for m in matches[:3]]


def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        print(json.dumps({}))
        return

    # Get user's prompt
    prompt = input_data.get('prompt', '')
    if not prompt or len(prompt) < 10:
        print(json.dumps({}))
        return

    # Find knowledge.json - check current directory and parent
    knowledge_paths = [
        Path('.claude/knowledge/knowledge.json'),
        Path('../.claude/knowledge/knowledge.json'),
    ]

    knowledge_json = None
    for kp in knowledge_paths:
        if kp.exists():
            knowledge_json = kp
            break

    if not knowledge_json:
        print(json.dumps({}))
        return

    try:
        data = json.loads(knowledge_json.read_text(encoding='utf-8'))
    except Exception:
        print(json.dumps({}))
        return

    # Extract keywords from prompt
    keywords = extract_keywords(prompt)
    if len(keywords) < 2:
        print(json.dumps({}))
        return

    # Search patterns and files
    patterns = data.get('patterns', [])
    files = data.get('files', {})

    pattern_matches = search_patterns(keywords, patterns)
    file_matches = search_files(keywords, files)

    if not pattern_matches and not file_matches:
        print(json.dumps({}))
        return

    # Build message
    msg_parts = [">> KNOWLEDGE BASE MATCHES:"]

    if pattern_matches:
        msg_parts.append("\nPatterns (check before trying):")
        msg_parts.extend(pattern_matches)

    if file_matches:
        msg_parts.append("\nRelated entries:")
        msg_parts.extend(file_matches)

    msg_parts.append("\n(Review these before suggesting an approach)")

    print(json.dumps({
        "message": "\n".join(msg_parts)
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({}))
