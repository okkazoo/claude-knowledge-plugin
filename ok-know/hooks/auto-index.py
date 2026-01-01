#!/usr/bin/env python
"""
PostToolUse Hook: Auto-Index
Updates coderef.json when source code files are modified.
"""

import json
import sys
import re
from pathlib import Path
from datetime import datetime

CODE_EXTENSIONS = {
    '.py', '.js', '.ts', '.tsx', '.jsx',
    '.java', '.go', '.rs', '.rb', '.php',
    '.c', '.cpp', '.h', '.hpp', '.cs'
}

CODE_PATTERNS = [
    (r'^def\s+(\w+)\s*\(', 'function'),
    (r'^async\s+def\s+(\w+)\s*\(', 'async function'),
    (r'^class\s+(\w+)', 'class'),
    (r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(', 'function'),
    (r'^(?:export\s+)?class\s+(\w+)', 'class'),
    (r'^func\s+(\w+)\s*\(', 'function'),
    (r'^type\s+(\w+)\s+struct', 'struct'),
]


def extract_code_refs(filepath):
    """Extract function/class names and line numbers from source code."""
    refs = []
    try:
        with open(filepath, 'r', errors='ignore') as f:
            lines = f.readlines()
    except Exception:
        return refs

    for i, line in enumerate(lines, 1):
        stripped = line.lstrip()
        if not stripped or stripped.startswith('#') or stripped.startswith('//'):
            continue

        for pattern, sym_type in CODE_PATTERNS:
            match = re.match(pattern, stripped)
            if match:
                name = match.group(1)
                if name.startswith('_') and name != '__init__':
                    continue
                refs.append({
                    'name': name,
                    'type': sym_type,
                    'line': i
                })
                break

    return refs


def update_coderef_json(filepath, refs):
    """Update coderef.json with refs for the given file."""
    coderef_path = Path('.claude/knowledge/coderef.json')

    if coderef_path.exists():
        try:
            data = json.loads(coderef_path.read_text())
        except (json.JSONDecodeError, Exception):
            data = {'version': 1, 'updated': None, 'files': {}}
    else:
        data = {'version': 1, 'updated': None, 'files': {}}

    try:
        rel_path = str(Path(filepath).resolve().relative_to(Path.cwd()))
    except ValueError:
        rel_path = filepath
    rel_path = rel_path.replace('\\', '/')

    now = datetime.now().isoformat()
    if refs:
        data['files'][rel_path] = {
            'modified': now,
            'symbols': refs
        }
    elif rel_path in data['files']:
        del data['files'][rel_path]

    data['updated'] = now
    coderef_path.write_text(json.dumps(data, indent=2))
    return len(refs)


def is_source_file(filepath):
    """Check if file is a source code file we should index."""
    path = Path(filepath)
    if '.claude' in path.parts:
        return False
    skip_dirs = {'node_modules', 'venv', '.venv', '__pycache__', '.git', 'dist', 'build'}
    if any(d in path.parts for d in skip_dirs):
        return False
    return path.suffix.lower() in CODE_EXTENSIONS


def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    try:
        tool_input = input_data.get('tool_input', {})
        file_path = tool_input.get('file_path', '')

        if not file_path:
            sys.exit(0)

        if is_source_file(file_path):
            refs = extract_code_refs(file_path)
            count = update_coderef_json(file_path, refs)
            if count > 0:
                print(f"Code index updated: {count} symbols in {Path(file_path).name}")
            sys.exit(0)

        if '.claude/knowledge/' not in file_path:
            sys.exit(0)

        if not file_path.endswith('.md'):
            sys.exit(0)

        if '_meta.md' in file_path:
            sys.exit(0)

        print(f"Knowledge updated: {Path(file_path).name}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
