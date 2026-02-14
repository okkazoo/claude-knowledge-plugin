#!/usr/bin/env python3
"""
scan_repo.py - One-off repo scanner for Echo setup

Walks git-tracked files, extracts top-level code structures, and
pre-populates structures.jsonl so Echo has context from the first prompt.

Designed to run once when adding Echo to an existing repo.
"""

import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

from config import get_worklog_dir, log_verbose


MAX_STRUCTURES = 200

# Directories to skip entirely
SKIP_DIRS = {
    "test", "tests", "__tests__", "__test__", "spec", "specs",
    "node_modules", "vendor", "dist", "build", "out", "target",
    "__pycache__", ".git", ".svn", ".hg", "coverage",
    ".next", ".nuxt", ".output", "venv", "env", ".venv",
    ".tox", "eggs", ".eggs", "site-packages",
}

# File patterns to skip
SKIP_FILE_PATTERNS = [
    re.compile(r"test[_.]"),
    re.compile(r"[_.]test\."),
    re.compile(r"[_.]spec\."),
    re.compile(r"\.min\."),
    re.compile(r"\.d\.ts$"),
    re.compile(r"__init__\.py$"),
    re.compile(r"setup\.py$"),
    re.compile(r"conftest\.py$"),
]

# Supported extensions
SUPPORTED_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".mts", ".cts", ".mjs", ".cjs"}

# Top-level-only patterns — more selective than capture_structure.py
# These only match structures worth indexing for navigation
SCAN_PATTERNS = {
    ".py": [
        # Only unindented (top-level) definitions
        (r"^class\s+(\w+)", "class"),
        (r"^def\s+(\w+)", "function"),
        (r"^async\s+def\s+(\w+)", "async_function"),
    ],
    ".ts": [
        (r"^export\s+class\s+(\w+)", "class"),
        (r"^export\s+interface\s+(\w+)", "interface"),
        (r"^export\s+type\s+(\w+)", "type"),
        (r"^export\s+(?:async\s+)?function\s+(\w+)", "function"),
        (r"^export\s+const\s+(\w+)\s*=\s*(?:async\s*)?\(", "function"),
        (r"^class\s+(\w+)", "class"),
        (r"^interface\s+(\w+)", "interface"),
    ],
    ".tsx": [
        (r"^export\s+class\s+(\w+)", "class"),
        (r"^export\s+interface\s+(\w+)", "interface"),
        (r"^export\s+type\s+(\w+)", "type"),
        (r"^export\s+(?:async\s+)?function\s+(\w+)", "function"),
        (r"^export\s+const\s+(\w+)\s*[=:]\s*(?:React\.)?(?:FC|memo|forwardRef)", "component"),
        (r"^export\s+const\s+(\w+)\s*=\s*\([^)]*\)\s*(?:=>|:)", "component"),
        (r"^export\s+default\s+function\s+(\w+)", "component"),
        (r"^class\s+(\w+)", "class"),
    ],
    ".js": [
        (r"^class\s+(\w+)", "class"),
        (r"^export\s+class\s+(\w+)", "class"),
        (r"^export\s+(?:async\s+)?function\s+(\w+)", "function"),
        (r"^export\s+const\s+(\w+)\s*=\s*(?:async\s*)?\(", "function"),
    ],
    ".jsx": [
        (r"^class\s+(\w+)", "class"),
        (r"^export\s+class\s+(\w+)", "class"),
        (r"^export\s+(?:async\s+)?function\s+(\w+)", "function"),
        (r"^export\s+default\s+function\s+(\w+)", "component"),
        (r"^export\s+const\s+(\w+)\s*=\s*\([^)]*\)\s*=>", "component"),
    ],
    ".go": [
        (r"^type\s+(\w+)\s+struct", "struct"),
        (r"^type\s+(\w+)\s+interface", "interface"),
        # Only exported functions (capitalized)
        (r"^func\s+([A-Z]\w*)\s*\(", "function"),
    ],
    ".rs": [
        (r"^pub\s+struct\s+(\w+)", "struct"),
        (r"^pub\s+enum\s+(\w+)", "enum"),
        (r"^pub\s+trait\s+(\w+)", "trait"),
        (r"^pub\s+(?:async\s+)?fn\s+(\w+)", "function"),
        (r"^impl(?:<[^>]+>)?\s+(\w+)", "impl"),
    ],
}

# Extension aliases
EXTENSION_ALIASES = {
    ".mts": ".ts",
    ".cts": ".ts",
    ".mjs": ".js",
    ".cjs": ".js",
}


def get_git_files(project_dir: str) -> List[str]:
    """Get list of git-tracked files."""
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True, text=True, cwd=project_dir,
            timeout=30
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except Exception:
        pass
    return []


def should_skip_file(rel_path: str) -> bool:
    """Check if a file should be skipped."""
    parts = Path(rel_path).parts

    # Check directory components
    for part in parts[:-1]:  # All but the filename
        if part.lower() in SKIP_DIRS:
            return True

    # Check filename patterns
    filename = parts[-1].lower()
    for pattern in SKIP_FILE_PATTERNS:
        if pattern.search(filename):
            return True

    return False


def get_patterns(file_path: str) -> List[Tuple[str, str]]:
    """Get scan patterns for a file extension."""
    ext = Path(file_path).suffix.lower()
    ext = EXTENSION_ALIASES.get(ext, ext)
    return SCAN_PATTERNS.get(ext, [])


