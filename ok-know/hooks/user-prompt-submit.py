#!/usr/bin/env python3
"""
UserPromptSubmit Hook: Search knowledge.json before Claude responds

Extracts keywords from user's prompt and searches knowledge.json for:
- Matching patterns (solutions, gotchas, tried-failed, best-practices)
- Relevant journey files and facts

Uses mtime-based caching to avoid re-parsing on every prompt.
"""

import json
import sys
import re
import os
import pickle
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
    'also', 'like', 'using', 'use', 'used', 'about', 'know', 'think',
    'yes', 'yeah', 'okay', 'sure', 'thanks', 'thank', 'hello', 'hey', 'hi'
}

MIN_WORD_LENGTH = 3
CACHE_FILENAME = '.knowledge_cache.pkl'


def extract_keywords(text):
    """Extract meaningful keywords from user prompt."""
    words = re.findall(r'[a-zA-Z0-9_-]+', text.lower())
    keywords = set()
    for word in words:
        if len(word) >= MIN_WORD_LENGTH and word not in STOP_WORDS:
            keywords.add(word)
    return keywords


def build_search_index(data):
    """
    Build optimized search index from knowledge.json data.

    Returns:
        dict with 'patterns' and 'files' pre-processed for fast search
    """
    type_icons = {
        'solution': '[OK]',
        'tried-failed': '[X]',
        'gotcha': '[!]',
        'best-practice': '[*]'
    }
    type_priority = {'gotcha': 0, 'tried-failed': 1, 'best-practice': 2, 'solution': 3}

    # Pre-process patterns
    patterns_index = []
    for p in data.get('patterns', []):
        pattern_text = p.get('pattern', p.get('text', '')).lower()
        context = p.get('context', [])
        if isinstance(context, str):
            context = context.lower().replace(',', ' ').split()
        else:
            context = [c.lower() for c in context]

        # Pre-compute searchable words
        all_words = set(pattern_text.split()) | set(context)

        ptype = p.get('type', 'other')
        icon = type_icons.get(ptype, '*')
        display_text = p.get('pattern', p.get('text', ''))[:100]

        patterns_index.append({
            'words': all_words,
            'text': pattern_text,
            'type': ptype,
            'priority': type_priority.get(ptype, 4),
            'display': f"  {icon} {display_text}"
        })

    # Pre-process files
    files_index = []
    for filepath, info in data.get('files', {}).items():
        title = info.get('title', filepath).lower()
        file_keywords = [kw.lower() for kw in info.get('keywords', [])]
        category = info.get('category', '').lower()

        # Pre-compute searchable words
        all_words = set(title.split()) | set(file_keywords) | {category}

        display_title = info.get('title', filepath)[:60]

        files_index.append({
            'words': all_words,
            'title': title,
            'display': f"  - {display_title}"
        })

    return {
        'patterns': patterns_index,
        'files': files_index
    }


def get_cached_index(knowledge_json_path):
    """
    Get search index, using cache if knowledge.json hasn't changed.

    Returns:
        tuple: (patterns_index, files_index) or (None, None) if no data
    """
    cache_path = knowledge_json_path.parent / CACHE_FILENAME

    try:
        knowledge_mtime = knowledge_json_path.stat().st_mtime
    except OSError:
        return None, None

    # Try to load from cache
    if cache_path.exists():
        try:
            cache_mtime = cache_path.stat().st_mtime
            # Cache is valid if it's newer than knowledge.json
            if cache_mtime >= knowledge_mtime:
                with open(cache_path, 'rb') as f:
                    cached = pickle.load(f)
                    if cached.get('mtime') == knowledge_mtime:
                        idx = cached.get('index', {})
                        return idx.get('patterns', []), idx.get('files', [])
        except Exception:
            pass  # Cache invalid, rebuild

    # Load and parse knowledge.json
    try:
        data = json.loads(knowledge_json_path.read_text(encoding='utf-8'))
    except Exception:
        return None, None

    # Build index
    index = build_search_index(data)

    # Save to cache
    try:
        with open(cache_path, 'wb') as f:
            pickle.dump({
                'mtime': knowledge_mtime,
                'index': index
            }, f)
    except Exception:
        pass  # Cache write failed, still return index

    return index.get('patterns', []), index.get('files', [])


def search_patterns(keywords, patterns_index):
    """Search pre-indexed patterns for keyword matches."""
    matches = []

    for p in patterns_index:
        # Count keyword overlap with pre-computed words
        overlap = len(keywords & p['words'])

        # Also check for substring matches
        for kw in keywords:
            if kw in p['text']:
                overlap += 1

        if overlap >= 2:
            matches.append((overlap, p['priority'], p['display']))

    # Sort by overlap score, then by type priority
    matches.sort(key=lambda x: (-x[0], x[1]))
    return [m[2] for m in matches[:5]]


def search_files(keywords, files_index):
    """Search pre-indexed files for keyword matches."""
    matches = []

    for f in files_index:
        # Count keyword overlap with pre-computed words
        overlap = len(keywords & f['words'])

        # Also check for substring matches in title
        for kw in keywords:
            if kw in f['title']:
                overlap += 1

        if overlap >= 2:
            matches.append((overlap, f['display']))

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

    # Quick filter: skip if prompt looks like a greeting or simple response
    prompt_lower = prompt.lower().strip()
    if prompt_lower in ('yes', 'no', 'ok', 'okay', 'thanks', 'thank you', 'hi', 'hello', 'hey'):
        print(json.dumps({}))
        return

    # Extract keywords early - skip if not enough
    keywords = extract_keywords(prompt)
    if len(keywords) < 2:
        print(json.dumps({}))
        return

    # Find knowledge.json
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

    # Get cached index (fast path if unchanged)
    patterns_index, files_index = get_cached_index(knowledge_json)

    if patterns_index is None and files_index is None:
        print(json.dumps({}))
        return

    # Search
    pattern_matches = search_patterns(keywords, patterns_index) if patterns_index else []
    file_matches = search_files(keywords, files_index) if files_index else []

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
