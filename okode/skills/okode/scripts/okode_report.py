#!/usr/bin/env python3
"""
okode_report.py -- Synthesis report generator for the oKode code graph system.

Produces a full reconcile / synthesis report from the graph for a given
feature, writing it to .okode/synthesis/{feature}_synthesis.md.

Usage:
    python okode_report.py --feature topic_atlas
    python okode_report.py --feature billing --graph-path .okode/graph.json
    python okode_report.py --feature auth --output reports/auth_report.md
"""

from __future__ import annotations

import argparse
import json
import textwrap
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
GraphDict = dict[str, Any]
NodeDict = dict[str, Any]
EdgeDict = dict[str, Any]


# ===================================================================
# Graph loading
# ===================================================================

def load_graph(graph_path: Path) -> GraphDict:
    """Load the graph JSON from disk."""
    if not graph_path.exists():
        raise FileNotFoundError(f"Graph not found at {graph_path}")
    return json.loads(graph_path.read_text(encoding="utf-8"))


# ===================================================================
# Feature filtering
# ===================================================================

def _match_feature(rel_path: str, feature: str) -> bool:
    """
    Return True if *rel_path* belongs to the given *feature*.

    Matching rules (in priority order):
    1. The path contains a directory segment equal to the feature name.
    2. The path starts with the feature name (treated as a prefix).
    3. The feature name appears anywhere in the path (fuzzy fallback).
    """
    parts = rel_path.replace("\\", "/").split("/")
    # Exact directory segment
    if feature in parts:
        return True
    # Prefix match
    if rel_path.replace("\\", "/").startswith(feature + "/") or rel_path.replace("\\", "/").startswith(feature + "\\"):
        return True
    # Fuzzy
    if feature.lower() in rel_path.lower():
        return True
    return False


def filter_graph(graph: GraphDict, feature: str) -> tuple[list[NodeDict], list[EdgeDict]]:
    """
    Return (nodes, edges) that belong to *feature*.

    A node belongs if its ``file`` field matches the feature.
    An edge belongs if its ``file`` matches, or if its source or target
    node belongs.
    """
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    feature_files: set[str] = set()
    feature_node_ids: set[str] = set()
    filtered_nodes: list[NodeDict] = []

    for n in nodes:
        f = n.get("file", "")
        if _match_feature(f, feature):
            feature_files.add(f)
            feature_node_ids.add(n["id"])
            filtered_nodes.append(n)

    # Also pull in nodes referenced by edges of matched files
    # (e.g. a collection node might not have a file match but is a target)
    referenced_ids: set[str] = set()
    for e in edges:
        if e.get("file", "") in feature_files or e.get("source") in feature_node_ids:
            referenced_ids.add(e.get("target", ""))
        if e.get("target") in feature_node_ids:
            referenced_ids.add(e.get("source", ""))

    extra_ids = referenced_ids - feature_node_ids
    for n in nodes:
        if n["id"] in extra_ids:
            filtered_nodes.append(n)
            feature_node_ids.add(n["id"])

    # Filter edges: keep if source or target is in feature_node_ids
    filtered_edges: list[EdgeDict] = []
    for e in edges:
        if e.get("source") in feature_node_ids or e.get("target") in feature_node_ids:
            filtered_edges.append(e)

    return filtered_nodes, filtered_edges


# ===================================================================
# Counting / analysis helpers
# ===================================================================

RING_LABELS = {0: "Core", 1: "Adjacent", 2: "Infrastructure"}


def _count_by_type(nodes: list[NodeDict]) -> Counter:
    return Counter(n.get("type", "unknown") for n in nodes)


def _count_by_ring(nodes: list[NodeDict]) -> dict[int, int]:
    counts: dict[int, int] = {0: 0, 1: 0, 2: 0}
    for n in nodes:
        r = n.get("ring")
        if isinstance(r, int) and r in counts:
            counts[r] += 1
    return counts