def scan_file(file_path: str, project_dir: str) -> List[Dict]:
    """Scan a single file for top-level structures."""
    full_path = os.path.join(project_dir, file_path)
    patterns = get_patterns(file_path)
    if not patterns:
        return []

    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return []

    # For Python, only match truly unindented lines
    ext = Path(file_path).suffix.lower()
    ext = EXTENSION_ALIASES.get(ext, ext)
    is_python = ext == ".py"

    structures = []
    seen = set()

    for line in content.split("\n"):
        # For Python: skip indented lines (methods, nested functions)
        if is_python and line and line[0] in (" ", "\t"):
            continue

        stripped = line.strip()
        for pattern, struct_type in patterns:
            match = re.match(pattern, stripped)
            if match:
                name = match.group(1)
                # Skip private/dunder in Python
                if is_python and name.startswith("_"):
                    continue
                key = (name, struct_type)
                if key not in seen:
                    seen.add(key)
                    structures.append({
                        "name": name,
                        "type": struct_type,
                    })

    return structures


def prioritize_structures(
    by_dir: Dict[str, List[Dict]],
    max_total: int
) -> Dict[str, List[Dict]]:
    """
    Distribute structure budget across directories for breadth.
    Prioritizes: classes > interfaces/types > functions.
    """
    if not by_dir:
        return {}

    # Count total
    total = sum(len(structs) for structs in by_dir.values())
    if total <= max_total:
        return by_dir  # All fit

    # Type priority: lower = keep first
    type_priority = {
        "class": 0, "struct": 0, "trait": 0, "enum": 0,
        "interface": 1, "type": 1, "impl": 1,
        "component": 2,
        "function": 3, "async_function": 3, "arrow_function": 4,
    }

    # Allocate proportionally per directory, minimum 1
    dir_count = len(by_dir)
    per_dir = max(1, max_total // dir_count)

    result = {}
    remaining_budget = max_total

    for directory in sorted(by_dir.keys()):
        structs = by_dir[directory]
        # Sort by priority
        structs.sort(key=lambda s: type_priority.get(s.get("type", ""), 5))
        # Take up to per_dir, but don't exceed remaining budget
        take = min(len(structs), per_dir, remaining_budget)
        if take > 0:
            result[directory] = structs[:take]
            remaining_budget -= take

        if remaining_budget <= 0:
            break

    return result


def main():
    try:
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

        # Check for --full flag
        full_scan = "--full" in sys.argv

        # Get git-tracked files
        files = get_git_files(project_dir)
        if not files:
            print("No git-tracked files found. Is this a git repository?", file=sys.stderr)
            return

        # Filter to supported, non-skipped files
        scan_files = []
        for f in files:
            ext = Path(f).suffix.lower()
            ext = EXTENSION_ALIASES.get(ext, ext)
            if ext in SUPPORTED_EXTENSIONS and not should_skip_file(f):
                scan_files.append(f)

        if not scan_files:
            print("No supported source files found to scan.", file=sys.stderr)
            return

        print(f"Scanning {len(scan_files)} files...", file=sys.stderr)

        # Scan all files
        all_structures: Dict[str, List[Dict]] = defaultdict(list)
        file_structures: Dict[str, List[Dict]] = {}

        for rel_path in scan_files:
            structs = scan_file(rel_path, project_dir)
            if structs:
                file_structures[rel_path] = structs
                directory = str(Path(rel_path).parent)
                if directory == ".":
                    directory = "(root)"
                for s in structs:
                    s["file"] = rel_path
                    all_structures[directory].append(s)

        total_found = sum(len(s) for s in all_structures.values())
        max_structs = MAX_STRUCTURES * 2 if full_scan else MAX_STRUCTURES

        # Prioritize for breadth
        selected = prioritize_structures(all_structures, max_structs)

        # Write to structures.jsonl
        worklog_dir = get_worklog_dir()
        structures_file = worklog_dir / "structures.jsonl"


        written = 0

        # Preserve existing entries (from manual work)
        existing_entries = []
        if structures_file.exists():
            with open(structures_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            existing_entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

        # Build set of existing (file, name) pairs to avoid duplicates
        existing_keys = {(e.get("file", ""), e.get("name", "")) for e in existing_entries}

        with open(structures_file, "a", encoding="utf-8") as f:
            for directory, structs in sorted(selected.items()):
                for s in structs:
                    key = (s["file"], s["name"])
                    if key in existing_keys:
                        continue

                    # Build path keywords
                    path_keywords = []
                    for part in Path(s["file"]).parts:
                        stem = Path(part).stem.lower()
                        if stem and len(stem) >= 2:
                            path_keywords.append(stem)

                    entry = {
                        "file": s["file"],
                        "name": s["name"],
                        "type": s["type"],
                        "task_hint": "repo scan",
                        "path_keywords": path_keywords,
                        "operation": "scanned",
                    }
                    f.write(json.dumps(entry) + "\n")
                    written += 1

        # Summary
        selected_total = sum(len(s) for s in selected.values())
        dir_count = len(selected)

        print(f"✓ Scanned: {total_found} structures found across {len(all_structures)} directories", file=sys.stderr)
        if total_found > selected_total:
            print(f"  Kept {selected_total} (capped for token efficiency, use --full for {min(total_found, max_structs * 2)})", file=sys.stderr)
        print(f"  {written} new structures added ({len(existing_keys)} already known)", file=sys.stderr)
        print(f"  Covering {dir_count} directories", file=sys.stderr)

        # Output for hook consumption (if run as part of a command)
        result = {
            "scanned_files": len(scan_files),
            "structures_found": total_found,
            "structures_kept": selected_total,
            "structures_new": written,
            "directories": dir_count,
        }
        print(json.dumps(result))

    except Exception as e:
        print(f"Scan error: {e}", file=sys.stderr)
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
