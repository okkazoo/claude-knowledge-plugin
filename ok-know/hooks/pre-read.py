#!/usr/bin/env python3
"""PreToolUse Hook: Pre-Read Large File Warning

Warns when reading large files (>200 lines) without offset/limit.
Suggests searching first to find targeted line ranges.

Output format: {"continue": true, "systemMessage": "..."}
"""

import json
import sys
import os
from pathlib import Path

LARGE_FILE_THRESHOLD = 200  # lines

def count_lines(filepath):
    """Count lines in a file efficiently."""
    try:
        with open(filepath, 'rb') as f:
            return sum(1 for _ in f)
    except:
        return 0

def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except:
        print(json.dumps({"continue": True}))
        return

    tool_input = input_data.get('tool_input', {})
    file_path = tool_input.get('file_path', '')
    offset = tool_input.get('offset')
    limit = tool_input.get('limit')

    # If offset/limit provided, they're doing a targeted read - allow it
    if offset is not None or limit is not None:
        print(json.dumps({"continue": True}))
        return

    # Check if file exists and get line count
    if not file_path or not Path(file_path).exists():
        print(json.dumps({"continue": True}))
        return

    # Skip non-text files (images, binaries, etc.)
    text_extensions = {'.py', '.js', '.jsx', '.ts', '.tsx', '.css', '.html',
                       '.json', '.yml', '.yaml', '.md', '.txt', '.sh', '.cmd',
                       '.bat', '.ps1', '.xml', '.toml', '.ini', '.cfg', '.conf'}
    ext = Path(file_path).suffix.lower()
    if ext not in text_extensions:
        print(json.dumps({"continue": True}))
        return

    line_count = count_lines(file_path)

    if line_count > LARGE_FILE_THRESHOLD:
        filename = Path(file_path).name
        msg = (
            f"[!] Large file: {filename} has {line_count} lines.\n"
            f">> Consider: Grep/Glob first to find what you need, then Read with offset/limit.\n"
            f">> Example: Read(file_path=\"...\", offset=LINE, limit=50)"
        )
        print(json.dumps({
            "continue": True,
            "systemMessage": msg
        }))
    else:
        print(json.dumps({"continue": True}))

if __name__ == "__main__":
    try:
        main()
    except:
        print(json.dumps({"continue": True}))
