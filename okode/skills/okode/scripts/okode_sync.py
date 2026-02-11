#!/usr/bin/env python3
"""
okode_sync.py -- Incremental graph updater for the oKode code graph system.

Syncs the graph for changed files only, detects architectural drift,
and records diffs in the history directory.

Usage:
    python okode_sync.py --files file1.py file2.py
    python okode_sync.py --since-last
    python okode_sync.py --since-last --graph-path .okode/graph.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Attempt to import StaticAnalyzer and LLMClassifier from okode_scan.
# If okode_scan.py has not been created yet, define lightweight fallbacks
# so that okode_sync can still operate in "static-only" mode.
# ---------------------------------------------------------------------------

_SCAN_MODULE_AVAILABLE = False

try:
    # Try relative import (if used as a package)
    from . import okode_scan as _scan_mod  # type: ignore[import-not-found]
    _SCAN_MODULE_AVAILABLE = True
except (ImportError, SystemError):
    pass

if not _SCAN_MODULE_AVAILABLE:
    # Try sys.path manipulation so we can import from the same directory
    _SCRIPTS_DIR = Path(__file__).resolve().parent
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    try:
        import okode_scan as _scan_mod  # type: ignore[import-untyped,no-redef]
        _SCAN_MODULE_AVAILABLE = True
    except ImportError:
        _scan_mod = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
GraphDict = dict[str, Any]
NodeDict = dict[str, Any]
EdgeDict = dict[str, Any]
DriftWarning = dict[str, str]


# ===================================================================
# Fallback static analyser (used when okode_scan is not yet available)
# ===================================================================

class _FallbackStaticAnalyzer:
    """
    Minimal static analyser that extracts basic nodes and edges from a
    single Python/JS/TS file using AST parsing and regex patterns.

    This exists so that okode_sync can function before okode_scan.py is
    built.  Once okode_scan.py exists, the real StaticAnalyzer is used
    instead.
    """

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir

    # ------------------------------------------------------------------
    def analyze_file(self, filepath: Path) -> tuple[list[NodeDict], list[EdgeDict]]:
        """Return (nodes, edges) extracted from *filepath*."""
        import ast as _ast
        import re as _re

        rel = filepath.relative_to(self.project_dir).as_posix()
        nodes: list[NodeDict] = []
        edges: list[EdgeDict] = []

        # Always create a file node
        nodes.append({
            "id": f"file:{rel}",
            "type": "file",
            "label": filepath.name,
            "file": rel,
            "line": 1,
            "ring": self._guess_ring(rel),
            "metadata": {},
        })

        try:
            source = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return nodes, edges

        suffix = filepath.suffix.lower()
        if suffix == ".py":
            nodes_extra, edges_extra = self._analyze_python(source, rel)
        elif suffix in (".js", ".ts", ".jsx", ".tsx", ".mjs"):
            nodes_extra, edges_extra = self._analyze_js(source, rel)
        else:
            nodes_extra, edges_extra = [], []

        nodes.extend(nodes_extra)
        edges.extend(edges_extra)
        return nodes, edges

    # ------------------------------------------------------------------
    def _guess_ring(self, rel_path: str) -> int:
        parts = rel_path.lower()
        if any(k in parts for k in ("util", "lib/", "helpers/", "common/")):
            return 1
        if any(k in parts for k in ("config", "logging", "database", "db/", "infra")):
            return 2
        return 0

    # ------------------------------------------------------------------
    def _analyze_python(self, source: str, rel: str) -> tuple[list[NodeDict], list[EdgeDict]]:
        import ast as _ast
        import re as _re

        nodes: list[NodeDict] = []
        edges: list[EdgeDict] = []

        try:
            tree = _ast.parse(source)
        except SyntaxError:
            return nodes, edges

        for node in _ast.walk(tree):
            # Detect route decorators (FastAPI / Flask)
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    method, path = self._extract_route_decorator(dec)
                    if method and path:
                        nid = f"endpoint:{method}:{path}"
                        nodes.append({
                            "id": nid,
                            "type": "endpoint",
                            "label": f"{method} {path}",
                            "file": rel,
                            "line": node.lineno,
                            "ring": 0,
                            "metadata": {"method": method},
                        })
                        edges.append({
                            "source": nid,
                            "target": f"file:{rel}",
                            "type": "endpoint_handler",
                            "context": f"Handler in {rel}",
                            "file": rel,
                            "line": node.lineno,
                        })

            # Detect os.getenv / os.environ
            if isinstance(node, _ast.Call):
                func_name = self._get_call_name(node)
                if func_name in ("os.getenv", "os.environ.get"):
                    if node.args and isinstance(node.args[0], _ast.Constant):
                        env_name = str(node.args[0].value)
                        env_id = f"env_var:{env_name}"
                        nodes.append({
                            "id": env_id,
                            "type": "env_var",
                            "label": env_name,
                            "file": rel,
                            "line": node.lineno,
                            "ring": 2,
                            "metadata": {},
                        })
                        edges.append({
                            "source": f"file:{rel}",
                            "target": env_id,
                            "type": "calls",
                            "context": f"Reads env var {env_name}",
                            "file": rel,
                            "line": node.lineno,
                        })

        # Regex-based detection for common patterns
        for i, line in enumerate(source.splitlines(), 1):
            # DB collection patterns (mongo-style)
            for m in _re.finditer(r'(?:db|collection|mongo)\[?["\'](\w+)["\']', line):
                col = m.group(1)
                col_id = f"collection:{col}"
                is_write = any(w in line for w in ("insert", "update", "delete", "save", "create", "replace", "write"))
                edge_type = "db_write" if is_write else "db_read"
                nodes.append({
                    "id": col_id, "type": "collection", "label": col,
                    "file": rel, "line": i, "ring": 2, "metadata": {},
                })
                edges.append({
                    "source": f"file:{rel}", "target": col_id, "type": edge_type,
                    "context": f"{'Writes to' if is_write else 'Reads from'} {col}",
                    "file": rel, "line": i,
                })

            # External API patterns
            for m in _re.finditer(r'(?:requests|httpx|aiohttp)\.(get|post|put|patch|delete)\s*\(', line):
                api_id = f"external_api:http_{i}"
                nodes.append({
                    "id": api_id, "type": "external_api", "label": f"HTTP {m.group(1).upper()} call",
                    "file": rel, "line": i, "ring": 2, "metadata": {},
                })
                edges.append({
                    "source": f"file:{rel}", "target": api_id, "type": "api_call",
                    "context": f"External HTTP {m.group(1).upper()} call",
                    "file": rel, "line": i,
                })

        return nodes, edges

    # ------------------------------------------------------------------
    def _analyze_js(self, source: str, rel: str) -> tuple[list[NodeDict], list[EdgeDict]]:
        import re as _re

        nodes: list[NodeDict] = []
        edges: list[EdgeDict] = []

        for i, line in enumerate(source.splitlines(), 1):
            # Express route patterns
            for m in _re.finditer(r'(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*["\']([^"\']+)', line):
                method = m.group(1).upper()
                path = m.group(2)
                nid = f"endpoint:{method}:{path}"
                nodes.append({
                    "id": nid, "type": "endpoint", "label": f"{method} {path}",
                    "file": rel, "line": i, "ring": 0, "metadata": {"method": method},
                })
                edges.append({
                    "source": nid, "target": f"file:{rel}", "type": "endpoint_handler",
                    "context": f"Handler in {rel}", "file": rel, "line": i,
                })

            # process.env
            for m in _re.finditer(r'process\.env\.(\w+)', line):
                env_name = m.group(1)
                env_id = f"env_var:{env_name}"
                nodes.append({
                    "id": env_id, "type": "env_var", "label": env_name,
                    "file": rel, "line": i, "ring": 2, "metadata": {},
                })
                edges.append({
                    "source": f"file:{rel}", "target": env_id, "type": "calls",
                    "context": f"Reads env var {env_name}", "file": rel, "line": i,
                })

            # fetch / axios
            for m in _re.finditer(r'(?:fetch|axios)\s*[\.(]', line):
                api_id = f"external_api:http_{i}"
                nodes.append({
                    "id": api_id, "type": "external_api", "label": "HTTP call",
                    "file": rel, "line": i, "ring": 2, "metadata": {},
                })
                edges.append({
                    "source": f"file:{rel}", "target": api_id, "type": "api_call",
                    "context": "External HTTP call", "file": rel, "line": i,
                })

        return nodes, edges

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_route_decorator(dec) -> tuple[str | None, str | None]:
        import ast as _ast

        # @app.get("/path") or @router.post("/path")
        if isinstance(dec, _ast.Call) and isinstance(dec.func, _ast.Attribute):
            method = dec.func.attr.upper()
            if method in ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"):
                if dec.args and isinstance(dec.args[0], _ast.Constant):
                    return method, str(dec.args[0].value)
        return None, None

    @staticmethod
    def _get_call_name(node) -> str:
        import ast as _ast

        if isinstance(node.func, _ast.Attribute):
            parts = []
            obj = node.func
            while isinstance(obj, _ast.Attribute):
                parts.append(obj.attr)
                obj = obj.value  # type: ignore[assignment]
            if isinstance(obj, _ast.Name):
                parts.append(obj.id)
            return ".".join(reversed(parts))
        if isinstance(node.func, _ast.Name):
            return node.func.id
        return ""


# ===================================================================
# Fallback LLM classifier (no-op when okode_scan is missing)
# ===================================================================

class _FallbackLLMClassifier:
    """No-op LLM classifier used when okode_scan is not available."""

    def classify(
        self, filepath: Path, nodes: list[NodeDict], edges: list[EdgeDict]
    ) -> tuple[list[NodeDict], list[EdgeDict]]:
        return nodes, edges


# ===================================================================
# Helper: get the right analyser / classifier
# ===================================================================

def _get_analyzer(project_dir: Path):
    if _SCAN_MODULE_AVAILABLE and hasattr(_scan_mod, "StaticAnalyzer"):
        return _scan_mod.StaticAnalyzer(project_dir)
    return _FallbackStaticAnalyzer(project_dir)


def _get_classifier(project_dir: Path):
    if _SCAN_MODULE_AVAILABLE and hasattr(_scan_mod, "LLMClassifier"):
        return _scan_mod.LLMClassifier(project_dir)
    return _FallbackLLMClassifier()


# ===================================================================
# Graph I/O
# ===================================================================

def load_graph(graph_path: Path) -> GraphDict:
    """Load an existing graph.json or return an empty graph structure."""
    if graph_path.exists():
        return json.loads(graph_path.read_text(encoding="utf-8"))
    return {
        "metadata": {
            "project": "",
            "generated_at": "",
            "scanner_version": "1.0.0",
            "total_files_analyzed": 0,
            "analysis_duration_seconds": 0,
        },
        "nodes": [],
        "edges": [],
    }


def save_graph(graph: GraphDict, graph_path: Path) -> None:
    """Persist the graph to disk."""
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(
        json.dumps(graph, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ===================================================================
# Changed file detection
# ===================================================================

def _files_from_args(file_list: list[str], project_dir: Path) -> list[Path]:
    """Resolve explicit --files arguments to absolute paths."""
    resolved: list[Path] = []
    for f in file_list:
        p = Path(f)
        if not p.is_absolute():
            p = project_dir / p
        p = p.resolve()
        if p.is_file():
            resolved.append(p)
    return resolved


def _files_since_last(graph: GraphDict, project_dir: Path) -> list[Path]:
    """Use git diff to find files changed since the last scan timestamp."""
    last_ts = graph.get("metadata", {}).get("generated_at", "")
    git_cmd = ["git", "diff", "--name-only"]
    if last_ts:
        git_cmd.append(f"--since={last_ts}")
        # git diff --name-only HEAD works more reliably; use diff-tree or
        # diff against HEAD with a timestamp filter via log
        # Safer approach: git log --since=<ts> --name-only --pretty=format:""
        git_cmd = [
            "git", "log", "--since", last_ts,
            "--name-only", "--pretty=format:",
        ]
    else:
        # No previous scan -- treat everything tracked by git as changed
        git_cmd = ["git", "ls-files"]

    try:
        result = subprocess.run(
            git_cmd,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
        raw = result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        print("[warn] git command failed; falling back to empty changeset")
        return []

    seen: set[str] = set()
    paths: list[Path] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line in seen:
            continue
        seen.add(line)
        p = (project_dir / line).resolve()
        if p.is_file():
            paths.append(p)
    return paths


# ===================================================================
# Graph manipulation helpers
# ===================================================================

def _nodes_for_file(graph: GraphDict, rel_path: str) -> list[NodeDict]:
    return [n for n in graph["nodes"] if n.get("file") == rel_path]


def _edges_for_file(graph: GraphDict, rel_path: str) -> list[EdgeDict]:
    return [e for e in graph["edges"] if e.get("file") == rel_path]


def _remove_file_from_graph(graph: GraphDict, rel_path: str) -> tuple[list[NodeDict], list[EdgeDict]]:
    """Remove all nodes/edges associated with *rel_path* and return them."""
    old_nodes = _nodes_for_file(graph, rel_path)
    old_edges = _edges_for_file(graph, rel_path)
    old_node_ids = {n["id"] for n in old_nodes}

    graph["nodes"] = [n for n in graph["nodes"] if n.get("file") != rel_path]
    # Remove edges whose file matches OR whose source/target was an old node
    graph["edges"] = [
        e for e in graph["edges"]
        if e.get("file") != rel_path
        and e.get("source") not in old_node_ids
        and e.get("target") not in old_node_ids
    ]
    return old_nodes, old_edges


def _merge_into_graph(
    graph: GraphDict,
    new_nodes: list[NodeDict],
    new_edges: list[EdgeDict],
) -> None:
    """Merge *new_nodes* and *new_edges* into the graph, deduplicating by id."""
    existing_ids = {n["id"] for n in graph["nodes"]}
    for n in new_nodes:
        if n["id"] in existing_ids:
            # Update existing node in-place
            for i, en in enumerate(graph["nodes"]):
                if en["id"] == n["id"]:
                    graph["nodes"][i] = n
                    break
        else:
            graph["nodes"].append(n)
            existing_ids.add(n["id"])

    # Edges: deduplicate by (source, target, type, file)
    existing_edge_keys: set[tuple[str, ...]] = set()
    for e in graph["edges"]:
        key = (e.get("source", ""), e.get("target", ""), e.get("type", ""), e.get("file", ""))
        existing_edge_keys.add(key)
    for e in new_edges:
        key = (e.get("source", ""), e.get("target", ""), e.get("type", ""), e.get("file", ""))
        if key not in existing_edge_keys:
            graph["edges"].append(e)
            existing_edge_keys.add(key)


# ===================================================================
# Drift detection
# ===================================================================

def _detect_drift(
    graph: GraphDict,
    rel_path: str,
    old_nodes: list[NodeDict],
    old_edges: list[EdgeDict],
    new_nodes: list[NodeDict],
    new_edges: list[EdgeDict],
) -> list[DriftWarning]:
    """Compare old vs new nodes/edges and detect architectural drift."""
    warnings: list[DriftWarning] = []

    old_edge_set = {(e.get("type"), e.get("target")) for e in old_edges}
    new_edge_set = {(e.get("type"), e.get("target")) for e in new_edges}
    added_edges = new_edge_set - old_edge_set

    old_node_map = {n["id"]: n for n in old_nodes}
    new_node_map = {n["id"]: n for n in new_nodes}

    # 1. New external API call
    for etype, target in added_edges:
        if etype == "api_call":
            warnings.append({
                "type": "new_external_api",
                "severity": "FLAG",
                "detail": f"{rel_path} added external API call to {target}",
            })

    # 2. New DB write to previously read-only collection
    old_write_targets = {e.get("target") for e in old_edges if e.get("type") == "db_write"}
    old_read_targets = {e.get("target") for e in old_edges if e.get("type") == "db_read"}
    for etype, target in added_edges:
        if etype == "db_write" and target not in old_write_targets:
            # Check if the collection was previously read-only in the FULL graph
            graph_writers = [
                e for e in graph["edges"]
                if e.get("target") == target
                and e.get("type") == "db_write"
                and e.get("file") != rel_path
            ]
            if not graph_writers and target in old_read_targets:
                warnings.append({
                    "type": "new_db_write_to_readonly",
                    "severity": "FLAG",
                    "detail": (
                        f"{rel_path} added db_write to {target}, "
                        f"which was previously read-only for this file"
                    ),
                })

    # 3. New env var dependency
    for etype, target in added_edges:
        if target and target.startswith("env_var:"):
            old_env_targets = {
                e.get("target") for e in old_edges
                if e.get("target", "").startswith("env_var:")
            }
            if target not in old_env_targets:
                warnings.append({
                    "type": "new_env_var",
                    "severity": "FLAG",
                    "detail": f"{rel_path} added dependency on {target}",
                })

    # 4. Ring change
    for nid, new_node in new_node_map.items():
        old_node = old_node_map.get(nid)
        if old_node and old_node.get("ring") != new_node.get("ring"):
            warnings.append({
                "type": "ring_changed",
                "severity": "FLAG",
                "detail": (
                    f"{nid} ring changed from {old_node.get('ring')} "
                    f"to {new_node.get('ring')}"
                ),
            })

    # 5. Orphaned code (callers dropped to 0)
    for nid in new_node_map:
        # Count incoming edges in the full graph (edges where target == nid)
        incoming = [e for e in graph["edges"] if e.get("target") == nid]
        if not incoming and nid in old_node_map:
            # Check if the old node HAD incoming edges
            old_incoming = [
                e for e in old_edges if e.get("target") == nid
            ]
            if old_incoming:
                warnings.append({
                    "type": "orphaned_code",
                    "severity": "FLAG",
                    "detail": f"{nid} now has 0 callers (previously {len(old_incoming)})",
                })

    # 6. Circular dependency detection (DFS on the full graph)
    circ = _detect_circular_dependencies(graph, rel_path)
    for cycle in circ:
        warnings.append({
            "type": "circular_dependency",
            "severity": "BLOCK",
            "detail": f"Circular dependency detected: {' -> '.join(cycle)}",
        })

    return warnings


def _detect_circular_dependencies(graph: GraphDict, rel_path: str) -> list[list[str]]:
    """
    Check whether any new edge originating from *rel_path* creates a cycle
    in the imports/calls subgraph.
    """
    # Build adjacency list from imports/calls edges
    adj: dict[str, set[str]] = {}
    for e in graph["edges"]:
        if e.get("type") in ("imports", "calls"):
            src = e.get("source", "")
            tgt = e.get("target", "")
            adj.setdefault(src, set()).add(tgt)

    # Only search starting from nodes in the changed file
    start_nodes = {
        n["id"] for n in graph["nodes"] if n.get("file") == rel_path
    }

    cycles: list[list[str]] = []
    for start in start_nodes:
        visited: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> None:
            if node in visited:
                if node in path:
                    idx = path.index(node)
                    cycles.append(path[idx:] + [node])
                return
            visited.add(node)
            path.append(node)
            for neighbour in adj.get(node, []):
                dfs(neighbour)
            path.pop()

        dfs(start)

    return cycles


# ===================================================================
# History / diff recording
# ===================================================================

def _save_diff(
    history_dir: Path,
    files_changed: list[str],
    nodes_added: list[NodeDict],
    nodes_removed: list[NodeDict],
    edges_added: list[EdgeDict],
    edges_removed: list[EdgeDict],
    drift_warnings: list[DriftWarning],
) -> Path:
    """Save a diff record to .okode/history/{timestamp}_diff.json."""
    history_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    diff_path = history_dir / f"{ts}_diff.json"
    diff = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "files_changed": files_changed,
        "nodes_added": nodes_added,
        "nodes_removed": nodes_removed,
        "edges_added": edges_added,
        "edges_removed": edges_removed,
        "drift_warnings": drift_warnings,
    }
    diff_path.write_text(
        json.dumps(diff, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return diff_path


# ===================================================================
# Graph index regeneration
# ===================================================================

def regenerate_graph_index(graph: GraphDict, index_path: Path) -> None:
    """
    Produce a condensed graph_index.md (target: under 200 lines).

    If okode_scan provides a generate_graph_index function, delegate to it.
    Otherwise produce a basic index inline.
    """
    if _SCAN_MODULE_AVAILABLE and hasattr(_scan_mod, "generate_graph_index"):
        _scan_mod.generate_graph_index(graph, index_path)
        return

    # ---- inline fallback implementation ----
    meta = graph.get("metadata", {})
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    lines: list[str] = []
    lines.append("# oKode Graph Index")
    lines.append("")
    lines.append(f"Project: {meta.get('project', 'unknown')}")
    lines.append(f"Generated: {meta.get('generated_at', 'unknown')}")
    lines.append(f"Total nodes: {len(nodes)}")
    lines.append(f"Total edges: {len(edges)}")
    lines.append("")

    # Count by type
    type_counts: dict[str, int] = {}
    for n in nodes:
        t = n.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    lines.append("## Node Summary")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {t}: {c}")
    lines.append("")

    # Endpoints
    endpoints = [n for n in nodes if n.get("type") == "endpoint"]
    if endpoints:
        lines.append("## Endpoints")
        for ep in sorted(endpoints, key=lambda n: n.get("label", "")):
            lines.append(f"  {ep.get('label', '?')}  ({ep.get('file', '?')}:{ep.get('line', '?')})")
        lines.append("")

    # Ring distribution
    ring_counts: dict[int, int] = {0: 0, 1: 0, 2: 0}
    for n in nodes:
        r = n.get("ring")
        if isinstance(r, int) and r in ring_counts:
            ring_counts[r] += 1
    ring_labels = {0: "Core", 1: "Adjacent", 2: "Infrastructure"}
    lines.append("## Ring Distribution")
    for r in (0, 1, 2):
        lines.append(f"  Ring {r} ({ring_labels[r]}): {ring_counts[r]}")
    lines.append("")

    # Hotspots (top 10 by edge count)
    edge_count: dict[str, int] = {}
    for e in edges:
        for key in ("source", "target"):
            nid = e.get(key, "")
            edge_count[nid] = edge_count.get(nid, 0) + 1
    top = sorted(edge_count.items(), key=lambda x: -x[1])[:10]
    if top:
        lines.append("## Hotspots (top 10 by connections)")
        for nid, cnt in top:
            lines.append(f"  {nid}: {cnt} edges")
        lines.append("")

    # External APIs
    ext = [n for n in nodes if n.get("type") == "external_api"]
    if ext:
        lines.append("## External API Dependencies")
        for n in ext:
            lines.append(f"  {n.get('label', '?')} ({n.get('file', '?')})")
        lines.append("")

    # Env vars
    envs = [n for n in nodes if n.get("type") == "env_var"]
    if envs:
        lines.append("## Environment Variables")
        seen: set[str] = set()
        for n in envs:
            label = n.get("label", "?")
            if label not in seen:
                seen.add(label)
                lines.append(f"  {label}")
        lines.append("")

    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ===================================================================
# Main sync workflow
# ===================================================================

def sync(
    graph_path: Path,
    project_dir: Path,
    files: list[Path],
) -> dict[str, Any]:
    """
    Run the incremental sync for the given *files*.

    Returns a summary dict with counts and drift warnings.
    """
    graph = load_graph(graph_path)
    analyzer = _get_analyzer(project_dir)
    classifier = _get_classifier(project_dir)

    all_nodes_added: list[NodeDict] = []
    all_nodes_removed: list[NodeDict] = []
    all_edges_added: list[EdgeDict] = []
    all_edges_removed: list[EdgeDict] = []
    all_drift: list[DriftWarning] = []
    rel_paths: list[str] = []

    for fpath in files:
        try:
            rel = fpath.relative_to(project_dir).as_posix()
        except ValueError:
            rel = fpath.as_posix()
        rel_paths.append(rel)

        # Step 3a: remove old data for this file
        old_nodes, old_edges = _remove_file_from_graph(graph, rel)

        # Step 3b: re-run static analysis
        if hasattr(analyzer, "analyze_file"):
            new_nodes, new_edges = analyzer.analyze_file(fpath)
        else:
            new_nodes, new_edges = [], []

        # Step 3c: LLM classification pass (if available)
        if hasattr(classifier, "classify"):
            new_nodes, new_edges = classifier.classify(fpath, new_nodes, new_edges)

        # Step 3d: merge into graph
        _merge_into_graph(graph, new_nodes, new_edges)

        # Step 4/5: detect drift
        drift = _detect_drift(graph, rel, old_nodes, old_edges, new_nodes, new_edges)
        all_drift.extend(drift)

        # Track diff
        old_ids = {n["id"] for n in old_nodes}
        new_ids = {n["id"] for n in new_nodes}
        all_nodes_added.extend([n for n in new_nodes if n["id"] not in old_ids])
        all_nodes_removed.extend([n for n in old_nodes if n["id"] not in new_ids])

        old_edge_keys = {
            (e.get("source"), e.get("target"), e.get("type"))
            for e in old_edges
        }
        new_edge_keys = {
            (e.get("source"), e.get("target"), e.get("type"))
            for e in new_edges
        }
        all_edges_added.extend(
            [e for e in new_edges
             if (e.get("source"), e.get("target"), e.get("type")) not in old_edge_keys]
        )
        all_edges_removed.extend(
            [e for e in old_edges
             if (e.get("source"), e.get("target"), e.get("type")) not in new_edge_keys]
        )

    # Step 6: save diff
    history_dir = graph_path.parent / "history"
    diff_path = _save_diff(
        history_dir,
        rel_paths,
        all_nodes_added,
        all_nodes_removed,
        all_edges_added,
        all_edges_removed,
        all_drift,
    )

    # Step 7: update metadata
    graph["metadata"]["generated_at"] = datetime.now(timezone.utc).isoformat()
    graph["metadata"]["total_files_analyzed"] = len(
        {n.get("file") for n in graph["nodes"] if n.get("file")}
    )

    # Step 8: save graph
    save_graph(graph, graph_path)

    # Step 9: regenerate index
    index_path = graph_path.parent / "graph_index.md"
    regenerate_graph_index(graph, index_path)

    summary = {
        "files_updated": len(files),
        "nodes_added": len(all_nodes_added),
        "nodes_removed": len(all_nodes_removed),
        "edges_added": len(all_edges_added),
        "edges_removed": len(all_edges_removed),
        "drift_warnings": all_drift,
        "diff_path": str(diff_path),
    }
    return summary


# ===================================================================
# CLI
# ===================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="oKode incremental graph sync",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        default=[],
        help="Specific files to re-scan",
    )
    parser.add_argument(
        "--since-last",
        action="store_true",
        help="Auto-detect files changed since last scan via git",
    )
    parser.add_argument(
        "--graph-path",
        type=str,
        default=".okode/graph.json",
        help="Path to graph.json (default: .okode/graph.json)",
    )
    parser.add_argument(
        "--project-dir",
        type=str,
        default=".",
        help="Project root directory (default: cwd)",
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    graph_path = Path(args.graph_path)
    if not graph_path.is_absolute():
        graph_path = project_dir / graph_path
    graph_path = graph_path.resolve()

    # Determine which files to sync
    if args.files:
        files = _files_from_args(args.files, project_dir)
    elif args.since_last:
        graph = load_graph(graph_path)
        files = _files_since_last(graph, project_dir)
    else:
        parser.error("Provide --files or --since-last")
        return  # unreachable but keeps type checkers happy

    if not files:
        print("[okode_sync] No changed files detected. Graph is up to date.")
        return

    print(f"[okode_sync] Syncing {len(files)} file(s)...")
    for f in files:
        print(f"  - {f.relative_to(project_dir) if f.is_relative_to(project_dir) else f}")

    summary = sync(graph_path, project_dir, files)

    # Step 10: print summary
    print()
    print("=" * 60)
    print("oKode Sync Summary")
    print("=" * 60)
    print(f"  Files updated:   {summary['files_updated']}")
    print(f"  Nodes added:     {summary['nodes_added']}")
    print(f"  Nodes removed:   {summary['nodes_removed']}")
    print(f"  Edges added:     {summary['edges_added']}")
    print(f"  Edges removed:   {summary['edges_removed']}")
    print(f"  Diff saved to:   {summary['diff_path']}")

    drift = summary["drift_warnings"]
    if drift:
        print()
        print(f"  Drift warnings:  {len(drift)}")
        for w in drift:
            severity = w.get("severity", "?")
            wtype = w.get("type", "?")
            detail = w.get("detail", "")
            marker = "!!!" if severity == "BLOCK" else " ! "
            print(f"  {marker} [{severity}] {wtype}: {detail}")

        blocks = [w for w in drift if w.get("severity") == "BLOCK"]
        if blocks:
            print()
            print("  *** BLOCKING issues detected. Review before proceeding. ***")
    else:
        print("  Drift warnings:  0 (clean)")

    print("=" * 60)


if __name__ == "__main__":
    main()
