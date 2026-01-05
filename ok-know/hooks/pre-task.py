#!/usr/bin/env python3
"""
PreToolUse Hook: Search knowledge before launching Task agents

When Claude launches exploration or planning agents, first search the local
knowledge base for relevant context. This saves API costs by surfacing
existing knowledge before expensive agent searches.
"""

import json
import sys
import re
from pathlib import Path

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

    # Search patterns
    type_icons = {
        'solution': '[OK]',
        'tried-failed': '[X]',
        'gotcha': '[!]',
        'best-practice': '[*]'
    }

    for p in data.get('patterns', []):
        pattern_text = p.get('pattern', '').lower()
        context = p.get('context', '')
        if isinstance(context, list):
            context = ' '.join(context)
        context = context.lower()

        all_text = pattern_text + ' ' + context
        overlap = sum(1 for kw in keywords if kw in all_text)

        if overlap >= 2:  # Need at least 2 keyword matches
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

        if total_score >= 2:
            matches['files'].append({
                'score': total_score,
                'path': filepath,
                'title': info.get('title', filepath),
                'keywords': list(file_keywords & keywords)[:3]
            })

    # Sort by score
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
    agent_type = tool_input.get('subagent_type', '').lower()
    prompt = tool_input.get('prompt', '')

    # Only intercept relevant agent types
    if agent_type not in KNOWLEDGE_RELEVANT_AGENTS:
        print(json.dumps({"continue": True}))
        return

    # Extract keywords from the task prompt
    keywords = extract_keywords(prompt)

    if len(keywords) < 2:
        print(json.dumps({"continue": True}))
        return

    # Search knowledge base
    matches = search_knowledge(keywords)

    if not matches['patterns'] and not matches['files']:
        print(json.dumps({"continue": True}))
        return

    # Build context message
    msg_parts = [">> EXISTING KNOWLEDGE (check before exploring):"]

    if matches['patterns']:
        msg_parts.append("\nPatterns:")
        for p in matches['patterns'][:5]:
            msg_parts.append(f"  {p['text']}")

    if matches['files']:
        msg_parts.append("\nRelevant files:")
        for f in matches['files'][:5]:
            kw_str = ', '.join(f['keywords']) if f['keywords'] else ''
            msg_parts.append(f"  - {f['title']} ({f['path']})")
            if kw_str:
                msg_parts.append(f"    keywords: {kw_str}")

    msg_parts.append("\n(Read these files first - may have the answer already)")

    print(json.dumps({
        "continue": True,
        "message": "\n".join(msg_parts)
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({"continue": True}))
