#!/usr/bin/env python3
"""
Context Manager: Summarize large files and data.
Used by context-manager skill to reduce context consumption.
"""

import sys
import json
import re
from collections import Counter
from pathlib import Path


def summarize_log_file(filepath: str, max_samples: int = 5) -> dict:
    """Summarize a log file without loading it all into memory."""

    stats = {
        "total_lines": 0,
        "errors": [],
        "warnings": [],
        "error_count": 0,
        "warning_count": 0,
        "info_count": 0,
        "first_timestamp": None,
        "last_timestamp": None,
    }

    error_types = Counter()

    timestamp_pattern = re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}')

    with open(filepath, 'r', errors='ignore') as f:
        for line in f:
            stats["total_lines"] += 1

            # Extract timestamp
            ts_match = timestamp_pattern.search(line)
            if ts_match:
                ts = ts_match.group()
                if not stats["first_timestamp"]:
                    stats["first_timestamp"] = ts
                stats["last_timestamp"] = ts

            # Categorize
            line_upper = line.upper()
            if 'ERROR' in line_upper:
                stats["error_count"] += 1
                if len(stats["errors"]) < max_samples:
                    stats["errors"].append(line.strip()[:200])
                # Track error types
                if ':' in line:
                    error_type = line.split(':')[0].strip()[-50:]
                    error_types[error_type] += 1
            elif 'WARN' in line_upper:
                stats["warning_count"] += 1
                if len(stats["warnings"]) < max_samples:
                    stats["warnings"].append(line.strip()[:200])
            else:
                stats["info_count"] += 1

    stats["top_error_types"] = error_types.most_common(5)

    return stats


def summarize_json_file(filepath: str) -> dict:
    """Summarize a JSON file structure without full content."""

    with open(filepath, 'r') as f:
        data = json.load(f)

    def describe_structure(obj, max_depth=2, depth=0):
        if depth >= max_depth:
            return f"<{type(obj).__name__}>"

        if isinstance(obj, dict):
            return {k: describe_structure(v, max_depth, depth+1)
                    for k in list(obj.keys())[:10]}
        elif isinstance(obj, list):
            if len(obj) == 0:
                return "[]"
            return f"[{describe_structure(obj[0], max_depth, depth+1)}] ({len(obj)} items)"
        else:
            return f"<{type(obj).__name__}>"

    return {
        "structure": describe_structure(data),
        "top_level_type": type(data).__name__,
        "size": len(str(data)),
    }


def summarize_code_file(filepath: str) -> dict:
    """Summarize a code file structure."""

    stats = {
        "total_lines": 0,
        "blank_lines": 0,
        "comment_lines": 0,
        "functions": [],
        "classes": [],
        "imports": [],
    }

    func_pattern = re.compile(r'^\s*(?:async\s+)?def\s+(\w+)')
    class_pattern = re.compile(r'^\s*class\s+(\w+)')
    import_pattern = re.compile(r'^(?:from\s+\S+\s+)?import\s+(.+)')

    with open(filepath, 'r', errors='ignore') as f:
        for line in f:
            stats["total_lines"] += 1
            stripped = line.strip()

            if not stripped:
                stats["blank_lines"] += 1
            elif stripped.startswith('#'):
                stats["comment_lines"] += 1
            else:
                func_match = func_pattern.match(line)
                if func_match:
                    stats["functions"].append(func_match.group(1))

                class_match = class_pattern.match(line)
                if class_match:
                    stats["classes"].append(class_match.group(1))

                import_match = import_pattern.match(line)
                if import_match and len(stats["imports"]) < 10:
                    stats["imports"].append(stripped)

    return stats


def format_summary(filepath: str, stats: dict) -> str:
    """Format summary for output."""

    output = [f"## Summary: {filepath}\n"]

    if "error_count" in stats:  # Log file
        output.append(f"- **Lines:** {stats['total_lines']}")
        output.append(f"- **Errors:** {stats['error_count']}")
        output.append(f"- **Warnings:** {stats['warning_count']}")
        if stats.get("first_timestamp"):
            output.append(f"- **Time range:** {stats['first_timestamp']} to {stats['last_timestamp']}")

        if stats.get("top_error_types"):
            output.append("\n### Top Error Types")
            for error_type, count in stats["top_error_types"]:
                output.append(f"- {error_type}: {count}")

        if stats.get("errors"):
            output.append("\n### Sample Errors")
            for err in stats["errors"][:3]:
                output.append(f"```\n{err}\n```")

    elif "functions" in stats:  # Code file
        output.append(f"- **Lines:** {stats['total_lines']} ({stats['blank_lines']} blank, {stats['comment_lines']} comments)")
        output.append(f"- **Classes:** {len(stats['classes'])}")
        output.append(f"- **Functions:** {len(stats['functions'])}")

        if stats.get("classes"):
            output.append(f"\n### Classes\n- " + ", ".join(stats["classes"]))
        if stats.get("functions"):
            output.append(f"\n### Functions\n- " + ", ".join(stats["functions"][:20]))

    elif "structure" in stats:  # JSON file
        output.append(f"- **Type:** {stats['top_level_type']}")
        output.append(f"- **Size:** ~{stats['size']} chars")
        output.append(f"\n### Structure\n```json\n{json.dumps(stats['structure'], indent=2)}\n```")

    return "\n".join(output)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: summarize.py <filepath>")
        sys.exit(1)

    filepath = sys.argv[1]
    path = Path(filepath)

    if not path.exists():
        print(f"File not found: {filepath}")
        sys.exit(1)

    suffix = path.suffix.lower()

    if suffix == '.json':
        stats = summarize_json_file(filepath)
    elif suffix in ('.py', '.js', '.ts', '.jsx', '.tsx'):
        stats = summarize_code_file(filepath)
    elif suffix in ('.log', '.txt') or 'log' in path.name.lower():
        stats = summarize_log_file(filepath)
    else:
        stats = summarize_code_file(filepath)  # Default to code

    print(format_summary(filepath, stats))
