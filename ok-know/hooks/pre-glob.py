#!/usr/bin/env python3
"""PreToolUse Hook: Search knowledge before Glob searches

When Claude uses Glob to find files, first check if knowledge.json
has relevant patterns or files that might answer the question.
"""

import json
import sys
import re
from pathlib import Path

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
    # Extract words from pattern, ignoring glob chars
    words = re.findall(r'[a-zA-Z][a-zA-Z0-9_-]*', text.lower())
    keywords = set()
    for word in words:
        if len(word) >= 3 and word not in STOP_WORDS:
            keywords.add(word)
    return keywords


def search_knowledge(keywords):
    """Search knowledge.json for matching entries."""
    matches = {'patterns': [], 'files': []}
    knowledge_json = Path('.claude/knowledge/knowledge.json')

    if not knowledge_json.exists():
        return matches

    try:
        data = json.loads(knowledge_json.read_text(encoding='utf-8'))
    except:
        return matches

    type_icons = {
        'solution': '[OK]',
        'tried-failed': '[X]',
        'gotcha': '[!]',
        'best-practice': '[*]'
    }

    # Search patterns
    for p in data.get('patterns', []):
        pattern_text = p.get('pattern', '').lower()
        context = p.get('context', '')
        if isinstance(context, list):
            context = ' '.join(context)
        context = context.lower()

        all_text = pattern_text + ' ' + context
        overlap = sum(1 for kw in keywords if kw in all_text)

        if overlap >= 1:  # Lower threshold for glob patterns
            ptype = p.get('type', 'other')
            icon = type_icons.get(ptype, '*')
            matches['patterns'].append({
                'score': overlap,
                'text': f"{icon} {p.get('pattern', '')}"
            })

    # Search files by keywords
    for filepath, info in data.get('files', {}).items():
        file_keywords = set(kw.lower() for kw in info.get('keywords', []))
        title = info.get('title', filepath).lower()

        overlap = len(keywords & file_keywords)
        title_overlap = sum(1 for kw in keywords if kw in title)
        total_score = overlap + title_overlap

        if total_score >= 1:  # Lower threshold
            matches['files'].append({
                'score': total_score,
                'path': filepath,
                'title': info.get('title', filepath)
            })

    matches['patterns'].sort(key=lambda x: x['score'], reverse=True)
    matches['files'].sort(key=lambda x: x['score'], reverse=True)

    return matches


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except:
        print(json.dumps({"continue": True}))
        return

    tool_input = input_data.get('tool_input', {})
    pattern = tool_input.get('pattern', '')

    if not pattern or len(pattern) < 3:
        print(json.dumps({"continue": True}))
        return

    keywords = extract_keywords(pattern)

    if len(keywords) < 1:
        print(json.dumps({"continue": True}))
        return

    matches = search_knowledge(keywords)

    if not matches['patterns'] and not matches['files']:
        print(json.dumps({"continue": True}))
        return

    msg_parts = [f">> KNOWLEDGE CHECK for '{pattern}':"]

    if matches['patterns']:
        msg_parts.append("\nRelevant patterns:")
        for p in matches['patterns'][:3]:
            msg_parts.append(f"  {p['text']}")

    if matches['files']:
        msg_parts.append("\nKnowledge files:")
        for f in matches['files'][:3]:
            msg_parts.append(f"  - {f['title']}")

    msg_parts.append("\n(Check knowledge first - may already have the answer)")

    print(json.dumps({
        "continue": True,
        "message": "\n".join(msg_parts)
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({"continue": True}))
