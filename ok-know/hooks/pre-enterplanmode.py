#!/usr/bin/env python3
"""
PreToolUse Hook: Surface knowledge before entering plan mode

When Claude enters plan mode, show relevant knowledge entries so
Claude has existing context before designing an implementation plan.
"""

import json
import sys
from pathlib import Path


def get_recent_journeys(limit=5):
    """Get most recently modified journey files."""
    journey_dir = Path('.claude/knowledge/journey')
    if not journey_dir.exists():
        return []

    entries = []
    for md_file in journey_dir.rglob('*.md'):
        if md_file.name.startswith('_'):
            continue
        try:
            mtime = md_file.stat().st_mtime
            # Get relative path from journey dir
            rel_path = md_file.relative_to(Path('.claude/knowledge'))
            entries.append({
                'mtime': mtime,
                'path': str(rel_path),
                'name': md_file.stem.replace('-', ' ').title()
            })
        except:
            continue

    entries.sort(key=lambda x: x['mtime'], reverse=True)
    return entries[:limit]


def get_patterns_summary():
    """Get summary of available patterns."""
    knowledge_json = Path('.claude/knowledge/knowledge.json')
    if not knowledge_json.exists():
        return None

    try:
        data = json.loads(knowledge_json.read_text(encoding='utf-8'))
        patterns = data.get('patterns', [])

        if not patterns:
            return None

        by_type = {}
        for p in patterns:
            ptype = p.get('type', 'other')
            by_type[ptype] = by_type.get(ptype, 0) + 1

        return by_type
    except:
        return None


def get_facts_count():
    """Count fact files."""
    facts_dir = Path('.claude/knowledge/facts')
    if not facts_dir.exists():
        return 0

    return len(list(facts_dir.glob('*.md')))


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except:
        print(json.dumps({"continue": True}))
        return

    # Check if knowledge base exists
    knowledge_dir = Path('.claude/knowledge')
    if not knowledge_dir.exists():
        print(json.dumps({"continue": True}))
        return

    msg_parts = [">> KNOWLEDGE BASE AVAILABLE - Check before planning:"]

    # Recent journeys
    journeys = get_recent_journeys(5)
    if journeys:
        msg_parts.append("\nRecent journeys (may have relevant implementation details):")
        for j in journeys:
            msg_parts.append(f"  - {j['name']} ({j['path']})")

    # Patterns summary
    patterns = get_patterns_summary()
    if patterns:
        pattern_str = ', '.join(f"{v} {k}" for k, v in patterns.items())
        msg_parts.append(f"\nPatterns indexed: {pattern_str}")
        msg_parts.append("  (Use /knowledge-search to find relevant patterns)")

    # Facts count
    facts = get_facts_count()
    if facts > 0:
        msg_parts.append(f"\nFacts: {facts} entries")

    if len(msg_parts) > 1:
        msg_parts.append("\nTip: Read relevant knowledge files before designing your plan.")
        print(json.dumps({
            "continue": True,
            "message": "\n".join(msg_parts)
        }))
    else:
        print(json.dumps({"continue": True}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({"continue": True}))