def _unique_files(nodes: list[NodeDict]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for n in nodes:
        f = n.get("file", "")
        if f and f not in seen:
            seen.add(f)
            result.append(f)
    return sorted(result)


def _callers_for_node(nid: str, edges: list[EdgeDict]) -> list[str]:
    """Return list of source node ids that have an edge targeting *nid*."""
    return [e["source"] for e in edges if e.get("target") == nid]


def _io_profile(
    nid: str, file_path: str, edges: list[EdgeDict]
) -> tuple[list[str], list[str]]:
    """Return (read_collections, write_collections) for a node or file."""
    reads: list[str] = []
    writes: list[str] = []
    for e in edges:
        src = e.get("source", "")
        if src != nid and e.get("file") != file_path:
            continue
        if e.get("type") == "db_read":
            target = e.get("target", "")
            col = target.replace("collection:", "") if target.startswith("collection:") else target
            if col not in reads:
                reads.append(col)
        elif e.get("type") == "db_write":
            target = e.get("target", "")
            col = target.replace("collection:", "") if target.startswith("collection:") else target
            if col not in writes:
                writes.append(col)
    return reads, writes


# ===================================================================
# Report sections
# ===================================================================

class SynthesisReport:
    """Builds the full synthesis markdown report for a feature."""

    def __init__(self, feature: str, nodes: list[NodeDict], edges: list[EdgeDict]):
        self.feature = feature
        self.nodes = nodes
        self.edges = edges
        self.node_map: dict[str, NodeDict] = {n["id"]: n for n in nodes}
        self.type_counts = _count_by_type(nodes)
        self.ring_counts = _count_by_ring(nodes)
        self.files = _unique_files(nodes)

    # ------------------------------------------------------------------
    def build(self) -> str:
        sections = [
            self._header(),
            self._toc(),
            self._section1_architecture(),
            self._section2_registry(),
            self._section3_data_flows(),
            self._section4_dependency_map(),
            self._footer(),
        ]
        return "\n".join(sections)

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    def _header(self) -> str:
        tc = self.type_counts
        rc = self.ring_counts
        endpoints = [n for n in self.nodes if n.get("type") == "endpoint"]
        collections = [n for n in self.nodes if n.get("type") == "collection"]
        ext_apis = [n for n in self.nodes if n.get("type") == "external_api"]
        # Count trace paths (endpoint -> handler chains)
        trace_count = len(endpoints)
        entity_card_count = len(self.files)
        collection_contracts = len(collections)

        lines = [
            f"# {self.feature.upper()} -- COMPLETE CODE SYNTHESIS",
            "=" * 60,
            "",
            f"Feature: {self.feature}",
            f"Total Files: {len(self.files)}",
            f"Routers: {tc.get('router', 0)}",
            f"Services: {tc.get('service', 0)}",
            f"Tasks: {tc.get('task', 0)}",
            f"Scripts: {tc.get('script', 0)}",
            f"Endpoints: {len(endpoints)}",
            f"Collections: {len(collections)}",
            f"External APIs: {len(ext_apis)}",
            "",
            f"Queries Executed: {trace_count + entity_card_count + collection_contracts}",
            f"Trace Paths: {trace_count}",
            f"Entity Cards: {entity_card_count}",
            f"Collection Contracts: {collection_contracts}",
            "",
            "Ring Distribution:",
            f"  Ring 0 (Core): {rc.get(0, 0)} files",
            f"  Ring 1 (Adjacent): {rc.get(1, 0)} files",
            f"  Ring 2 (Infrastructure): {rc.get(2, 0)} files",
            "",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Table of Contents
    # ------------------------------------------------------------------
    def _toc(self) -> str:
        return "\n".join([
            "=" * 60,
            "TABLE OF CONTENTS",
            "=" * 60,
            "1. Architecture Overview -- Layer structure, ring membership, data flow",
            "2. Complete Component Registry -- EVERY file detailed",
            "3. Complete Data Flows -- ALL endpoints, collections, API usage",
            "4. Dependency Map -- Service relationships, cross-feature usage",
            "5. Complete Quick Reference -- ALL endpoints, services, collections",
            "",
        ])

    # ------------------------------------------------------------------
    # Section 1: Architecture Overview
    # ------------------------------------------------------------------
    def _section1_architecture(self) -> str:
        lines = [
            "=" * 60,
            "SECTION 1: ARCHITECTURE OVERVIEW",
            "=" * 60,
            "",
        ]

        # Group files by primary node type
        file_primary_type: dict[str, str] = {}
        file_ring: dict[str, int] = {}
        for n in self.nodes:
            f = n.get("file", "")
            if not f:
                continue
            ntype = n.get("type", "file")
            # Prefer more specific types over "file"
            if f not in file_primary_type or ntype != "file":
                file_primary_type[f] = ntype
            ring = n.get("ring")
            if isinstance(ring, int):
                file_ring[f] = ring

        # Service layer
        services = sorted(
            [f for f, t in file_primary_type.items() if t == "service"],
        )
        lines.append(f"Service Layer ({len(services)} Services):")
        for s in services:
            r = file_ring.get(s, 0)
            reads, writes = self._file_io(s)
            lines.append(f"  +-- {Path(s).name} [Ring {r}: {RING_LABELS.get(r, '?')}]")
            lines.append(f"  |     {len(reads)}R/{len(writes)}W")
        lines.append("")

        # Task layer
        tasks = sorted(
            [f for f, t in file_primary_type.items() if t == "task"],
        )
        lines.append(f"Task Layer ({len(tasks)} Background Jobs):")
        for t in tasks:
            r = file_ring.get(t, 0)
            reads, writes = self._file_io(t)
            lines.append(f"  +-- {Path(t).name} [Ring {r}: {RING_LABELS.get(r, '?')}]")
            lines.append(f"  |     {len(reads)}R/{len(writes)}W")
        lines.append("")

        # Script layer
        scripts = sorted(
            [f for f, t in file_primary_type.items() if t == "script"],
        )
        lines.append(f"Script Layer ({len(scripts)} Scripts):")
        for s in scripts:
            lines.append(f"  +-- {Path(s).name}")
            reads, writes = self._file_io(s)
            lines.append(f"  |     {len(reads)}R/{len(writes)}W")
        lines.append("")

        # Router layer
        routers = sorted(
            [f for f, t in file_primary_type.items() if t in ("router", "endpoint")],
        )
        lines.append(f"Router Layer ({len(routers)} Routers):")
        for rt in routers:
            r = file_ring.get(rt, 0)
            reads, writes = self._file_io(rt)
            lines.append(f"  +-- {Path(rt).name} [Ring {r}: {RING_LABELS.get(r, '?')}]")
            lines.append(f"  |     {len(reads)}R/{len(writes)}W")
        lines.append("")

        # Data layer (collections)
        collections = sorted(
            [n for n in self.nodes if n.get("type") == "collection"],
            key=lambda n: n.get("label", ""),
        )
        lines.append(f"Data Layer ({len(collections)} Collections):")
        for col in collections:
            cid = col["id"]
            w_count = sum(1 for e in self.edges if e.get("target") == cid and e.get("type") == "db_write")
            r_count = sum(1 for e in self.edges if e.get("target") == cid and e.get("type") == "db_read")
            lines.append(f"  +-- {col.get('label', '?')} ({w_count}W/{r_count}R)")
        lines.append("")

        return "\n".join(lines)

    def _file_io(self, file_path: str) -> tuple[list[str], list[str]]:
        """Collect read/write collections for all edges originating from *file_path*."""
        reads: list[str] = []
        writes: list[str] = []
        for e in self.edges:
            if e.get("file") != file_path:
                continue
            target = e.get("target", "")
            col = target.replace("collection:", "") if target.startswith("collection:") else target
            if e.get("type") == "db_read" and col not in reads:
                reads.append(col)
            elif e.get("type") == "db_write" and col not in writes:
                writes.append(col)
        return reads, writes

    # ------------------------------------------------------------------
    # Section 2: Complete Component Registry
    # ------------------------------------------------------------------
    def _section2_registry(self) -> str:
        lines = [
            "=" * 60,
            "SECTION 2: COMPLETE COMPONENT REGISTRY",
            "=" * 60,
            "",
        ]

        for fpath in self.files:
            # Find the primary node for this file
            file_nodes = [n for n in self.nodes if n.get("file") == fpath]
            if not file_nodes:
                continue

            # Pick the most specific node type
            primary = file_nodes[0]
            for fn in file_nodes:
                if fn.get("type") != "file":
                    primary = fn
                    break

            ntype = primary.get("type", "file")
            ring = primary.get("ring", 0)
            ring_label = RING_LABELS.get(ring, "?") if isinstance(ring, int) else "?"

            reads, writes = self._file_io(fpath)

            # Callers: nodes that call into any node in this file
            file_node_ids = {n["id"] for n in file_nodes}
            callers: list[str] = []
            for e in self.edges:
                if e.get("target") in file_node_ids and e.get("source") not in file_node_ids:
                    src = e.get("source", "?")
                    if src not in callers:
                        callers.append(src)

            # Is it a pure function? (no writes, no external API calls, no side effects)
            has_writes = len(writes) > 0
            has_api = any(
                e.get("type") == "api_call"
                for e in self.edges
                if e.get("file") == fpath
            )
            is_pure = not has_writes and not has_api

            filename = Path(fpath).name
            lines.append(f"{filename}")
            lines.append(f"  Path: {fpath}")
            lines.append(f"  Type: {ntype}")
            lines.append(f"  Ring: {ring} ({ring_label})")
            lines.append(f"  IO Profile:")
            lines.append(f"    DB Reads: {', '.join(reads) if reads else '(none)'}")
            lines.append(f"    DB Writes: {', '.join(writes) if writes else '(none)'}")
            lines.append(f"  Pure Function: {'yes' if is_pure else 'no'}")
            lines.append(f"  Callers: {len(callers)} ({', '.join(callers[:10]) if callers else 'none'})")
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Section 3: Complete Data Flows
    # ------------------------------------------------------------------
    def _section3_data_flows(self) -> str:
        lines = [
            "=" * 60,
            "SECTION 3: COMPLETE DATA FLOWS",
            "=" * 60,
            "",
        ]

        # --- Endpoint traces ---
        endpoints = [n for n in self.nodes if n.get("type") == "endpoint"]
        lines.append(f"ALL ENDPOINT TRACES ({len(endpoints)} total)")
        lines.append("")

        for i, ep in enumerate(sorted(endpoints, key=lambda n: n.get("label", "")), 1):
            label = ep.get("label", "?")
            ep_file = ep.get("file", "?")
            ep_id = ep["id"]

            # Trace: follow edges from this endpoint
            read_cols, write_cols = self._trace_endpoint_io(ep_id)
            call_chain = self._trace_call_chain(ep_id, max_depth=5)

            lines.append(f"{i}. {label}")
            lines.append(f"     Handler: {ep_file}")
            lines.append(f"     Reads: {', '.join(read_cols) if read_cols else '(none)'}")
            lines.append(f"     Writes: {', '.join(write_cols) if write_cols else '(none)'}")
            lines.append(f"     Call Chain: {' -> '.join(call_chain) if call_chain else '(direct)'}")
            lines.append("")

        # --- Collection contracts ---
        lines.append("-" * 40)
        lines.append("COMPLETE COLLECTION CONTRACTS")
        lines.append("")

        collections = sorted(
            [n for n in self.nodes if n.get("type") == "collection"],
            key=lambda n: n.get("label", ""),
        )

        for col in collections:
            cid = col["id"]
            col_label = col.get("label", "?")

            writers: list[str] = []
            readers: list[str] = []
            for e in self.edges:
                if e.get("target") != cid:
                    continue
                src = e.get("source", "?")
                src_node = self.node_map.get(src)
                src_label = src_node.get("label", src) if src_node else src
                src_file = e.get("file", "")
                desc = f"{src_label} ({src_file})" if src_file else src_label

                if e.get("type") == "db_write" and desc not in writers:
                    writers.append(desc)
                elif e.get("type") == "db_read" and desc not in readers:
                    readers.append(desc)

            lines.append(f"Collection: {col_label}")
            lines.append(f"  Writers: {len(writers)} components")
            for w in writers:
                lines.append(f"    W: {w}")
            lines.append(f"  Readers: {len(readers)} components")
            for r in readers:
                lines.append(f"    R: {r}")
            lines.append("")

        return "\n".join(lines)

    def _trace_endpoint_io(self, ep_id: str) -> tuple[list[str], list[str]]:
        """Trace all read/write collections reachable from an endpoint."""
        visited: set[str] = set()
        reads: list[str] = []
        writes: list[str] = []

        def walk(nid: str, depth: int = 0) -> None:
            if nid in visited or depth > 8:
                return
            visited.add(nid)
            for e in self.edges:
                if e.get("source") != nid:
                    continue
                target = e.get("target", "")
                etype = e.get("type", "")
                if etype == "db_read":
                    col = target.replace("collection:", "") if target.startswith("collection:") else target
                    if col not in reads:
                        reads.append(col)
                elif etype == "db_write":
                    col = target.replace("collection:", "") if target.startswith("collection:") else target
                    if col not in writes:
                        writes.append(col)
                elif etype in ("calls", "endpoint_handler", "enqueues"):
                    walk(target, depth + 1)

        walk(ep_id)
        return reads, writes

    def _trace_call_chain(self, ep_id: str, max_depth: int = 5) -> list[str]:
        """Build a simplified call chain from an endpoint."""
        chain: list[str] = []
        visited: set[str] = set()

        def walk(nid: str, depth: int = 0) -> None:
            if nid in visited or depth > max_depth:
                return
            visited.add(nid)
            for e in self.edges:
                if e.get("source") != nid:
                    continue
                etype = e.get("type", "")
                if etype in ("calls", "endpoint_handler", "enqueues", "imports"):
                    target = e.get("target", "")
                    target_node = self.node_map.get(target)
                    label = target_node.get("label", target) if target_node else target
                    if label not in chain:
                        chain.append(label)
                    walk(target, depth + 1)

        walk(ep_id)
        return chain

    # ------------------------------------------------------------------
    # Section 4: Dependency Map
    # ------------------------------------------------------------------
    def _section4_dependency_map(self) -> str:
        lines = [
            "=" * 60,
            "SECTION 4: DEPENDENCY MAP",
            "=" * 60,
            "",
        ]

        # Service tiers by caller count
        services = [n for n in self.nodes if n.get("type") == "service"]
        service_callers: dict[str, list[str]] = {}
        for svc in services:
            sid = svc["id"]
            callers = _callers_for_node(sid, self.edges)
            service_callers[sid] = callers

        lines.append("SERVICE TIERS (by usage)")
        lines.append("")

        tier1 = [(s, c) for s, c in service_callers.items() if len(c) >= 5]
        tier2 = [(s, c) for s, c in service_callers.items() if 2 <= len(c) < 5]
        tier3 = [(s, c) for s, c in service_callers.items() if len(c) < 2]

        lines.append("Tier 1 (High Usage, 5+ callers):")
        if tier1:
            for sid, callers in sorted(tier1, key=lambda x: -len(x[1])):
                svc_node = self.node_map.get(sid)
                label = svc_node.get("label", sid) if svc_node else sid
                ring = svc_node.get("ring", "?") if svc_node else "?"
                lines.append(f"  +-- {label} [Ring {ring}] ({len(callers)} callers)")
        else:
            lines.append("  (none)")
        lines.append("")

        lines.append("Tier 2 (Medium Usage, 2-4 callers):")
        if tier2:
            for sid, callers in sorted(tier2, key=lambda x: -len(x[1])):
                svc_node = self.node_map.get(sid)
                label = svc_node.get("label", sid) if svc_node else sid
                ring = svc_node.get("ring", "?") if svc_node else "?"
                lines.append(f"  +-- {label} [Ring {ring}] ({len(callers)} callers)")
        else:
            lines.append("  (none)")
        lines.append("")

        lines.append("Tier 3 (Low Usage, 0-1 callers):")
        if tier3:
            for sid, callers in sorted(tier3, key=lambda x: len(x[1])):
                svc_node = self.node_map.get(sid)
                label = svc_node.get("label", sid) if svc_node else sid
                ring = svc_node.get("ring", "?") if svc_node else "?"
                dead_marker = " <-- potential dead code" if len(callers) == 0 else ""
                lines.append(f"  +-- {label} [Ring {ring}] ({len(callers)} callers){dead_marker}")
        else:
            lines.append("  (none)")
        lines.append("")

        # External API dependencies
        ext_apis = [n for n in self.nodes if n.get("type") == "external_api"]
        lines.append("EXTERNAL API DEPENDENCIES")
        if ext_apis:
            # Group by label, find who uses each
            api_usage: dict[str, list[str]] = defaultdict(list)
            for api in ext_apis:
                api_id = api["id"]
                label = api.get("label", api_id)
                for e in self.edges:
                    if e.get("target") == api_id:
                        src = e.get("source", "?")
                        src_node = self.node_map.get(src)
                        src_label = src_node.get("label", src) if src_node else src
                        if src_label not in api_usage[label]:
                            api_usage[label].append(src_label)
            for api_name, users in sorted(api_usage.items()):
                lines.append(f"  {api_name}: used by {', '.join(users)}")
        else:
            lines.append("  (none)")
        lines.append("")

        # Env var dependencies
        env_vars = [n for n in self.nodes if n.get("type") == "env_var"]
        if env_vars:
            lines.append("ENVIRONMENT VARIABLE DEPENDENCIES")
            env_usage: dict[str, list[str]] = defaultdict(list)
            for ev in env_vars:
                ev_id = ev["id"]
                label = ev.get("label", ev_id)
                for e in self.edges:
                    if e.get("target") == ev_id:
                        src = e.get("source", "?")
                        src_node = self.node_map.get(src)
                        src_label = src_node.get("label", src) if src_node else src
                        if src_label not in env_usage[label]:
                            env_usage[label].append(src_label)
            for var_name, users in sorted(env_usage.items()):
                lines.append(f"  {var_name}: used by {', '.join(users)}")
            lines.append("")

        # Dead code (nodes with 0 incoming edges)
        lines.append("POTENTIAL DEAD CODE (0 incoming edges)")
        all_targeted = {e.get("target") for e in self.edges}
        dead: list[NodeDict] = []
        for n in self.nodes:
            if n["id"] not in all_targeted and n.get("type") not in ("collection", "external_api", "env_var"):
                dead.append(n)
        if dead:
            for d in sorted(dead, key=lambda n: n.get("file", "")):
                lines.append(f"  {d.get('label', d['id'])} ({d.get('file', '?')})")
        else:
            lines.append("  (none detected)")
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Section 5 / Quick Reference (embedded in footer)
    # ------------------------------------------------------------------
    def _quick_reference(self) -> str:
        lines = [
            "=" * 60,
            "SECTION 5: COMPLETE QUICK REFERENCE",
            "=" * 60,
            "",
        ]

        # All endpoints
        endpoints = sorted(
            [n for n in self.nodes if n.get("type") == "endpoint"],
            key=lambda n: n.get("label", ""),
        )
        lines.append(f"All Endpoints ({len(endpoints)}):")
        for ep in endpoints:
            lines.append(f"  {ep.get('label', '?')} -> {ep.get('file', '?')}")
        lines.append("")

        # All services
        services = sorted(
            [n for n in self.nodes if n.get("type") == "service"],
            key=lambda n: n.get("label", ""),
        )
        lines.append(f"All Services ({len(services)}):")
        for svc in services:
            lines.append(f"  {svc.get('label', '?')} ({svc.get('file', '?')})")
        lines.append("")

        # All collections
        collections = sorted(
            [n for n in self.nodes if n.get("type") == "collection"],
            key=lambda n: n.get("label", ""),
        )
        lines.append(f"All Collections ({len(collections)}):")
        for col in collections:
            cid = col["id"]
            w = sum(1 for e in self.edges if e.get("target") == cid and e.get("type") == "db_write")
            r = sum(1 for e in self.edges if e.get("target") == cid and e.get("type") == "db_read")
            lines.append(f"  {col.get('label', '?')} ({w}W/{r}R)")
        lines.append("")

        # All tasks
        tasks = sorted(
            [n for n in self.nodes if n.get("type") == "task"],
            key=lambda n: n.get("label", ""),
        )
        if tasks:
            lines.append(f"All Tasks ({len(tasks)}):")
            for t in tasks:
                lines.append(f"  {t.get('label', '?')} ({t.get('file', '?')})")
            lines.append("")

        # All external APIs
        ext = sorted(
            [n for n in self.nodes if n.get("type") == "external_api"],
            key=lambda n: n.get("label", ""),
        )
        if ext:
            lines.append(f"All External APIs ({len(ext)}):")
            for api in ext:
                lines.append(f"  {api.get('label', '?')} ({api.get('file', '?')})")
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------
    def _footer(self) -> str:
        rc = self.ring_counts
        tc = self.type_counts
        total_queries = (
            len([n for n in self.nodes if n.get("type") == "endpoint"])
            + len(self.files)
            + len([n for n in self.nodes if n.get("type") == "collection"])
        )

        qr = self._quick_reference()

        lines = [
            qr,
            "=" * 60,
            "END OF COMPLETE SYNTHESIS",
            "=" * 60,
            "",
            f"Feature: {self.feature}",
            f"Total Queries: {total_queries}",
            f"Components Analyzed: {len(self.files)}",
            f"Ring 0 (Core): {rc.get(0, 0)}",
            f"Ring 1 (Adjacent): {rc.get(1, 0)}",
            f"Ring 2 (Infrastructure): {rc.get(2, 0)}",
            "",
            "ALL data preserved -- no removals, no summarization",
            "Note: Some graph relationships (call chains) may be incomplete",
            "due to dynamic language features and current static analysis limitations.",
            "",
        ]
        return "\n".join(lines)


# ===================================================================
# CLI
# ===================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="oKode synthesis report generator",
    )
    parser.add_argument(
        "--feature",
        required=True,
        help="Feature name to generate the report for",
    )
    parser.add_argument(
        "--graph-path",
        type=str,
        default=".okode/graph.json",
        help="Path to graph.json (default: .okode/graph.json)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Output path for the report (default: .okode/synthesis/{feature}_synthesis.md)",
    )
    args = parser.parse_args()

    graph_path = Path(args.graph_path)
    if not graph_path.is_absolute():
        graph_path = Path.cwd() / graph_path
    graph_path = graph_path.resolve()

    output_path: Path
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = Path.cwd() / output_path
    else:
        output_path = graph_path.parent / "synthesis" / f"{args.feature}_synthesis.md"
    output_path = output_path.resolve()

    # Load and filter
    print(f"[okode_report] Loading graph from {graph_path}")
    graph = load_graph(graph_path)

    print(f"[okode_report] Filtering for feature: {args.feature}")
    nodes, edges = filter_graph(graph, args.feature)

    if not nodes:
        print(f"[okode_report] No nodes found matching feature '{args.feature}'.")
        print("  Ensure the feature name matches a directory segment or path prefix in the graph.")
        return

    print(f"[okode_report] Found {len(nodes)} nodes and {len(edges)} edges")

    # Build report
    report = SynthesisReport(args.feature, nodes, edges)
    content = report.build()

    # Write
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(f"[okode_report] Report written to {output_path}")

    # Quick summary
    print()
    print(f"  Feature:         {args.feature}")
    print(f"  Files:           {len(report.files)}")
    print(f"  Nodes:           {len(nodes)}")
    print(f"  Edges:           {len(edges)}")
    print(f"  Ring 0 (Core):   {report.ring_counts.get(0, 0)}")
    print(f"  Ring 1 (Adj):    {report.ring_counts.get(1, 0)}")
    print(f"  Ring 2 (Infra):  {report.ring_counts.get(2, 0)}")


if __name__ == "__main__":
    main()
