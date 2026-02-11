#!/usr/bin/env python
"""
oKode Frontmatter Stamping Hook

After Write or Edit on source files, adds/updates an oKode CONTEXT
comment block at the top of the file, summarizing the file's role
and edges from the code graph.

Exit 0 always — never block tool execution.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Source file extensions eligible for frontmatter
SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".svelte",
}

# Extensions that use Python-style # comments
HASH_COMMENT_EXTS = {".py"}

# Extensions that use JS/TS-style /** */ block comments
BLOCK_COMMENT_EXTS = {".js", ".ts", ".tsx", ".jsx", ".vue", ".svelte"}

# Ring label mapping
RING_LABELS = {
    0: "Core",
    1: "Core",
    2: "Adjacent",
    3: "Adjacent",
    4: "Infrastructure",
    5: "Infrastructure",
}

# Regex patterns for existing oKode CONTEXT blocks
HASH_CONTEXT_RE = re.compile(
    r"^(#!.*\n)?(\s*\n)?"  # optional shebang + blank line
    r"(# oKode CONTEXT.*?# Last updated:.*?\n)",
    re.DOTALL,
)

BLOCK_CONTEXT_RE = re.compile(
    r"^(['\"]use strict['\"];?\s*\n)?"  # optional "use strict"
    r"(\s*\n)?"
    r"(/\*\*\s*\n\s*\* oKode CONTEXT.*?\*/\s*\n)",
    re.DOTALL,
)


def classify_node(node: dict) -> str:
    """Determine the type label for a node."""
    node_type = node.get("type", "")
    if node_type:
        return node_type
    # Fallback heuristics based on file path
    path = node.get("file", "")
    if "route" in path.lower() or "router" in path.lower():
        return "router"
    if "task" in path.lower() or "worker" in path.lower():
        return "task"
    if "service" in path.lower():
        return "service"
    return "script"


def build_python_frontmatter(node: dict, edges: list, graph: dict) -> str:
    """Build a # comment frontmatter block for Python files."""
    lines = [
        "# oKode CONTEXT — auto-generated, do not edit manually",
    ]

    node_type = classify_node(node)
    lines.append(f"# Type: {node_type}")

    # Endpoint (if present on the node)
    endpoint = node.get("endpoint", "")
    if endpoint:
        method = node.get("method", "GET").upper()
        lines.append(f"# Endpoint: {method} {endpoint}")

    # Categorize edges
    reads = []
    writes = []
    calls = []
    used_by = []

    file_path = node.get("file", "")
    nodes_by_id = {n.get("id", ""): n for n in graph.get("nodes", [])}

    for edge in edges:
        edge_type = edge.get("type", "").lower()
        source = edge.get("source", "")
        target = edge.get("target", "")

        if edge_type in ("reads", "read"):
            target_node = nodes_by_id.get(target, {})
            reads.append(target_node.get("label", target))
        elif edge_type in ("writes", "write"):
            target_node = nodes_by_id.get(target, {})
            writes.append(target_node.get("label", target))
        elif edge_type in ("calls", "call", "http", "fetch"):
            target_node = nodes_by_id.get(target, {})
            calls.append(target_node.get("label", target))
        elif edge_type in ("imports", "import", "uses", "use"):
            if target == node.get("id", ""):
                source_node = nodes_by_id.get(source, {})
                used_by.append(source_node.get("label", source))

    if reads:
        lines.append(f"# Reads: {', '.join(reads[:5])}")
    if writes:
        lines.append(f"# Writes: {', '.join(writes[:5])}")
    if calls:
        lines.append(f"# Calls: {', '.join(calls[:5])}")
    if used_by:
        lines.append(f"# Used by: {', '.join(used_by[:5])}")

    # Ring
    ring = node.get("ring", "")
    if ring != "":
        try:
            ring_num = int(ring)
            ring_label = RING_LABELS.get(ring_num, "")
            lines.append(f"# Ring: {ring_num} ({ring_label})")
        except (ValueError, TypeError):
            lines.append(f"# Ring: {ring}")

    lines.append(f"# Last updated: {datetime.now(timezone.utc).isoformat()}")

    # Enforce 15-line limit
    lines = lines[:15]

    return "\n".join(lines) + "\n"


def build_js_frontmatter(node: dict, edges: list, graph: dict) -> str:
    """Build a /** */ block comment frontmatter for JS/TS files."""
    inner_lines = [
        " * oKode CONTEXT — auto-generated, do not edit manually",
    ]

    component = node.get("label", node.get("name", ""))
    if component:
        inner_lines.append(f" * Component: {component}")

    # Categorize edges
    fetches = []
    renders = []

    nodes_by_id = {n.get("id", ""): n for n in graph.get("nodes", [])}

    for edge in edges:
        edge_type = edge.get("type", "").lower()
        target = edge.get("target", "")
        source = edge.get("source", "")

        if edge_type in ("fetch", "fetches", "http", "calls", "call"):
            target_node = nodes_by_id.get(target, {})
            fetches.append(target_node.get("label", target))
        elif edge_type in ("renders", "render", "imports", "import", "uses", "use"):
            if source == node.get("id", ""):
                target_node = nodes_by_id.get(target, {})
                renders.append(target_node.get("label", target))

    if fetches:
        inner_lines.append(f" * Fetches: {', '.join(fetches[:5])}")
    if renders:
        inner_lines.append(f" * Renders: {', '.join(renders[:5])}")

    # Ring
    ring = node.get("ring", "")
    if ring != "":
        try:
            ring_num = int(ring)
            ring_label = RING_LABELS.get(ring_num, "")
            inner_lines.append(f" * Ring: {ring_num} ({ring_label})")
        except (ValueError, TypeError):
            inner_lines.append(f" * Ring: {ring}")

    inner_lines.append(f" * Last updated: {datetime.now(timezone.utc).isoformat()}")

    # Enforce 15-line limit (including the /** and */ lines)
    inner_lines = inner_lines[:13]

    return "/**\n" + "\n".join(inner_lines) + "\n */\n"


