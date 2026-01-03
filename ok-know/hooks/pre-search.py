#!/usr/bin/env python3
"""PreToolUse Hook: Pre-Search Index Check"""

import json
import sys

try:
    from pathlib import Path

    def search_patterns(pattern):
        """Search knowledge.json patterns for matching entries."""
        matches = []
        knowledge_json_path = Path('.claude/knowledge/knowledge.json')

        if not knowledge_json_path.exists():
            return matches

        try:
            data = json.loads(knowledge_json_path.read_text(encoding='utf-8'))
        except:
            return matches

        patterns_list = data.get('patterns', [])
        pattern_lower = pattern.lower()
        pattern_words = set(pattern_lower.split())

        type_icons = {
            'solution': '[OK]',
            'tried-failed': '[X]',
            'gotcha': '[!]',
            'best-practice': '[*]'
        }

        scored = []
        for p in patterns_list:
            pattern_text = p.get('pattern', '').lower()
            context = p.get('context', '').lower().replace(',', ' ')

            all_words = set(pattern_text.split()) | set(context.split())
            overlap = len(pattern_words & all_words)

            if pattern_lower in pattern_text or pattern_lower in context:
                overlap += 2

            if overlap > 0:
                ptype = p.get('type', 'other')
                icon = type_icons.get(ptype, '*')
                scored.append((overlap, f"  {icon} {p.get('pattern', '')}"))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:5]]

    def search_knowledge_keywords(pattern):
        """Search knowledge.json for matching keywords."""
        matches = []
        knowledge_json_path = Path('.claude/knowledge/knowledge.json')
        knowledge_base = Path('.claude/knowledge')

        if not knowledge_json_path.exists():
            return matches

        try:
            data = json.loads(knowledge_json_path.read_text(encoding='utf-8'))
        except:
            return matches

        pattern_lower = pattern.lower()

        for filepath, info in data.get('files', {}).items():
            full_path = knowledge_base / filepath
            if not full_path.exists():
                continue

            keywords = info.get('keywords', [])
            title = info.get('title', filepath)

            matching_keywords = [kw for kw in keywords if pattern_lower in kw.lower()]
            if matching_keywords:
                kw_str = ', '.join(matching_keywords[:3])
                matches.append(f"  - {title} -> {filepath} (keywords: {kw_str})")

        return matches[:5]

    def main():
        try:
            input_data = json.load(sys.stdin)
        except:
            print(json.dumps({"decision": "continue"}))
            return

        tool_input = input_data.get('tool_input', {})
        pattern = tool_input.get('pattern', '')

        if not pattern or len(pattern) < 2:
            print(json.dumps({"decision": "continue"}))
            return

        pattern_matches = search_patterns(pattern)
        knowledge_matches = search_knowledge_keywords(pattern)

        if pattern_matches or knowledge_matches:
            msg_parts = [f"Index matches for '{pattern}':"]

            if pattern_matches:
                msg_parts.append("\n>> PATTERNS (check before trying):")
                msg_parts.extend(pattern_matches)

            if knowledge_matches:
                msg_parts.append("\nKnowledge:")
                msg_parts.extend(knowledge_matches[:5])

            msg_parts.append("\n(Skip search if these answer your question)")

            print(json.dumps({
                "decision": "continue",
                "message": "\n".join(msg_parts)
            }))
        else:
            print(json.dumps({"decision": "continue"}))

    if __name__ == "__main__":
        main()

except Exception:
    print(json.dumps({"decision": "continue"}))
