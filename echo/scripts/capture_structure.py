#!/usr/bin/env python3
"""
capture_structure.py - Captures class/function definitions on Write/Edit

Parses file content for structural elements (classes, functions, etc.)
and logs them for later consolidation.
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from config import get_worklog_dir, log_verbose


def get_task_keywords() -> str:
    """Extract keywords from current task for correlation."""
    try:
        worklog_dir = get_worklog_dir()
        tasks_file = worklog_dir / ".current_tasks"

        if not tasks_file.exists():
            return ""

        # Read most recent task
        with open(tasks_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if not lines:
            return ""

        # Parse most recent task
        import json
        last_task = json.loads(lines[-1].strip())
        prompt = last_task.get("prompt", "")

        if not prompt:
            return ""

        # Extract meaningful keywords (skip common words)
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "must", "shall", "can", "need", "to", "of",
            "in", "for", "on", "with", "at", "by", "from", "as", "into", "through",
            "and", "or", "but", "if", "then", "else", "when", "where", "why", "how",
            "all", "each", "every", "both", "few", "more", "most", "other", "some",
            "such", "no", "not", "only", "same", "so", "than", "too", "very", "just",
            "also", "now", "here", "there", "this", "that", "these", "those", "it",
            "its", "i", "me", "my", "we", "our", "you", "your", "he", "she", "they",
            "them", "what", "which", "who", "whom", "get", "make", "like", "want",
            "could", "please", "change", "add", "update", "fix", "modify", "create",
        }

        # Tokenize and filter
        import re
        words = re.findall(r'\b[a-zA-Z]{3,}\b', prompt.lower())
        keywords = [w for w in words if w not in stop_words]

        # Return top 3-4 keywords
        return " ".join(keywords[:4])

    except Exception:
        return ""


# Patterns to detect structural elements by file extension
PATTERNS = {
    # Python
    ".py": [
        (r"^class\s+(\w+)", "class"),
        (r"^def\s+(\w+)", "function"),
        (r"^async\s+def\s+(\w+)", "async_function"),
    ],
    # TypeScript/JavaScript
    ".ts": [
        (r"^export\s+class\s+(\w+)", "class"),
        (r"^class\s+(\w+)", "class"),
        (r"^export\s+interface\s+(\w+)", "interface"),
        (r"^interface\s+(\w+)", "interface"),
        (r"^export\s+type\s+(\w+)", "type"),
        (r"^type\s+(\w+)", "type"),
        (r"^export\s+(?:async\s+)?function\s+(\w+)", "function"),
        (r"^(?:async\s+)?function\s+(\w+)", "function"),
        (r"^export\s+const\s+(\w+)\s*=\s*(?:async\s*)?\(", "arrow_function"),
        (r"^const\s+(\w+)\s*=\s*(?:async\s*)?\(", "arrow_function"),
    ],
    ".tsx": [
        (r"^export\s+class\s+(\w+)", "class"),
        (r"^class\s+(\w+)", "class"),
        (r"^export\s+interface\s+(\w+)", "interface"),
        (r"^interface\s+(\w+)", "interface"),
        (r"^export\s+type\s+(\w+)", "type"),
        (r"^type\s+(\w+)", "type"),
        (r"^export\s+(?:async\s+)?function\s+(\w+)", "function"),
        (r"^(?:async\s+)?function\s+(\w+)", "function"),
        (r"^export\s+const\s+(\w+)\s*[=:]\s*(?:React\.)?(?:FC|memo|forwardRef)", "component"),
        (r"^const\s+(\w+)\s*[=:]\s*(?:React\.)?(?:FC|memo|forwardRef)", "component"),
        (r"^export\s+const\s+(\w+)\s*=\s*\([^)]*\)\s*(?:=>|:)", "component"),
        (r"^const\s+(\w+)\s*=\s*\([^)]*\)\s*(?:=>|:)", "arrow_function"),
    ],
    ".js": [
        (r"^class\s+(\w+)", "class"),
        (r"^export\s+class\s+(\w+)", "class"),
        (r"^(?:async\s+)?function\s+(\w+)", "function"),
        (r"^export\s+(?:async\s+)?function\s+(\w+)", "function"),
        (r"^const\s+(\w+)\s*=\s*(?:async\s*)?\(", "arrow_function"),
        (r"^export\s+const\s+(\w+)\s*=\s*(?:async\s*)?\(", "arrow_function"),
    ],
    ".jsx": [
        (r"^class\s+(\w+)", "class"),
        (r"^export\s+class\s+(\w+)", "class"),
        (r"^(?:async\s+)?function\s+(\w+)", "function"),
        (r"^export\s+(?:async\s+)?function\s+(\w+)", "function"),
        (r"^const\s+(\w+)\s*=\s*\([^)]*\)\s*=>", "component"),
        (r"^export\s+const\s+(\w+)\s*=\s*\([^)]*\)\s*=>", "component"),
    ],
    # Go
    ".go": [
        (r"^type\s+(\w+)\s+struct", "struct"),
        (r"^type\s+(\w+)\s+interface", "interface"),
        (r"^func\s+(\w+)\s*\(", "function"),
        (r"^func\s+\([^)]+\)\s+(\w+)\s*\(", "method"),
    ],
    # Rust
    ".rs": [
        (r"^pub\s+struct\s+(\w+)", "struct"),
        (r"^struct\s+(\w+)", "struct"),
        (r"^pub\s+enum\s+(\w+)", "enum"),
        (r"^enum\s+(\w+)", "enum"),
        (r"^pub\s+trait\s+(\w+)", "trait"),
        (r"^trait\s+(\w+)", "trait"),
        (r"^pub\s+(?:async\s+)?fn\s+(\w+)", "function"),
        (r"^(?:async\s+)?fn\s+(\w+)", "function"),
        (r"^impl(?:<[^>]+>)?\s+(\w+)", "impl"),
    ],
}

# Also check these extensions with their base patterns
EXTENSION_ALIASES = {
    ".mts": ".ts",
    ".cts": ".ts",
    ".mjs": ".js",
    ".cjs": ".js",
}


def get_patterns_for_file(file_path: str) -> List[tuple]:
    """Get regex patterns for the given file extension."""
    ext = Path(file_path).suffix.lower()
    ext = EXTENSION_ALIASES.get(ext, ext)
    return PATTERNS.get(ext, [])


def extract_structures(content: str, file_path: str) -> List[Dict[str, Any]]:
    """Extract structural elements from file content."""
    patterns = get_patterns_for_file(file_path)
    if not patterns:
        return []

    structures = []
    seen = set()  # Avoid duplicates

    for line in content.split("\n"):
        stripped = line.strip()
        for pattern, struct_type in patterns:
            match = re.match(pattern, stripped)
            if match:
                name = match.group(1)
                key = (name, struct_type)
                if key not in seen:
                    seen.add(key)
                    structures.append({
                        "name": name,
                        "type": struct_type,
                    })

    return structures


def get_content_from_hook_data(data: Dict) -> Optional[str]:
    """Extract content by reading the full file from disk.

    PostToolUse fires AFTER the write, so the file is current.
    Reading the full file captures ALL structures, not just the edited snippet.
    """
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    # For ALL tools, read the actual file from disk
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception:
            pass

    # Fallback to tool input content
    if tool_name == "Write":
        return tool_input.get("content", "")
    elif tool_name == "Edit":
        return tool_input.get("new_string", "")
    elif tool_name == "MultiEdit":
        edits = tool_input.get("edits", [])
        return "\n".join(e.get("new_string", "") for e in edits)

    return None


def main():
    try:
        input_data = sys.stdin.read()
        if not input_data.strip():
            return

        data = json.loads(input_data)

        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {})

        if tool_name not in ("Write", "Edit", "MultiEdit"):
            return

        file_path = tool_input.get("file_path", "")
        if not file_path:
            return

        # Check if this file type is supported
        if not get_patterns_for_file(file_path):
            return

        content = get_content_from_hook_data(data)
        if not content:
            return

        structures = extract_structures(content, file_path)
        if not structures:
            return

        # Make path relative
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
        try:
            rel_path = os.path.relpath(file_path, project_dir)
            if not rel_path.startswith(".."):
                file_path = rel_path
        except ValueError:
            pass

        # Log each structure with task correlation
        worklog_dir = get_worklog_dir()
        structures_file = worklog_dir / "structures.jsonl"

        timestamp = datetime.now().isoformat()
        task_hint = get_task_keywords()

        # Build path keywords from directory segments
        path_keywords = []
        for part in Path(file_path).parts:
            stem = Path(part).stem.lower()
            if stem and len(stem) >= 2:
                path_keywords.append(stem)

        with open(structures_file, "a", encoding="utf-8") as f:
            for struct in structures:
                entry = {
                    "ts": timestamp,
                    "file": file_path,
                    "name": struct["name"],
                    "type": struct["type"],
                    "task_hint": task_hint,
                    "path_keywords": path_keywords,
                    "operation": "created" if tool_name == "Write" else "modified",
                }
                f.write(json.dumps(entry) + "\n")

        # Verbose output
        names = ", ".join(s["name"] for s in structures[:3])
        if len(structures) > 3:
            names += f" +{len(structures) - 3} more"
        log_verbose(f"✓ Learned: {names} in {Path(file_path).name}")

    except Exception:
        # Fail silently
        pass


if __name__ == "__main__":
    main()