def find_node_for_file(graph: dict, file_path: str) -> dict | None:
    """Find the graph node matching this file path."""
    # Normalize the path for comparison
    target = Path(file_path).resolve()

    for node in graph.get("nodes", []):
        node_file = node.get("file", "")
        if not node_file:
            continue
        try:
            if Path(node_file).resolve() == target:
                return node
        except Exception:
            # Also try simple string matching
            if node_file.replace("\\", "/") == str(target).replace("\\", "/"):
                return node
    return None


def find_edges_for_node(graph: dict, node_id: str) -> list:
    """Find all edges where this node is source or target."""
    edges = []
    for edge in graph.get("edges", []):
        if edge.get("source") == node_id or edge.get("target") == node_id:
            edges.append(edge)
    return edges


def insert_frontmatter_python(content: str, frontmatter: str) -> str:
    """Insert or replace frontmatter in a Python file."""
    # Check for existing oKode CONTEXT block
    # Pattern: consecutive lines starting with "# oKode CONTEXT" through "# Last updated:"
    lines = content.split("\n")
    in_block = False
    block_start = None
    block_end = None

    # Skip shebang line
    start_search = 0
    if lines and lines[0].startswith("#!"):
        start_search = 1
        # Skip blank line after shebang
        if len(lines) > 1 and lines[1].strip() == "":
            start_search = 2

    for i in range(start_search, len(lines)):
        line = lines[i]
        if "oKode CONTEXT" in line and line.strip().startswith("#"):
            in_block = True
            block_start = i
        if in_block and "Last updated:" in line:
            block_end = i + 1
            break

    if block_start is not None and block_end is not None:
        # Replace existing block
        before = lines[:block_start]
        after = lines[block_end:]
        # Remove blank line after old block if present
        if after and after[0].strip() == "":
            after = after[1:]
        new_content = "\n".join(before) + ("\n" if before else "")
        new_content += frontmatter + "\n"
        new_content += "\n".join(after)
        return new_content

    # No existing block — insert after shebang
    if start_search > 0:
        before = lines[:start_search]
        after = lines[start_search:]
        return "\n".join(before) + "\n" + frontmatter + "\n" + "\n".join(after)
    else:
        return frontmatter + "\n" + content


def insert_frontmatter_js(content: str, frontmatter: str) -> str:
    """Insert or replace frontmatter in a JS/TS file."""
    # Check for existing oKode CONTEXT block
    match = re.search(
        r"/\*\*\s*\n\s*\* oKode CONTEXT.*?\*/\s*\n",
        content,
        re.DOTALL,
    )

    if match:
        # Replace existing block
        return content[: match.start()] + frontmatter + "\n" + content[match.end():]

    # No existing block — insert at top, after "use strict" if present
    lines = content.split("\n")
    insert_at = 0

    if lines:
        first = lines[0].strip()
        if first.startswith(("'use strict'", '"use strict"')):
            insert_at = 1
            # Skip blank line after use strict
            if len(lines) > 1 and lines[1].strip() == "":
                insert_at = 2

    before = lines[:insert_at]
    after = lines[insert_at:]
    result = ""
    if before:
        result = "\n".join(before) + "\n"
    result += frontmatter + "\n"
    result += "\n".join(after)
    return result


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    # Only act on Write or Edit tool invocations
    tool_name = input_data.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        sys.exit(0)

    # Extract the file path
    tool_input = input_data.get("tool_input", {})
    file_path_str = tool_input.get("file_path", "")
    if not file_path_str:
        sys.exit(0)

    file_path = Path(file_path_str)
    ext = file_path.suffix.lower()

    # Only process source files
    if ext not in SOURCE_EXTENSIONS:
        sys.exit(0)

    # Determine project directory
    project_dir = Path(input_data.get("cwd", ".")).resolve()
    graph_path = project_dir / ".okode" / "graph.json"

    # If no graph exists, nothing to stamp
    if not graph_path.is_file():
        sys.exit(0)

    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except Exception:
        sys.exit(0)

    # Find the node for this file
    node = find_node_for_file(graph, file_path_str)
    if node is None:
        # File not in graph yet — skip frontmatter stamping
        sys.exit(0)

    node_id = node.get("id", "")
    edges = find_edges_for_node(graph, node_id)

    # Build the frontmatter
    if ext in HASH_COMMENT_EXTS:
        frontmatter = build_python_frontmatter(node, edges, graph)
    elif ext in BLOCK_COMMENT_EXTS:
        frontmatter = build_js_frontmatter(node, edges, graph)
    else:
        sys.exit(0)

    # Read the current file, insert/replace frontmatter, write back
    try:
        resolved_path = Path(file_path_str)
        if not resolved_path.is_absolute():
            resolved_path = project_dir / resolved_path
        resolved_path = resolved_path.resolve()

        if not resolved_path.is_file():
            sys.exit(0)

        content = resolved_path.read_text(encoding="utf-8", errors="replace")

        if ext in HASH_COMMENT_EXTS:
            new_content = insert_frontmatter_python(content, frontmatter)
        else:
            new_content = insert_frontmatter_js(content, frontmatter)

        # Only write if content actually changed
        if new_content != content:
            resolved_path.write_text(new_content, encoding="utf-8")

    except Exception as exc:
        print(f"oKode: frontmatter error — {exc}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never crash, never block
        sys.exit(0)
