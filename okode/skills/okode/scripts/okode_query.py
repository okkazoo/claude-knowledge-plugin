#!/usr/bin/env python3
"""
oKode Query Engine — CLI tool for querying the oKode code graph.

Answers architectural questions from the graph without reading source files.
Uses only Python stdlib (json, argparse, pathlib, collections, textwrap).

Usage:
  python okode_query.py --trace-endpoint "POST /api/workflows/analyze"
  python okode_query.py --what-does "services/workflow_analyzer.py"
  python okode_query.py --where-used "services/cache.py"
  python okode_query.py --db-contract "workflows"
  python okode_query.py --risk-map
  python okode_query.py --hotspots
  python okode_query.py --dead-code
  python okode_query.py --feature-summary "topic_atlas"
  python okode_query.py --reconcile "feature_name"
  python okode_query.py --graph-path ".okode/graph.json"
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Edge type groupings
# ---------------------------------------------------------------------------

DB_READ_TYPES = {"db_read"}
DB_WRITE_TYPES = {"db_write"}
DB_EDGE_TYPES = DB_READ_TYPES | DB_WRITE_TYPES

CALL_EDGE_TYPES = {"calls", "imports", "api_call"}
ENQUEUE_TYPES = {"enqueues"}
CACHE_TYPES = {"cache_read", "cache_write"}
EVENT_TYPES = {"event_publish", "event_subscribe"}
WEBHOOK_TYPES = {"webhook_send", "webhook_receive"}
RENDER_TYPES = {"renders", "fetches"}

RISK_EDGE_TYPES = {"api_call", "webhook_send", "webhook_receive"}
RISK_NODE_TYPES = {"external_api", "env_var"}

# Node types considered entrypoints (root nodes that are *meant* to have
# zero incoming edges).
ENTRYPOINT_NODE_TYPES = {"endpoint", "task", "script", "webhook", "page", "event"}

RING_LABELS = {0: "Core", 1: "Adjacent", 2: "Infrastructure"}


# ---------------------------------------------------------------------------
# GraphQuery — main query engine
# ---------------------------------------------------------------------------

class GraphQuery:
    """Loads an oKode graph and provides fast indexed queries."""

    def __init__(self, graph_path: Path) -> None:
        self.graph_path = graph_path
        self.metadata: dict[str, Any] = {}
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []
        self.outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.nodes_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.nodes_by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._load()

    # ------------------------------------------------------------------
    # Loading & indexing
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self.graph_path.exists():
            print(f"ERROR: Graph file not found: {self.graph_path}", file=sys.stderr)
            print("Run okode_scan.py first to generate the graph.", file=sys.stderr)
            sys.exit(1)

        with open(self.graph_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        self.metadata = data.get("metadata", {})

        for node in data.get("nodes", []):
            nid = node["id"]
            self.nodes[nid] = node
            self.nodes_by_type[node.get("type", "unknown")].append(node)
            if node.get("file"):
                self.nodes_by_file[self._normalise_path(node["file"])].append(node)

        for edge in data.get("edges", []):
            self.edges.append(edge)
            self.outgoing[edge["source"]].append(edge)
            self.incoming[edge["target"]].append(edge)

    @staticmethod
    def _normalise_path(p: str) -> str:
        """Normalise a path to forward-slash style for consistent lookups."""
        return p.replace("\\", "/")

    # ------------------------------------------------------------------
    # Node lookup helpers
    # ------------------------------------------------------------------

    def _find_node(self, query: str) -> dict[str, Any] | None:
        """Fuzzy-find a node by id, label, or file path fragment."""
        query_norm = self._normalise_path(query)

        # Exact id match
        if query_norm in self.nodes:
            return self.nodes[query_norm]

        # Label match (case-insensitive)
        ql = query.lower()
        for node in self.nodes.values():
            if node.get("label", "").lower() == ql:
                return node

        # Partial id / label match
        for node in self.nodes.values():
            nid_lower = node["id"].lower()
            label_lower = node.get("label", "").lower()
            if ql in nid_lower or ql in label_lower:
                return node

        # File path match
        for node in self.nodes.values():
            node_file = self._normalise_path(node.get("file", ""))
            if node_file and (query_norm in node_file or node_file.endswith(query_norm)):
                return node

        return None

    def _find_nodes_by_query(self, query: str) -> list[dict[str, Any]]:
        """Find ALL nodes matching a query (file path, type, or partial id)."""
        query_norm = self._normalise_path(query)
        ql = query.lower()
        results: list[dict[str, Any]] = []
        seen: set[str] = set()

        # Exact id
        if query_norm in self.nodes:
            results.append(self.nodes[query_norm])
            seen.add(query_norm)

        for node in self.nodes.values():
            if node["id"] in seen:
                continue
            nid_lower = node["id"].lower()
            label_lower = node.get("label", "").lower()
            node_file = self._normalise_path(node.get("file", ""))

            if (ql in nid_lower
                    or ql in label_lower
                    or (node_file and (query_norm in node_file
                                       or node_file.endswith(query_norm)))):
                results.append(node)
                seen.add(node["id"])

        return results

    def _find_endpoint_node(self, endpoint_query: str) -> dict[str, Any] | None:
        """Find an endpoint node by method + path (e.g. 'POST /api/workflows/analyze')."""
        ql = endpoint_query.strip().lower()

        # Try exact match on label first
        for node in self.nodes_by_type.get("endpoint", []):
            if node.get("label", "").lower() == ql:
                return node

        # Try partial match
        for node in self.nodes_by_type.get("endpoint", []):
            if ql in node.get("label", "").lower() or ql in node["id"].lower():
                return node

        # Fallback to generic find
        return self._find_node(endpoint_query)

    def _node_display(self, node: dict[str, Any]) -> str:
        """Short display string for a node."""
        label = node.get("label", node["id"])
        file = node.get("file", "")
        line = node.get("line")
        loc = ""
        if file:
            loc = f" ({file}"
            if line:
                loc += f":{line}"
            loc += ")"
        return f"{label}{loc}"

    def _node_ring_label(self, node: dict[str, Any]) -> str:
        ring = node.get("ring")
        if ring is not None:
            return f"Ring {ring} ({RING_LABELS.get(ring, 'Unknown')})"
        return "Ring unclassified"

    # ------------------------------------------------------------------
    # 1. --trace-endpoint
    # ------------------------------------------------------------------

    def trace_endpoint(self, endpoint_query: str) -> str:
        node = self._find_endpoint_node(endpoint_query)
        if not node:
            return f"No endpoint found matching: {endpoint_query}"

        lines: list[str] = []
        lines.append(node.get("label", node["id"]))
        visited: set[str] = set()
        self._trace_recursive(node["id"], lines, indent=1, visited=visited)
        return "\n".join(lines)

    def _trace_recursive(
        self,
        node_id: str,
        lines: list[str],
        indent: int,
        visited: set[str],
    ) -> None:
        if node_id in visited:
            return
        visited.add(node_id)

        prefix = "  " * indent + "-> "

        # Group outgoing edges by type for cleaner output
        edge_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in self.outgoing.get(node_id, []):
            edge_groups[edge["type"]].append(edge)

        for etype, edges in edge_groups.items():
            for edge in edges:
                target = self.nodes.get(edge["target"], {})
                target_label = target.get("label", edge["target"])
                target_type = target.get("type", "unknown")
                context = edge.get("context", "")
                file_ref = edge.get("file", "")
                line_ref = edge.get("line", "")

                if etype == "endpoint_handler":
                    loc = file_ref
                    if line_ref:
                        loc += f":{line_ref}"
                    lines.append(f"{prefix}handler: {loc}")
                    # Recurse into handler
                    self._trace_recursive(edge["target"], lines, indent + 1, visited)

                elif etype in DB_READ_TYPES:
                    lines.append(f"{prefix}reads: {target_label} (collection)")

                elif etype in DB_WRITE_TYPES:
                    lines.append(f"{prefix}writes: {target_label} (collection)")

                elif etype == "api_call":
                    lines.append(f"{prefix}calls: {target_label} (external)")

                elif etype in ENQUEUE_TYPES:
                    lines.append(f"{prefix}enqueues: {target_label} (task)")

                elif etype in CACHE_TYPES:
                    op = "cache_read" if etype == "cache_read" else "cache_write"
                    lines.append(f"{prefix}{op}: {target_label}")

                elif etype in EVENT_TYPES:
                    op = "publishes" if etype == "event_publish" else "subscribes"
                    lines.append(f"{prefix}{op}: {target_label} (event)")

                elif etype in WEBHOOK_TYPES:
                    op = "webhook_send" if etype == "webhook_send" else "webhook_receive"
                    lines.append(f"{prefix}{op}: {target_label}")

                elif etype == "calls":
                    lines.append(f"{prefix}calls: {target_label}")
                    self._trace_recursive(edge["target"], lines, indent + 1, visited)

                elif etype == "imports":
                    lines.append(f"{prefix}imports: {target_label}")
                    # Do not recurse deeply into imports to avoid noise

                elif etype == "renders":
                    lines.append(f"{prefix}renders: {target_label} (component)")
                    self._trace_recursive(edge["target"], lines, indent + 1, visited)

                elif etype == "fetches":
                    lines.append(f"{prefix}fetches: {target_label} (endpoint)")
                    self._trace_recursive(edge["target"], lines, indent + 1, visited)

                else:
                    detail = f" — {context}" if context else ""
                    lines.append(f"{prefix}{etype}: {target_label}{detail}")
                    # Generic recurse for unknown edge types with callable targets
                    if target_type in ("service", "file", "utility", "router"):
                        self._trace_recursive(edge["target"], lines, indent + 1, visited)

    # ------------------------------------------------------------------
    # 2. --what-does
    # ------------------------------------------------------------------

    def what_does(self, query: str) -> str:
        nodes = self._find_nodes_by_query(query)
        if not nodes:
            return f"No node found matching: {query}"

        lines: list[str] = []

        for node in nodes:
            lines.append(f"=== {self._node_display(node)} ===")
            lines.append(f"  Type: {node.get('type', 'unknown')}")
            lines.append(f"  {self._node_ring_label(node)}")
            lines.append("")

            out_edges = self.outgoing.get(node["id"], [])
            in_edges = self.incoming.get(node["id"], [])

            if out_edges:
                lines.append(f"  Outgoing ({len(out_edges)} edges):")
                for edge in out_edges:
                    target = self.nodes.get(edge["target"], {})
                    target_label = target.get("label", edge["target"])
                    ctx = f" — {edge['context']}" if edge.get("context") else ""
                    lines.append(f"    -> [{edge['type']}] {target_label}{ctx}")
            else:
                lines.append("  Outgoing: (none)")

            lines.append("")

            if in_edges:
                lines.append(f"  Incoming ({len(in_edges)} edges):")
                for edge in in_edges:
                    source = self.nodes.get(edge["source"], {})
                    source_label = source.get("label", edge["source"])
                    ctx = f" — {edge['context']}" if edge.get("context") else ""
                    lines.append(f"    <- [{edge['type']}] {source_label}{ctx}")
            else:
                lines.append("  Incoming: (none)")

            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 3. --where-used
    # ------------------------------------------------------------------

    def where_used(self, query: str) -> str:
        nodes = self._find_nodes_by_query(query)
        if not nodes:
            return f"No node found matching: {query}"

        lines: list[str] = []
        for node in nodes:
            in_edges = self.incoming.get(node["id"], [])
            lines.append(f"=== Where used: {self._node_display(node)} ===")
            lines.append(f"  Type: {node.get('type', 'unknown')}")
            lines.append(f"  Referenced by {len(in_edges)} edge(s):")
            lines.append("")

            if not in_edges:
                lines.append("  (no incoming edges — this node has no callers)")
            else:
                # Group by source
                by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for edge in in_edges:
                    by_source[edge["source"]].append(edge)

                for source_id, edges in by_source.items():
                    source_node = self.nodes.get(source_id, {})
                    source_display = self._node_display(source_node) if source_node else source_id
                    edge_types = ", ".join(sorted({e["type"] for e in edges}))
                    lines.append(f"  <- {source_display}")
                    lines.append(f"     via: {edge_types}")

            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 4. --db-contract
    # ------------------------------------------------------------------

    def db_contract(self, collection_name: str) -> str:
        # Find the collection node
        cl = collection_name.lower()
        collection_node: dict[str, Any] | None = None
        for node in self.nodes_by_type.get("collection", []):
            if node.get("label", "").lower() == cl or cl in node["id"].lower():
                collection_node = node
                break

        # Even if node not found, search edges that reference the collection
        writers: list[tuple[dict[str, Any], dict[str, Any]]] = []
        readers: list[tuple[dict[str, Any], dict[str, Any]]] = []

        target_ids: set[str] = set()
        if collection_node:
            target_ids.add(collection_node["id"])
        # Also match by name fragment in edge targets
        for edge in self.edges:
            if cl in edge["target"].lower():
                target_ids.add(edge["target"])

        for tid in target_ids:
            for edge in self.incoming.get(tid, []):
                source_node = self.nodes.get(edge["source"], {})
                if edge["type"] in DB_WRITE_TYPES:
                    writers.append((source_node, edge))
                elif edge["type"] in DB_READ_TYPES:
                    readers.append((source_node, edge))

        lines: list[str] = []
        display_name = collection_node.get("label", collection_name) if collection_node else collection_name
        lines.append(f"Collection: {display_name}")
        lines.append(f"  Writers: {len(writers)} component(s)")
        for src, edge in writers:
            label = src.get("label", edge["source"]) if src else edge["source"]
            file = src.get("file", edge.get("file", "")) if src else edge.get("file", "")
            lines.append(f"    W: {label} ({file})")

        lines.append(f"  Readers: {len(readers)} component(s)")
        for src, edge in readers:
            label = src.get("label", edge["source"]) if src else edge["source"]
            file = src.get("file", edge.get("file", "")) if src else edge.get("file", "")
            lines.append(f"    R: {label} ({file})")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 5. --risk-map
    # ------------------------------------------------------------------

    def risk_map(self) -> str:
        lines: list[str] = []

        # External APIs
        ext_apis = self.nodes_by_type.get("external_api", [])
        lines.append(f"External API Dependencies ({len(ext_apis)}):")
        if ext_apis:
            for node in ext_apis:
                callers = self.incoming.get(node["id"], [])
                caller_labels = [
                    self.nodes.get(e["source"], {}).get("label", e["source"])
                    for e in callers
                ]
                lines.append(f"  {node.get('label', node['id'])}")
                if caller_labels:
                    lines.append(f"    Used by: {', '.join(caller_labels)}")
        else:
            lines.append("  (none)")
        lines.append("")

        # API call edges (even without explicit external_api nodes)
        api_call_edges = [e for e in self.edges if e["type"] == "api_call"]
        if api_call_edges:
            lines.append(f"API Call Edges ({len(api_call_edges)}):")
            for edge in api_call_edges:
                src = self.nodes.get(edge["source"], {})
                tgt = self.nodes.get(edge["target"], {})
                lines.append(
                    f"  {src.get('label', edge['source'])} -> "
                    f"{tgt.get('label', edge['target'])}"
                )
                if edge.get("context"):
                    lines.append(f"    Context: {edge['context']}")
            lines.append("")

        # Environment variables
        env_vars = self.nodes_by_type.get("env_var", [])
        lines.append(f"Environment Variable Dependencies ({len(env_vars)}):")
        if env_vars:
            for node in env_vars:
                users = self.incoming.get(node["id"], [])
                user_labels = [
                    self.nodes.get(e["source"], {}).get("label", e["source"])
                    for e in users
                ]
                label = node.get("label", node["id"])
                lines.append(f"  {label}")
                if user_labels:
                    lines.append(f"    Used by: {', '.join(user_labels)}")
        else:
            lines.append("  (none)")
        lines.append("")

        # Webhook edges
        webhook_edges = [e for e in self.edges if e["type"] in WEBHOOK_TYPES]
        lines.append(f"Webhook Dependencies ({len(webhook_edges)}):")
        if webhook_edges:
            for edge in webhook_edges:
                src = self.nodes.get(edge["source"], {})
                tgt = self.nodes.get(edge["target"], {})
                direction = "SEND" if edge["type"] == "webhook_send" else "RECEIVE"
                lines.append(
                    f"  [{direction}] {src.get('label', edge['source'])} -> "
                    f"{tgt.get('label', edge['target'])}"
                )
        else:
            lines.append("  (none)")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 6. --hotspots
    # ------------------------------------------------------------------

    def hotspots(self, limit: int = 20) -> str:
        counts: list[tuple[str, int, int, int]] = []
        for nid, node in self.nodes.items():
            out_count = len(self.outgoing.get(nid, []))
            in_count = len(self.incoming.get(nid, []))
            total = out_count + in_count
            counts.append((nid, total, out_count, in_count))

        counts.sort(key=lambda x: x[1], reverse=True)

        lines: list[str] = [f"Top {limit} Hotspots (most connected nodes):"]
        lines.append(f"{'Rank':<6} {'Total':<7} {'Out':<5} {'In':<5} {'Node'}")
        lines.append("-" * 80)

        for i, (nid, total, out_c, in_c) in enumerate(counts[:limit], 1):
            node = self.nodes.get(nid, {})
            label = node.get("label", nid)
            ntype = node.get("type", "?")
            file = node.get("file", "")
            loc = f" ({file})" if file else ""
            lines.append(f"{i:<6} {total:<7} {out_c:<5} {in_c:<5} [{ntype}] {label}{loc}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 7. --dead-code
    # ------------------------------------------------------------------

    def dead_code(self) -> str:
        dead: list[dict[str, Any]] = []
        for nid, node in self.nodes.items():
            ntype = node.get("type", "unknown")
            # Skip entrypoint types — they are meant to be root nodes
            if ntype in ENTRYPOINT_NODE_TYPES:
                continue
            # Skip collection/external_api/env_var — they are targets, not callers
            if ntype in ("collection", "external_api", "env_var", "cache_key"):
                continue

            in_edges = self.incoming.get(nid, [])
            if len(in_edges) == 0:
                dead.append(node)

        lines: list[str] = [f"Potential Dead Code ({len(dead)} nodes with 0 incoming edges):"]
        lines.append("(Excludes entrypoints: endpoints, tasks, scripts, webhooks, pages, events)")
        lines.append("")

        if not dead:
            lines.append("  No dead code detected.")
        else:
            # Sort by type then label
            dead.sort(key=lambda n: (n.get("type", ""), n.get("label", n["id"])))
            for node in dead:
                label = node.get("label", node["id"])
                ntype = node.get("type", "?")
                file = node.get("file", "")
                ring = node.get("ring")
                ring_str = f" [Ring {ring}]" if ring is not None else ""
                loc = f" ({file})" if file else ""
                out_count = len(self.outgoing.get(node["id"], []))
                lines.append(f"  [{ntype}]{ring_str} {label}{loc}  (outgoing: {out_count})")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 8. --feature-summary
    # ------------------------------------------------------------------

    def feature_summary(self, feature: str) -> str:
        """Ring-classified summary for a feature directory."""
        feature_norm = self._normalise_path(feature).lower()

        # Collect nodes belonging to this feature (by file path)
        feature_nodes: list[dict[str, Any]] = []
        for node in self.nodes.values():
            node_file = self._normalise_path(node.get("file", "")).lower()
            if feature_norm in node_file:
                feature_nodes.append(node)

        if not feature_nodes:
            return f"No nodes found for feature: {feature}"

        # Classify by ring
        by_ring: dict[int, list[dict[str, Any]]] = defaultdict(list)
        by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in feature_nodes:
            ring = node.get("ring", -1)
            by_ring[ring].append(node)
            by_type[node.get("type", "unknown")].append(node)

        lines: list[str] = []
        lines.append(f"Feature Summary: {feature}")
        lines.append(f"  Total nodes: {len(feature_nodes)}")
        lines.append("")

        # Ring distribution
        lines.append("Ring Distribution:")
        for ring in sorted(by_ring.keys()):
            label = RING_LABELS.get(ring, "Unclassified")
            lines.append(f"  Ring {ring} ({label}): {len(by_ring[ring])} node(s)")
        lines.append("")

        # By type
        lines.append("Component Types:")
        for ntype in sorted(by_type.keys()):
            lines.append(f"  {ntype}: {len(by_type[ntype])}")
        lines.append("")

        # Service tiers
        services = [n for n in feature_nodes if n.get("type") in ("service", "utility")]
        if services:
            lines.append("Service Tiers (by caller count):")
            svc_callers = []
            for svc in services:
                in_count = len(self.incoming.get(svc["id"], []))
                svc_callers.append((svc, in_count))
            svc_callers.sort(key=lambda x: x[1], reverse=True)
            for svc, count in svc_callers:
                ring_str = f"[Ring {svc.get('ring', '?')}]" if svc.get("ring") is not None else ""
                lines.append(f"  {svc.get('label', svc['id'])} {ring_str} ({count} callers)")
            lines.append("")

        # Data flows (collections touched by feature nodes)
        collections_read: set[str] = set()
        collections_written: set[str] = set()
        for node in feature_nodes:
            for edge in self.outgoing.get(node["id"], []):
                if edge["type"] in DB_READ_TYPES:
                    tgt = self.nodes.get(edge["target"], {})
                    collections_read.add(tgt.get("label", edge["target"]))
                elif edge["type"] in DB_WRITE_TYPES:
                    tgt = self.nodes.get(edge["target"], {})
                    collections_written.add(tgt.get("label", edge["target"]))

        if collections_read or collections_written:
            lines.append("Data Flows:")
            if collections_read:
                lines.append(f"  Reads from: {', '.join(sorted(collections_read))}")
            if collections_written:
                lines.append(f"  Writes to:  {', '.join(sorted(collections_written))}")
            lines.append("")

        # Endpoints in this feature
        endpoints = [n for n in feature_nodes if n.get("type") == "endpoint"]
        if endpoints:
            lines.append(f"Endpoints ({len(endpoints)}):")
            for ep in endpoints:
                lines.append(f"  {ep.get('label', ep['id'])}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 9. --reconcile (full deep analysis)
    # ------------------------------------------------------------------

    def reconcile(self, feature: str, output_dir: Path | None = None) -> str:
        """Full deep analysis combining all queries for a feature."""
        feature_norm = self._normalise_path(feature).lower()

        # Collect ALL nodes belonging to this feature
        feature_nodes: list[dict[str, Any]] = []
        feature_node_ids: set[str] = set()
        for node in self.nodes.values():
            node_file = self._normalise_path(node.get("file", "")).lower()
            if feature_norm in node_file:
                feature_nodes.append(node)
                feature_node_ids.add(node["id"])

        if not feature_nodes:
            return f"No nodes found for feature: {feature}"

        # ---- Classify nodes ----
        by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_ring: dict[int, list[dict[str, Any]]] = defaultdict(list)
        by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for node in feature_nodes:
            by_type[node.get("type", "unknown")].append(node)
            ring = node.get("ring", -1)
            by_ring[ring].append(node)
            if node.get("file"):
                by_file[self._normalise_path(node["file"])].append(node)

        routers = by_type.get("router", [])
        services = by_type.get("service", []) + by_type.get("utility", [])
        tasks = by_type.get("task", [])
        scripts = by_type.get("script", [])
        endpoints = by_type.get("endpoint", [])
        files = by_type.get("file", [])

        # Collect collections and external APIs referenced by feature nodes
        collections_touched: dict[str, dict[str, list[str]]] = defaultdict(
            lambda: {"readers": [], "writers": []}
        )
        external_apis: dict[str, list[str]] = defaultdict(list)

        for node in feature_nodes:
            for edge in self.outgoing.get(node["id"], []):
                tgt = self.nodes.get(edge["target"], {})
                tgt_label = tgt.get("label", edge["target"])
                node_label = node.get("label", node["id"])
                if edge["type"] in DB_READ_TYPES:
                    collections_touched[tgt_label]["readers"].append(node_label)
                elif edge["type"] in DB_WRITE_TYPES:
                    collections_touched[tgt_label]["writers"].append(node_label)
                elif edge["type"] == "api_call":
                    external_apis[tgt_label].append(node_label)

        unique_collections = list(collections_touched.keys())
        unique_ext_apis = list(external_apis.keys())

        # ---- Count metrics ----
        total_files = len(by_file)
        queries_executed = 0
        trace_paths = 0
        entity_cards = len(by_file)
        collection_contracts = len(unique_collections)

        # ---- Build the report ----
        out: list[str] = []

        def section(title: str) -> None:
            out.append("")
            out.append("=" * 60)
            out.append(title)
            out.append("=" * 60)
            out.append("")

        # Header
        out.append(f"# {feature.upper()} -- COMPLETE CODE SYNTHESIS")
        out.append("=" * 60)
        out.append("")
        out.append(f"Feature: {feature}")
        out.append(f"Total Files: {total_files}")
        out.append(f"Routers: {len(routers)}")
        out.append(f"Services: {len(services)}")
        out.append(f"Tasks: {len(tasks)}")
        out.append(f"Scripts: {len(scripts)}")
        out.append(f"Endpoints: {len(endpoints)}")
        out.append(f"Collections: {len(unique_collections)}")
        out.append(f"External APIs: {len(unique_ext_apis)}")
        out.append("")
        out.append("Ring Distribution:")
        for ring in sorted(by_ring.keys()):
            label = RING_LABELS.get(ring, "Unclassified")
            out.append(f"  Ring {ring} ({label}): {len(by_ring[ring])} files")
        out.append("")

        # Table of Contents
        out.append("=" * 60)
        out.append("TABLE OF CONTENTS")
        out.append("=" * 60)
        out.append("1. Architecture Overview")
        out.append("2. Complete Component Registry")
        out.append("3. Complete Data Flows")
        out.append("4. Dependency Map")
        out.append("5. Complete Quick Reference")
        out.append("")

        # ----------------------------------------------------------
        # SECTION 1: Architecture Overview
        # ----------------------------------------------------------
        section("SECTION 1: ARCHITECTURE OVERVIEW")

        # Service Layer
        out.append(f"Service Layer ({len(services)} Services):")
        for svc in sorted(services, key=lambda n: n.get("label", n["id"])):
            ring_str = f"[Ring {svc.get('ring', '?')}: {RING_LABELS.get(svc.get('ring'), 'Unknown')}]"
            reads = sum(1 for e in self.outgoing.get(svc["id"], []) if e["type"] in DB_READ_TYPES)
            writes = sum(1 for e in self.outgoing.get(svc["id"], []) if e["type"] in DB_WRITE_TYPES)
            out.append(f"  |-- {svc.get('label', svc['id'])} {ring_str}")
            out.append(f"  |     {reads}R/{writes}W")
        out.append("")

        # Task Layer
        out.append(f"Task Layer ({len(tasks)} Background Jobs):")
        for task in sorted(tasks, key=lambda n: n.get("label", n["id"])):
            ring_str = f"[Ring {task.get('ring', '?')}: {RING_LABELS.get(task.get('ring'), 'Unknown')}]"
            reads = sum(1 for e in self.outgoing.get(task["id"], []) if e["type"] in DB_READ_TYPES)
            writes = sum(1 for e in self.outgoing.get(task["id"], []) if e["type"] in DB_WRITE_TYPES)
            out.append(f"  |-- {task.get('label', task['id'])} {ring_str}")
            out.append(f"  |     {reads}R/{writes}W")
        out.append("")

        # Script Layer
        out.append(f"Script Layer ({len(scripts)} Scripts):")
        for script in sorted(scripts, key=lambda n: n.get("label", n["id"])):
            reads = sum(1 for e in self.outgoing.get(script["id"], []) if e["type"] in DB_READ_TYPES)
            writes = sum(1 for e in self.outgoing.get(script["id"], []) if e["type"] in DB_WRITE_TYPES)
            out.append(f"  |-- {script.get('label', script['id'])}")
            out.append(f"  |     {reads}R/{writes}W")
        out.append("")

        # Data Layer
        out.append(f"Data Layer ({len(unique_collections)} Collections):")
        for coll_name in sorted(unique_collections):
            data = collections_touched[coll_name]
            w = len(data["writers"])
            r = len(data["readers"])
            out.append(f"  |-- {coll_name} ({w}W/{r}R)")
        out.append("")

        # ----------------------------------------------------------
        # SECTION 2: Complete Component Registry
        # ----------------------------------------------------------
        section("SECTION 2: COMPLETE COMPONENT REGISTRY")

        queries_executed += 1

        for filepath in sorted(by_file.keys()):
            file_nodes = by_file[filepath]
            for node in file_nodes:
                nid = node["id"]
                ntype = node.get("type", "unknown")
                ring = node.get("ring")
                ring_label = self._node_ring_label(node)

                # IO profile
                db_reads: list[str] = []
                db_writes: list[str] = []
                for edge in self.outgoing.get(nid, []):
                    tgt = self.nodes.get(edge["target"], {})
                    tgt_label = tgt.get("label", edge["target"])
                    if edge["type"] in DB_READ_TYPES:
                        db_reads.append(tgt_label)
                    elif edge["type"] in DB_WRITE_TYPES:
                        db_writes.append(tgt_label)

                # Callers
                callers = self.incoming.get(nid, [])
                caller_labels = []
                for e in callers:
                    src = self.nodes.get(e["source"], {})
                    caller_labels.append(src.get("label", e["source"]))

                is_pure = len(db_reads) == 0 and len(db_writes) == 0

                label = node.get("label", nid)
                out.append(f"[{ntype}] {label}")
                out.append(f"  Path: {filepath}")
                out.append(f"  Type: {ntype}")
                out.append(f"  {ring_label}")
                out.append(f"  IO Profile:")
                out.append(f"    DB Reads:  {', '.join(db_reads) if db_reads else '(none)'}")
                out.append(f"    DB Writes: {', '.join(db_writes) if db_writes else '(none)'}")
                out.append(f"  Pure Function: {'yes' if is_pure else 'no'}")
                out.append(f"  Callers: {len(callers)} ({', '.join(caller_labels) if caller_labels else 'none'})")
                out.append("")

        # ----------------------------------------------------------
        # SECTION 3: Complete Data Flows
        # ----------------------------------------------------------
        section("SECTION 3: COMPLETE DATA FLOWS")

        # Endpoint traces
        out.append(f"ALL ENDPOINT TRACES ({len(endpoints)} total)")
        out.append("")

        for i, ep in enumerate(sorted(endpoints, key=lambda n: n.get("label", n["id"])), 1):
            queries_executed += 1
            trace_paths += 1

            trace_text = self.trace_endpoint(ep.get("label", ep["id"]))
            out.append(f"{i}. {trace_text}")
            out.append("")

        # Collection contracts
        out.append("-" * 60)
        out.append(f"COMPLETE COLLECTION CONTRACTS ({len(unique_collections)} total)")
        out.append("")

        for coll_name in sorted(unique_collections):
            queries_executed += 1
            contract_text = self.db_contract(coll_name)
            out.append(contract_text)
            out.append("")

        # ----------------------------------------------------------
        # SECTION 4: Dependency Map
        # ----------------------------------------------------------
        section("SECTION 4: DEPENDENCY MAP")

        queries_executed += 1

        # Service tiers
        out.append("SERVICE TIERS (by usage)")
        out.append("")

        svc_usage: list[tuple[dict[str, Any], int]] = []
        for svc in services:
            in_count = len(self.incoming.get(svc["id"], []))
            svc_usage.append((svc, in_count))
        svc_usage.sort(key=lambda x: x[1], reverse=True)

        tier1 = [(s, c) for s, c in svc_usage if c >= 5]
        tier2 = [(s, c) for s, c in svc_usage if 2 <= c < 5]
        tier3 = [(s, c) for s, c in svc_usage if c < 2]

        out.append(f"Tier 1 (High Usage, 5+ callers): {len(tier1)} services")
        for svc, count in tier1:
            ring_str = f"[Ring {svc.get('ring', '?')}]"
            out.append(f"  |-- {svc.get('label', svc['id'])} {ring_str} ({count} callers)")
        out.append("")

        out.append(f"Tier 2 (Medium Usage, 2-4 callers): {len(tier2)} services")
        for svc, count in tier2:
            ring_str = f"[Ring {svc.get('ring', '?')}]"
            out.append(f"  |-- {svc.get('label', svc['id'])} {ring_str} ({count} callers)")
        out.append("")

        out.append(f"Tier 3 (Low Usage, 0-1 callers): {len(tier3)} services")
        for svc, count in tier3:
            ring_str = f"[Ring {svc.get('ring', '?')}]"
            flag = "  <-- potential dead code" if count == 0 else ""
            out.append(f"  |-- {svc.get('label', svc['id'])} {ring_str} ({count} callers){flag}")
        out.append("")

        # External API dependencies
        out.append(f"EXTERNAL API DEPENDENCIES ({len(unique_ext_apis)} total)")
        if unique_ext_apis:
            for api_name in sorted(unique_ext_apis):
                users = external_apis[api_name]
                out.append(f"  {api_name}: used by {', '.join(sorted(set(users)))}")
        else:
            out.append("  (none)")
        out.append("")

        # ----------------------------------------------------------
        # SECTION 5: Quick Reference
        # ----------------------------------------------------------
        section("SECTION 5: COMPLETE QUICK REFERENCE")

        out.append("All Endpoints:")
        for ep in sorted(endpoints, key=lambda n: n.get("label", n["id"])):
            out.append(f"  {ep.get('label', ep['id'])}  ({ep.get('file', '')})")
        out.append("")

        out.append("All Services:")
        for svc in sorted(services, key=lambda n: n.get("label", n["id"])):
            callers = len(self.incoming.get(svc["id"], []))
            out.append(f"  {svc.get('label', svc['id'])}  ({svc.get('file', '')})  [{callers} callers]")
        out.append("")

        out.append("All Collections:")
        for coll_name in sorted(unique_collections):
            data = collections_touched[coll_name]
            out.append(f"  {coll_name}  ({len(data['writers'])}W/{len(data['readers'])}R)")
        out.append("")

        out.append("All Tasks:")
        for task in sorted(tasks, key=lambda n: n.get("label", n["id"])):
            out.append(f"  {task.get('label', task['id'])}  ({task.get('file', '')})")
        out.append("")

        out.append("All External APIs:")
        for api_name in sorted(unique_ext_apis):
            out.append(f"  {api_name}")
        out.append("")

        # ----------------------------------------------------------
        # Footer
        # ----------------------------------------------------------
        out.append("=" * 60)
        out.append("END OF COMPLETE SYNTHESIS")
        out.append("=" * 60)
        out.append("")
        out.append(f"Feature: {feature}")
        out.append(f"Total Queries: {queries_executed}")
        out.append(f"Components Analyzed: {entity_cards}")
        for ring in sorted(by_ring.keys()):
            label = RING_LABELS.get(ring, "Unclassified")
            out.append(f"Ring {ring} ({label}): {len(by_ring[ring])}")
        out.append("")
        out.append("ALL data preserved -- no removals, no summarization")
        out.append("Note: Some graph relationships (call chains) may be incomplete")
        out.append("due to dynamic nature of the language and current static analysis limitations.")

        report = "\n".join(out)

        # Save to .okode/synthesis/
        if output_dir is None:
            output_dir = self.graph_path.parent / "synthesis"
        output_dir.mkdir(parents=True, exist_ok=True)

        safe_name = feature.replace("/", "_").replace("\\", "_").replace(" ", "_")
        output_file = output_dir / f"{safe_name}_synthesis.md"
        output_file.write_text(report, encoding="utf-8")
        print(f"Synthesis report saved to: {output_file}", file=sys.stderr)

        return report


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _resolve_graph_path(args_path: str | None) -> Path:
    """Resolve the graph file path, searching upward from cwd if needed."""
    if args_path:
        return Path(args_path).resolve()

    # Search upward from cwd for .okode/graph.json
    current = Path.cwd()
    while True:
        candidate = current / ".okode" / "graph.json"
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent

    # Fallback to cwd
    return Path.cwd() / ".okode" / "graph.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="oKode Query Engine — query the code graph for architectural insights",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python okode_query.py --trace-endpoint "POST /api/workflows/analyze"
              python okode_query.py --what-does "services/workflow_analyzer.py"
              python okode_query.py --where-used "services/cache.py"
              python okode_query.py --db-contract "workflows"
              python okode_query.py --risk-map
              python okode_query.py --hotspots
              python okode_query.py --dead-code
              python okode_query.py --feature-summary "topic_atlas"
              python okode_query.py --reconcile "feature_name"
        """),
    )

    parser.add_argument(
        "--graph-path",
        type=str,
        default=None,
        help="Path to graph.json (default: .okode/graph.json, searching upward)",
    )

    # Query modes (mutually exclusive)
    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        "--trace-endpoint",
        type=str,
        metavar="ENDPOINT",
        help='Trace full execution chain from an endpoint (e.g. "POST /api/workflows/analyze")',
    )
    group.add_argument(
        "--what-does",
        type=str,
        metavar="NODE",
        help="Show all edges in/out of a node",
    )
    group.add_argument(
        "--where-used",
        type=str,
        metavar="NODE",
        help="Find all nodes that reference the target (reverse edge traversal)",
    )
    group.add_argument(
        "--db-contract",
        type=str,
        metavar="COLLECTION",
        help="Show all components that read/write a collection",
    )
    group.add_argument(
        "--risk-map",
        action="store_true",
        help="Show all external API calls, env vars, and webhook dependencies",
    )
    group.add_argument(
        "--hotspots",
        action="store_true",
        help="Show top 20 most-connected nodes",
    )
    group.add_argument(
        "--dead-code",
        action="store_true",
        help="Show nodes with 0 incoming edges (potential orphaned code)",
    )
    group.add_argument(
        "--feature-summary",
        type=str,
        metavar="FEATURE",
        help="Ring-classified summary for a feature directory",
    )
    group.add_argument(
        "--reconcile",
        type=str,
        metavar="FEATURE",
        help="Full deep analysis for a feature — combines all query types into a synthesis report",
    )

    args = parser.parse_args()

    graph_path = _resolve_graph_path(args.graph_path)
    gq = GraphQuery(graph_path)

    if args.trace_endpoint:
        print(gq.trace_endpoint(args.trace_endpoint))
    elif args.what_does:
        print(gq.what_does(args.what_does))
    elif args.where_used:
        print(gq.where_used(args.where_used))
    elif args.db_contract:
        print(gq.db_contract(args.db_contract))
    elif args.risk_map:
        print(gq.risk_map())
    elif args.hotspots:
        print(gq.hotspots())
    elif args.dead_code:
        print(gq.dead_code())
    elif args.feature_summary:
        print(gq.feature_summary(args.feature_summary))
    elif args.reconcile:
        print(gq.reconcile(args.reconcile))


if __name__ == "__main__":
    main()
