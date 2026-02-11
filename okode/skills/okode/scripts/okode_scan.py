#!/usr/bin/env python3
"""
oKode Code Graph Scanner
========================
Hybrid static + LLM analysis scanner that builds a JSON graph of all
runtime/system relationships in a codebase.

Usage:
    python okode_scan.py --full --project-dir /path/to/project
    python okode_scan.py --incremental --skip-llm
    python okode_scan.py --feature auth --output ./custom_graph.json

Requires: Python 3.10+ (stdlib only)
"""

from __future__ import annotations

import argparse
import ast
import datetime
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE = "%Y-%m-%d %H:%M:%S"

logger = logging.getLogger("okode.scan")


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format=LOG_FORMAT, datefmt=LOG_DATE)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Anchor:
    """A structural anchor found by static analysis."""
    file: str
    line: int
    anchor_type: str          # e.g. "route", "model", "task", "env_var", ...
    name: str                 # human-readable identifier
    decorator: str = ""       # decorator text if applicable
    context_lines: str = ""   # surrounding code (~10 lines above/below)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Node:
    id: str                   # e.g. "endpoint:GET:/api/users"
    node_type: str            # endpoint, collection, service, task, ...
    label: str = ""
    file: str = ""
    line: int = 0
    ring: str = ""            # inner / middle / outer classification
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Edge:
    source: str               # node id
    target: str               # node id
    edge_type: str            # calls, reads, writes, triggers, uses, ...
    context: str = ""
    file: str = ""
    line: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Framework detection
# ---------------------------------------------------------------------------

FRAMEWORK_MARKERS = {
    # Python frameworks
    "requirements.txt": "python",
    "pyproject.toml": "python",
    "setup.py": "python",
    "Pipfile": "python",
    # JS/TS
    "package.json": "javascript",
    # Rust
    "Cargo.toml": "rust",
    # Go
    "go.mod": "go",
}

PYTHON_FRAMEWORKS = {
    "fastapi": "fastapi",
    "flask": "flask",
    "django": "django",
    "starlette": "starlette",
    "tornado": "tornado",
    "sanic": "sanic",
}

JS_FRAMEWORKS = {
    "express": "express",
    "next": "nextjs",
    "fastify": "fastify",
    "react": "react",
    "vue": "vue",
    "angular": "angular",
    "svelte": "svelte",
    "nuxt": "nuxtjs",
    "hono": "hono",
}


def detect_frameworks(project_dir: Path) -> dict[str, Any]:
    """Auto-detect project language and frameworks."""
    result: dict[str, Any] = {
        "language": "unknown",
        "frameworks": [],
        "markers_found": [],
    }

    for marker_file, lang in FRAMEWORK_MARKERS.items():
        marker_path = project_dir / marker_file
        if marker_path.exists():
            result["markers_found"].append(marker_file)
            if result["language"] == "unknown":
                result["language"] = lang

    # --- Python sub-detection ---
    if result["language"] == "python":
        combined_text = ""
        for fname in ("requirements.txt", "pyproject.toml", "setup.py", "Pipfile"):
            fpath = project_dir / fname
            if fpath.exists():
                try:
                    combined_text += fpath.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    pass
        lower = combined_text.lower()
        for pkg, fw in PYTHON_FRAMEWORKS.items():
            if pkg in lower:
                result["frameworks"].append(fw)

    # --- JS/TS sub-detection ---
    if result["language"] == "javascript":
        pkg_path = project_dir / "package.json"
        if pkg_path.exists():
            try:
                pkg = json.loads(pkg_path.read_text(encoding="utf-8", errors="replace"))
                all_deps = {}
                all_deps.update(pkg.get("dependencies", {}))
                all_deps.update(pkg.get("devDependencies", {}))
                for pkg_name, fw in JS_FRAMEWORKS.items():
                    if pkg_name in all_deps:
                        result["frameworks"].append(fw)
            except (json.JSONDecodeError, OSError):
                pass

    logger.info("Detected language=%s  frameworks=%s", result["language"], result["frameworks"])
    return result


# ---------------------------------------------------------------------------
# File collection helpers
# ---------------------------------------------------------------------------

PYTHON_EXTS = {".py"}
JS_TS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
ALL_EXTS = PYTHON_EXTS | JS_TS_EXTS

IGNORE_DIRS = {
    "__pycache__", ".git", "node_modules", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".next",
    ".nuxt", ".output", "coverage", ".okode",
}


def collect_files(
    project_dir: Path,
    exts: set[str] | None = None,
    feature: str | None = None,
) -> list[Path]:
    """Walk project_dir and return relevant source files."""
    if exts is None:
        exts = ALL_EXTS

    files: list[Path] = []
    root = project_dir
    if feature:
        # Scope to a subdirectory matching the feature name
        candidates = [
            project_dir / feature,
            project_dir / "src" / feature,
            project_dir / "app" / feature,
            project_dir / "lib" / feature,
        ]
        for c in candidates:
            if c.is_dir():
                root = c
                break
        else:
            # Fallback: search everywhere but filter on path substring
            root = project_dir

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored directories (mutate dirnames in-place)
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        dp = Path(dirpath)
        for fname in filenames:
            fp = dp / fname
            if fp.suffix in exts:
                if feature and root == project_dir:
                    # Substring filter fallback
                    if feature.lower() not in str(fp).lower():
                        continue
                files.append(fp)

    logger.info("Collected %d source files under %s", len(files), root)
    return files


def get_changed_files(project_dir: Path) -> list[Path]:
    """Use git diff to find files changed since last scan."""
    scan_state = project_dir / ".okode" / "scan_state.json"
    last_sha = None
    if scan_state.exists():
        try:
            state = json.loads(scan_state.read_text(encoding="utf-8"))
            last_sha = state.get("last_commit_sha")
        except (json.JSONDecodeError, OSError):
            pass

    try:
        if last_sha:
            result = subprocess.run(
                ["git", "diff", "--name-only", last_sha, "HEAD"],
                capture_output=True, text=True, cwd=str(project_dir), timeout=30,
            )
        else:
            # No previous state — get all tracked files
            result = subprocess.run(
                ["git", "ls-files"],
                capture_output=True, text=True, cwd=str(project_dir), timeout=30,
            )
        if result.returncode != 0:
            logger.warning("git command failed: %s", result.stderr.strip())
            return []

        changed: list[Path] = []
        for line in result.stdout.strip().splitlines():
            fp = project_dir / Path(line.strip())
            if fp.suffix in ALL_EXTS and fp.exists():
                changed.append(fp)
        return changed

    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning("Could not run git: %s", exc)
        return []


def save_scan_state(project_dir: Path) -> None:
    """Persist the current HEAD sha for incremental scans."""
    okode_dir = project_dir / ".okode"
    okode_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=str(project_dir), timeout=10,
        )
        sha = result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        sha = None

    state = {
        "last_commit_sha": sha,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    state_path = okode_dir / "scan_state.json"
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def file_hash(path: Path) -> str:
    """SHA-256 of file contents for dedup / caching."""
    h = hashlib.sha256()
    try:
        h.update(path.read_bytes())
    except OSError:
        pass
    return h.hexdigest()


def extract_context(source_lines: list[str], target_line: int, window: int = 10) -> str:
    """Return surrounding lines as a string for context."""
    start = max(0, target_line - window - 1)
    end = min(len(source_lines), target_line + window)
    return "\n".join(source_lines[start:end])


# ---------------------------------------------------------------------------
# Phase 1: Static Analyzer
# ---------------------------------------------------------------------------

class StaticAnalyzer:
    """
    Uses Python ast module and regex patterns to find structural anchors
    WITHOUT any LLM calls.
    """

    def __init__(self, project_dir: Path, frameworks: list[str]):
        self.project_dir = project_dir
        self.frameworks = frameworks

    def analyze_files(self, files: list[Path]) -> list[Anchor]:
        """Analyze all given files and return anchors."""
        all_anchors: list[Anchor] = []
        for fp in files:
            try:
                rel = fp.relative_to(self.project_dir)
            except ValueError:
                rel = fp
            try:
                source = fp.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.warning("Cannot read %s: %s", fp, exc)
                continue

            if fp.suffix in PYTHON_EXTS:
                anchors = self._analyze_python(str(rel), source)
            elif fp.suffix in JS_TS_EXTS:
                anchors = self._analyze_js_ts(str(rel), source)
            else:
                continue

            all_anchors.extend(anchors)

        logger.info("Static analysis found %d anchors across %d files",
                     len(all_anchors), len(files))
        return all_anchors

    # -----------------------------------------------------------------------
    # Python analysis
    # -----------------------------------------------------------------------

    def _analyze_python(self, rel_path: str, source: str) -> list[Anchor]:
        anchors: list[Anchor] = []
        source_lines = source.splitlines()

        # --- AST-based detection ---
        try:
            tree = ast.parse(source, filename=rel_path)
        except SyntaxError as exc:
            logger.debug("SyntaxError parsing %s: %s", rel_path, exc)
            tree = None

        if tree is not None:
            anchors.extend(self._ast_python_routes(rel_path, tree, source_lines))
            anchors.extend(self._ast_python_models(rel_path, tree, source_lines))
            anchors.extend(self._ast_python_tasks(rel_path, tree, source_lines))
            anchors.extend(self._ast_python_classes(rel_path, tree, source_lines))

        # --- Regex-based detection (works even on partial/broken files) ---
        anchors.extend(self._regex_python_env(rel_path, source_lines))
        anchors.extend(self._regex_python_external_clients(rel_path, source_lines))
        anchors.extend(self._regex_python_cache(rel_path, source_lines))
        anchors.extend(self._regex_python_subprocess(rel_path, source_lines))
        anchors.extend(self._regex_python_db_ops(rel_path, source_lines))

        return anchors

    def _ast_python_routes(self, rel_path: str, tree: ast.Module,
                           source_lines: list[str]) -> list[Anchor]:
        """Detect FastAPI / Flask / Django route decorators."""
        anchors: list[Anchor] = []
        route_patterns = re.compile(
            r"^(app|router|api|blueprint|bp)\."
            r"(get|post|put|patch|delete|head|options|route|api_view|action)"
        )

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                dec_src = ast.get_source_segment(
                    "\n".join(source_lines), dec
                ) or ""
                if not dec_src:
                    # Fallback: reconstruct from AST
                    dec_src = self._decorator_to_str(dec)

                if route_patterns.search(dec_src) or "api_view" in dec_src:
                    method, path = self._extract_route_info(dec_src, dec)
                    name = f"{method.upper()}:{path}" if path else node.name
                    anchors.append(Anchor(
                        file=rel_path,
                        line=node.lineno,
                        anchor_type="route",
                        name=name,
                        decorator=dec_src,
                        context_lines=extract_context(source_lines, node.lineno),
                        metadata={"method": method.upper(), "path": path,
                                  "handler": node.name},
                    ))
        return anchors

    def _ast_python_models(self, rel_path: str, tree: ast.Module,
                           source_lines: list[str]) -> list[Anchor]:
        """Detect SQLAlchemy / Django / Mongoengine model classes."""
        anchors: list[Anchor] = []
        model_bases = {
            "Model", "Base", "DeclarativeBase", "Document",
            "DynamicDocument", "EmbeddedDocument",
            "models.Model", "db.Model", "SQLModel",
        }

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                base_name = self._name_from_node(base)
                if base_name in model_bases or base_name.endswith(".Model"):
                    # Try to extract table/collection name
                    table_name = self._extract_table_name(node) or node.name.lower()
                    anchors.append(Anchor(
                        file=rel_path,
                        line=node.lineno,
                        anchor_type="model",
                        name=node.name,
                        context_lines=extract_context(source_lines, node.lineno),
                        metadata={"class_name": node.name,
                                  "table_or_collection": table_name,
                                  "base": base_name},
                    ))
                    break  # one anchor per class
        return anchors

    def _ast_python_tasks(self, rel_path: str, tree: ast.Module,
                          source_lines: list[str]) -> list[Anchor]:
        """Detect Celery / RQ / Dramatiq task decorators."""
        anchors: list[Anchor] = []
        task_names = {"task", "shared_task", "job", "actor", "dramatiq.actor"}

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                dec_str = self._decorator_to_str(dec)
                for tn in task_names:
                    if tn in dec_str:
                        anchors.append(Anchor(
                            file=rel_path,
                            line=node.lineno,
                            anchor_type="task",
                            name=node.name,
                            decorator=dec_str,
                            context_lines=extract_context(source_lines, node.lineno),
                            metadata={"handler": node.name},
                        ))
                        break
        return anchors

    def _ast_python_classes(self, rel_path: str, tree: ast.Module,
                            source_lines: list[str]) -> list[Anchor]:
        """Detect service / manager / handler classes for the service graph."""
        anchors: list[Anchor] = []
        service_patterns = re.compile(
            r"(Service|Manager|Handler|Controller|Repository|Client|Provider|Factory|Worker)$"
        )
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if service_patterns.search(node.name):
                anchors.append(Anchor(
                    file=rel_path,
                    line=node.lineno,
                    anchor_type="service_class",
                    name=node.name,
                    context_lines=extract_context(source_lines, node.lineno),
                    metadata={"class_name": node.name},
                ))
        return anchors

    # --- Regex-based Python detectors ---

    def _regex_python_env(self, rel_path: str, lines: list[str]) -> list[Anchor]:
        """Detect os.environ / os.getenv calls."""
        anchors: list[Anchor] = []
        pattern = re.compile(
            r"""(?:os\.environ(?:\.get)?\s*[\[\(]\s*["'](\w+)["']|"""
            r"""os\.getenv\s*\(\s*["'](\w+)["'])"""
        )
        for i, line in enumerate(lines, 1):
            for m in pattern.finditer(line):
                var_name = m.group(1) or m.group(2)
                anchors.append(Anchor(
                    file=rel_path, line=i, anchor_type="env_var",
                    name=var_name,
                    context_lines=extract_context(lines, i),
                    metadata={"var_name": var_name},
                ))
        return anchors

    def _regex_python_external_clients(self, rel_path: str,
                                        lines: list[str]) -> list[Anchor]:
        """Detect external client instantiations (boto3, stripe, requests, etc.)."""
        anchors: list[Anchor] = []
        patterns = [
            (re.compile(r"boto3\.\w+\(\s*['\"](\w+)['\"]"), "aws"),
            (re.compile(r"stripe\.\w+"), "stripe"),
            (re.compile(r"requests\.(get|post|put|patch|delete|head)\s*\("), "http_requests"),
            (re.compile(r"requests\.Session\s*\("), "http_session"),
            (re.compile(r"httpx\.\w+"), "httpx"),
            (re.compile(r"aiohttp\.ClientSession"), "aiohttp"),
            (re.compile(r"twilio\.rest\.Client"), "twilio"),
            (re.compile(r"sendgrid\.SendGridAPIClient"), "sendgrid"),
            (re.compile(r"openai\.(?:OpenAI|ChatCompletion|Client)"), "openai"),
            (re.compile(r"anthropic\.(?:Anthropic|Client)"), "anthropic"),
        ]
        for i, line in enumerate(lines, 1):
            for pat, client_name in patterns:
                if pat.search(line):
                    anchors.append(Anchor(
                        file=rel_path, line=i, anchor_type="external_client",
                        name=client_name,
                        context_lines=extract_context(lines, i),
                        metadata={"client": client_name},
                    ))
        return anchors

    def _regex_python_cache(self, rel_path: str, lines: list[str]) -> list[Anchor]:
        """Detect Redis / cache operations."""
        anchors: list[Anchor] = []
        pattern = re.compile(
            r"(?:redis|cache|r|redis_client|redis_conn)\."
            r"(get|set|delete|hget|hset|lpush|rpush|sadd|setex|expire|incr|decr)\s*\("
        )
        for i, line in enumerate(lines, 1):
            m = pattern.search(line)
            if m:
                anchors.append(Anchor(
                    file=rel_path, line=i, anchor_type="cache_op",
                    name=f"cache.{m.group(1)}",
                    context_lines=extract_context(lines, i),
                    metadata={"operation": m.group(1)},
                ))
        return anchors

    def _regex_python_subprocess(self, rel_path: str,
                                  lines: list[str]) -> list[Anchor]:
        """Detect subprocess / os.system calls."""
        anchors: list[Anchor] = []
        pattern = re.compile(
            r"(?:subprocess\.(?:run|call|Popen|check_output|check_call)|os\.system|os\.popen)\s*\("
        )
        for i, line in enumerate(lines, 1):
            if pattern.search(line):
                anchors.append(Anchor(
                    file=rel_path, line=i, anchor_type="subprocess",
                    name="subprocess_call",
                    context_lines=extract_context(lines, i),
                    metadata={},
                ))
        return anchors

    def _regex_python_db_ops(self, rel_path: str,
                              lines: list[str]) -> list[Anchor]:
        """Detect database operations (ORM queries, raw Mongo, etc.)."""
        anchors: list[Anchor] = []
        patterns = [
            # Django ORM
            re.compile(r"(\w+)\.objects\.(filter|get|create|all|exclude|update|delete|aggregate)\s*\("),
            # SQLAlchemy session
            re.compile(r"(?:session|db)\.(query|execute|add|delete|commit|merge|flush)\s*\("),
            # MongoDB raw
            re.compile(r"(?:collection|db)\[\s*['\"](\w+)['\"]\]\.(find|insert|update|delete|aggregate)\s*\("),
            re.compile(r"(?:collection|db)\.(\w+)\.(find|insert_one|insert_many|update_one|update_many|delete_one|delete_many|aggregate|find_one)\s*\("),
        ]
        for i, line in enumerate(lines, 1):
            for pat in patterns:
                m = pat.search(line)
                if m:
                    anchors.append(Anchor(
                        file=rel_path, line=i, anchor_type="db_operation",
                        name=f"db.{m.group(0)[:60]}",
                        context_lines=extract_context(lines, i),
                        metadata={"raw_match": m.group(0)[:120]},
                    ))
                    break  # one per line
        return anchors

    # -----------------------------------------------------------------------
    # JS / TS analysis
    # -----------------------------------------------------------------------

    def _analyze_js_ts(self, rel_path: str, source: str) -> list[Anchor]:
        """Analyze JavaScript/TypeScript files with regex patterns."""
        anchors: list[Anchor] = []
        lines = source.splitlines()

        anchors.extend(self._regex_js_routes(rel_path, lines))
        anchors.extend(self._regex_js_models(rel_path, lines))
        anchors.extend(self._regex_js_queues(rel_path, lines))
        anchors.extend(self._regex_js_fetch(rel_path, lines))
        anchors.extend(self._regex_js_env(rel_path, lines))
        anchors.extend(self._regex_js_cache(rel_path, lines))
        anchors.extend(self._regex_js_components(rel_path, lines, source))
        anchors.extend(self._regex_js_pages(rel_path, lines))

        return anchors

    def _regex_js_routes(self, rel_path: str, lines: list[str]) -> list[Anchor]:
        """Detect Express/Next/Fastify route handlers."""
        anchors: list[Anchor] = []
        # Express-style: app.get('/path', ...) or router.post('/path', ...)
        pattern = re.compile(
            r"(?:app|router|server|fastify)\."
            r"(get|post|put|patch|delete|head|options|all|use)"
            r"""\s*\(\s*["'`](\/[^"'`]*)["'`]"""
        )
        for i, line in enumerate(lines, 1):
            m = pattern.search(line)
            if m:
                method = m.group(1).upper()
                path = m.group(2)
                anchors.append(Anchor(
                    file=rel_path, line=i, anchor_type="route",
                    name=f"{method}:{path}",
                    context_lines=extract_context(lines, i),
                    metadata={"method": method, "path": path},
                ))

        # Next.js API route pattern (export default function handler or
        # export async function GET/POST)
        nextjs_pattern = re.compile(
            r"export\s+(?:default\s+)?(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE|handler)\b"
        )
        for i, line in enumerate(lines, 1):
            m = nextjs_pattern.search(line)
            if m:
                method = m.group(1).upper() if m.group(1) != "handler" else "ALL"
                # Derive path from file path (Next.js convention)
                path = self._nextjs_path_from_file(rel_path)
                anchors.append(Anchor(
                    file=rel_path, line=i, anchor_type="route",
                    name=f"{method}:{path}",
                    context_lines=extract_context(lines, i),
                    metadata={"method": method, "path": path, "framework": "nextjs"},
                ))
        return anchors

    def _regex_js_models(self, rel_path: str, lines: list[str]) -> list[Anchor]:
        """Detect Mongoose/Prisma/TypeORM model definitions."""
        anchors: list[Anchor] = []
        patterns = [
            # Mongoose: mongoose.model('User', ...) or new Schema(...)
            (re.compile(r"""mongoose\.model\s*\(\s*["'](\w+)["']"""), "mongoose"),
            (re.compile(r"""new\s+(?:mongoose\.)?Schema\s*\("""), "mongoose_schema"),
            # Prisma usage: prisma.user.findMany()
            (re.compile(r"""prisma\.(\w+)\.\w+\s*\("""), "prisma"),
            # TypeORM: @Entity()
            (re.compile(r"""@Entity\s*\("""), "typeorm"),
        ]
        for i, line in enumerate(lines, 1):
            for pat, orm in patterns:
                m = pat.search(line)
                if m:
                    name = m.group(1) if m.lastindex and m.lastindex >= 1 else rel_path
                    anchors.append(Anchor(
                        file=rel_path, line=i, anchor_type="model",
                        name=str(name),
                        context_lines=extract_context(lines, i),
                        metadata={"orm": orm},
                    ))
        return anchors

    def _regex_js_queues(self, rel_path: str, lines: list[str]) -> list[Anchor]:
        """Detect Bull/BullMQ queue definitions."""
        anchors: list[Anchor] = []
        pattern = re.compile(
            r"""new\s+(?:Bull|Queue|Worker)\s*\(\s*["'](\w[\w-]*)["']"""
        )
        for i, line in enumerate(lines, 1):
            m = pattern.search(line)
            if m:
                anchors.append(Anchor(
                    file=rel_path, line=i, anchor_type="queue",
                    name=m.group(1),
                    context_lines=extract_context(lines, i),
                    metadata={"queue_name": m.group(1)},
                ))
        return anchors

    def _regex_js_fetch(self, rel_path: str, lines: list[str]) -> list[Anchor]:
        """Detect fetch/axios calls to external URLs."""
        anchors: list[Anchor] = []
        patterns = [
            re.compile(r"""fetch\s*\(\s*["'`](https?://[^"'`]+)["'`]"""),
            re.compile(r"""axios\.(get|post|put|patch|delete)\s*\(\s*["'`](https?://[^"'`]+)["'`]"""),
            re.compile(r"""axios\s*\(\s*\{[^}]*url\s*:\s*["'`](https?://[^"'`]+)["'`]"""),
        ]
        for i, line in enumerate(lines, 1):
            for pat in patterns:
                m = pat.search(line)
                if m:
                    url = m.group(m.lastindex) if m.lastindex else ""
                    anchors.append(Anchor(
                        file=rel_path, line=i, anchor_type="external_fetch",
                        name=url[:120],
                        context_lines=extract_context(lines, i),
                        metadata={"url": url},
                    ))
        return anchors

    def _regex_js_env(self, rel_path: str, lines: list[str]) -> list[Anchor]:
        """Detect process.env references."""
        anchors: list[Anchor] = []
        pattern = re.compile(r"process\.env\.(\w+)")
        for i, line in enumerate(lines, 1):
            for m in pattern.finditer(line):
                anchors.append(Anchor(
                    file=rel_path, line=i, anchor_type="env_var",
                    name=m.group(1),
                    context_lines=extract_context(lines, i),
                    metadata={"var_name": m.group(1)},
                ))
        return anchors

    def _regex_js_cache(self, rel_path: str, lines: list[str]) -> list[Anchor]:
        """Detect Redis/cache client usage in JS/TS."""
        anchors: list[Anchor] = []
        pattern = re.compile(
            r"(?:redis|cache|redisClient|cacheClient)\."
            r"(get|set|del|hget|hset|lpush|rpush|setex|expire|incr|decr)\s*\("
        )
        for i, line in enumerate(lines, 1):
            m = pattern.search(line)
            if m:
                anchors.append(Anchor(
                    file=rel_path, line=i, anchor_type="cache_op",
                    name=f"cache.{m.group(1)}",
                    context_lines=extract_context(lines, i),
                    metadata={"operation": m.group(1)},
                ))
        return anchors

    def _regex_js_components(self, rel_path: str, lines: list[str],
                             source: str) -> list[Anchor]:
        """Detect React component definitions."""
        anchors: list[Anchor] = []
        # Function components: export [default] function ComponentName
        fn_pattern = re.compile(
            r"(?:export\s+(?:default\s+)?)?function\s+([A-Z]\w+)\s*\("
        )
        # Arrow function components: const ComponentName = (...) =>
        arrow_pattern = re.compile(
            r"(?:export\s+(?:default\s+)?)?(?:const|let)\s+([A-Z]\w+)\s*=\s*(?:\([^)]*\)|[A-Za-z_]\w*)\s*=>"
        )
        # Class components: class ComponentName extends React.Component / Component
        class_pattern = re.compile(
            r"class\s+([A-Z]\w+)\s+extends\s+(?:React\.)?(?:Component|PureComponent)"
        )

        seen: set[str] = set()
        for i, line in enumerate(lines, 1):
            for pat in (fn_pattern, arrow_pattern, class_pattern):
                m = pat.search(line)
                if m and m.group(1) not in seen:
                    seen.add(m.group(1))
                    anchors.append(Anchor(
                        file=rel_path, line=i, anchor_type="component",
                        name=m.group(1),
                        context_lines=extract_context(lines, i),
                        metadata={"component_name": m.group(1)},
                    ))
        return anchors

    def _regex_js_pages(self, rel_path: str, lines: list[str]) -> list[Anchor]:
        """Detect Next.js / Nuxt page files based on path conventions."""
        anchors: list[Anchor] = []
        normalized = rel_path.replace("\\", "/")
        page_dirs = ("pages/", "app/", "src/pages/", "src/app/")
        for pd in page_dirs:
            if pd in normalized:
                # Extract the page path from file location
                idx = normalized.index(pd) + len(pd)
                page_path = normalized[idx:]
                # Remove extension and index
                page_path = re.sub(r"\.(tsx?|jsx?|vue)$", "", page_path)
                page_path = re.sub(r"/index$", "", page_path)
                if not page_path:
                    page_path = "/"
                elif not page_path.startswith("/"):
                    page_path = "/" + page_path
                anchors.append(Anchor(
                    file=rel_path, line=1, anchor_type="page",
                    name=page_path,
                    context_lines=extract_context(lines, 1),
                    metadata={"page_path": page_path},
                ))
                break
        return anchors

    # -----------------------------------------------------------------------
    # AST helper methods
    # -----------------------------------------------------------------------

    @staticmethod
    def _decorator_to_str(dec_node: ast.expr) -> str:
        """Best-effort string representation of a decorator AST node."""
        if isinstance(dec_node, ast.Name):
            return dec_node.id
        if isinstance(dec_node, ast.Attribute):
            parts = []
            node = dec_node
            while isinstance(node, ast.Attribute):
                parts.append(node.attr)
                node = node.value
            if isinstance(node, ast.Name):
                parts.append(node.id)
            return ".".join(reversed(parts))
        if isinstance(dec_node, ast.Call):
            func_str = StaticAnalyzer._decorator_to_str(dec_node.func)
            # Try to capture first positional string arg
            args_strs = []
            for arg in dec_node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    args_strs.append(f'"{arg.value}"')
            return f"{func_str}({', '.join(args_strs)})"
        return "<unknown_decorator>"

    @staticmethod
    def _name_from_node(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parts = []
            n = node
            while isinstance(n, ast.Attribute):
                parts.append(n.attr)
                n = n.value
            if isinstance(n, ast.Name):
                parts.append(n.id)
            return ".".join(reversed(parts))
        return ""

    @staticmethod
    def _extract_route_info(dec_src: str, dec_node: ast.expr) -> tuple[str, str]:
        """Extract HTTP method and path from a route decorator."""
        method = "ALL"
        path = ""

        # Method from decorator attribute: app.get, router.post, etc.
        method_match = re.search(
            r"\.(get|post|put|patch|delete|head|options|route|api_view)", dec_src
        )
        if method_match:
            m = method_match.group(1)
            method = m.upper() if m not in ("route", "api_view") else "ALL"

        # Path from first string argument
        path_match = re.search(r"""["'](/[^"']*)["']""", dec_src)
        if path_match:
            path = path_match.group(1)

        return method, path

    @staticmethod
    def _extract_table_name(class_node: ast.ClassDef) -> str | None:
        """Try to extract __tablename__ or Meta.db_table from a class."""
        for item in class_node.body:
            # __tablename__ = "users"
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "__tablename__":
                        if isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                            return item.value.value
            # class Meta: db_table = "users"
            if isinstance(item, ast.ClassDef) and item.name == "Meta":
                for meta_item in item.body:
                    if isinstance(meta_item, ast.Assign):
                        for t in meta_item.targets:
                            if isinstance(t, ast.Name) and t.id == "db_table":
                                if isinstance(meta_item.value, ast.Constant):
                                    return str(meta_item.value.value)
        return None

    @staticmethod
    def _nextjs_path_from_file(rel_path: str) -> str:
        """Convert Next.js file path to route path."""
        normalized = rel_path.replace("\\", "/")
        # Remove prefix up to pages/ or app/
        for prefix in ("src/app/", "app/", "src/pages/", "pages/"):
            if prefix in normalized:
                idx = normalized.index(prefix) + len(prefix)
                route = normalized[idx:]
                break
        else:
            route = normalized

        # Remove route.ts, page.tsx, etc.
        route = re.sub(r"/(route|page)\.(tsx?|jsx?)$", "", route)
        route = re.sub(r"\.(tsx?|jsx?)$", "", route)
        route = re.sub(r"/index$", "", route)
        # Convert [param] to :param
        route = re.sub(r"\[(\w+)\]", r":\1", route)
        if not route.startswith("/"):
            route = "/" + route
        return route


# ---------------------------------------------------------------------------
# Phase 2: LLM Classifier
# ---------------------------------------------------------------------------

class LLMClassifier:
    """
    For each anchor, call the Claude CLI to classify runtime interactions.
    Batches anchors per-file to minimize CLI calls.
    """

    CLASSIFICATION_PROMPT_TEMPLATE = """\
You are analyzing source code to identify runtime relationships in a software system.
Below are code anchors (structural points of interest) from the file `{file_path}`.

For each anchor, determine what runtime edges exist: what does this code read from,
write to, call, trigger, or depend on?

Return a JSON array of edge objects. Each edge:
{{
  "source_type": "<endpoint|service|task|component|page|script>",
  "source_id": "<node_id using convention: type:identifier>",
  "target_type": "<collection|external_api|env_var|service|task|queue|cache|endpoint|component|page>",
  "target_id": "<node_id using convention: type:identifier>",
  "edge_type": "<calls|reads|writes|triggers|uses|depends_on|renders|fetches>",
  "context": "<brief description of the relationship>",
  "line": <line number>
}}

Node ID conventions:
- endpoint:METHOD:/path  (e.g. endpoint:POST:/api/users)
- collection:name  (e.g. collection:users)
- service:module_name  (e.g. service:auth_service)
- task:name  (e.g. task:send_email)
- script:filename  (e.g. script:migrate)
- external_api:name  (e.g. external_api:stripe)
- env_var:NAME  (e.g. env_var:DATABASE_URL)
- component:Name  (e.g. component:UserCard)
- page:/path  (e.g. page:/dashboard)
- queue:name  (e.g. queue:email-jobs)
- cache:operation  (e.g. cache:session_store)

ANCHORS:
{anchors_json}

Return ONLY the JSON array, nothing else. If no edges are found, return [].
"""

    def __init__(self, project_dir: Path, timeout: int = 60):
        self.project_dir = project_dir
        self.timeout = timeout

    def classify_anchors(self, anchors: list[Anchor]) -> list[Edge]:
        """Classify all anchors using the Claude CLI, batched per-file."""
        if not anchors:
            return []

        # Group anchors by file
        by_file: dict[str, list[Anchor]] = {}
        for a in anchors:
            by_file.setdefault(a.file, []).append(a)

        all_edges: list[Edge] = []
        total_files = len(by_file)
        for idx, (file_path, file_anchors) in enumerate(by_file.items(), 1):
            logger.info("LLM classifying file %d/%d: %s (%d anchors)",
                        idx, total_files, file_path, len(file_anchors))
            edges = self._classify_file(file_path, file_anchors)
            all_edges.extend(edges)

        logger.info("LLM classification produced %d edges from %d files",
                     len(all_edges), total_files)
        return all_edges

    def _classify_file(self, file_path: str, anchors: list[Anchor]) -> list[Edge]:
        """Send anchors for a single file to the Claude CLI."""
        # Build a concise representation of anchors
        anchors_data = []
        for a in anchors:
            anchors_data.append({
                "line": a.line,
                "type": a.anchor_type,
                "name": a.name,
                "decorator": a.decorator,
                "context": a.context_lines[:800],  # Truncate to save tokens
                "metadata": a.metadata,
            })

        prompt = self.CLASSIFICATION_PROMPT_TEMPLATE.format(
            file_path=file_path,
            anchors_json=json.dumps(anchors_data, indent=2),
        )

        try:
            result = subprocess.run(
                ["claude", "-p", prompt, "--output-format", "json"],
                capture_output=True, text=True, timeout=self.timeout,
                cwd=str(self.project_dir),
            )

            if result.returncode != 0:
                logger.warning("Claude CLI failed for %s (rc=%d): %s",
                               file_path, result.returncode, result.stderr[:200])
                return []

            return self._parse_llm_response(result.stdout, file_path)

        except subprocess.TimeoutExpired:
            logger.warning("Claude CLI timed out for %s", file_path)
            return []
        except FileNotFoundError:
            logger.error("Claude CLI not found. Install it or use --skip-llm.")
            return []
        except Exception as exc:
            logger.warning("Unexpected error calling Claude CLI for %s: %s",
                           file_path, exc)
            return []

    def _parse_llm_response(self, raw_output: str, file_path: str) -> list[Edge]:
        """Parse the JSON response from the Claude CLI."""
        edges: list[Edge] = []

        # The Claude CLI with --output-format json wraps the response.
        # Try to extract the inner result.
        text = raw_output.strip()

        # Attempt to parse as direct JSON first
        parsed = self._try_parse_json(text)

        # If wrapped in a Claude CLI envelope, try to extract .result
        if isinstance(parsed, dict) and "result" in parsed:
            inner = parsed["result"]
            if isinstance(inner, str):
                parsed = self._try_parse_json(inner)
            elif isinstance(inner, list):
                parsed = inner

        # If still a string, try to find JSON array within it
        if isinstance(parsed, str):
            parsed = self._extract_json_array(parsed)

        if not isinstance(parsed, list):
            logger.debug("Could not parse LLM output for %s as array", file_path)
            return edges

        for item in parsed:
            if not isinstance(item, dict):
                continue
            try:
                edge = Edge(
                    source=item.get("source_id", ""),
                    target=item.get("target_id", ""),
                    edge_type=item.get("edge_type", "unknown"),
                    context=item.get("context", ""),
                    file=file_path,
                    line=int(item.get("line", 0)),
                )
                if edge.source and edge.target:
                    edges.append(edge)
            except (ValueError, TypeError) as exc:
                logger.debug("Skipping malformed edge: %s", exc)

        return edges

    @staticmethod
    def _try_parse_json(text: str) -> Any:
        """Attempt to parse text as JSON, return original string on failure."""
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text

    @staticmethod
    def _extract_json_array(text: str) -> list | str:
        """Try to extract a JSON array from text that may contain markdown fences."""
        # Strip markdown code fences
        cleaned = re.sub(r"```(?:json)?\s*", "", text)
        cleaned = re.sub(r"```\s*$", "", cleaned)

        # Find the first [ ... ] block
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return text


# ---------------------------------------------------------------------------
# Phase 3: Graph Assembler
# ---------------------------------------------------------------------------

class GraphAssembler:
    """
    Stitch classified edges and detected nodes into a unified graph JSON.
    Handles deduplication, ring classification, and index generation.
    """

    RING_MAP = {
        "route": "inner",
        "page": "inner",
        "component": "inner",
        "endpoint": "inner",
        "service_class": "middle",
        "service": "middle",
        "task": "middle",
        "queue": "middle",
        "model": "outer",
        "collection": "outer",
        "db_operation": "outer",
        "cache_op": "outer",
        "external_client": "outer",
        "external_fetch": "outer",
        "external_api": "outer",
        "env_var": "outer",
        "subprocess": "outer",
        "script": "middle",
    }

    def __init__(self, project_dir: Path, ring_root: Path | None = None):
        self.project_dir = project_dir
        self.ring_root = ring_root or project_dir
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []

    def build_graph(self, anchors: list[Anchor], llm_edges: list[Edge]) -> dict:
        """Build the complete graph from anchors and LLM-classified edges."""
        # --- Create nodes from anchors ---
        for a in anchors:
            node_id = self._anchor_to_node_id(a)
            if node_id in self.nodes:
                # Merge: keep earliest line, accumulate metadata
                existing = self.nodes[node_id]
                if a.line < existing.line or not existing.file:
                    existing.file = a.file
                    existing.line = a.line
                existing.metadata.update(a.metadata)
            else:
                self.nodes[node_id] = Node(
                    id=node_id,
                    node_type=a.anchor_type,
                    label=a.name,
                    file=a.file,
                    line=a.line,
                    ring=self._classify_ring(a.anchor_type, a.file),
                    metadata=a.metadata,
                )

        # --- Create nodes from LLM edges (both source and target) ---
        for edge in llm_edges:
            for nid in (edge.source, edge.target):
                if nid and nid not in self.nodes:
                    ntype = nid.split(":")[0] if ":" in nid else "unknown"
                    self.nodes[nid] = Node(
                        id=nid,
                        node_type=ntype,
                        label=nid.split(":", 1)[-1] if ":" in nid else nid,
                        file=edge.file,
                        line=edge.line,
                        ring=self._classify_ring(ntype, edge.file),
                    )

        # --- Deduplicate edges ---
        seen_edges: set[tuple[str, str, str]] = set()
        for edge in llm_edges:
            key = (edge.source, edge.target, edge.edge_type)
            if key not in seen_edges:
                seen_edges.add(key)
                self.edges.append(edge)

        # --- Also create implicit edges from anchors ---
        self._create_implicit_edges(anchors, seen_edges)

        graph = {
            "version": "1.0.0",
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "project_dir": str(self.project_dir),
            "summary": {
                "total_nodes": len(self.nodes),
                "total_edges": len(self.edges),
                "node_types": self._count_by(
                    [n.node_type for n in self.nodes.values()]
                ),
                "edge_types": self._count_by(
                    [e.edge_type for e in self.edges]
                ),
                "rings": self._count_by(
                    [n.ring for n in self.nodes.values()]
                ),
            },
            "nodes": [n.to_dict() for n in sorted(
                self.nodes.values(), key=lambda n: (n.ring, n.node_type, n.id)
            )],
            "edges": [e.to_dict() for e in self.edges],
        }

        return graph

    def write_graph(self, graph: dict, output_path: Path) -> None:
        """Write graph JSON to disk."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(graph, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Graph written to %s", output_path)

    def generate_index(self, graph: dict, index_path: Path) -> None:
        """Generate a condensed markdown index of the graph."""
        lines: list[str] = []
        summary = graph.get("summary", {})
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])

        lines.append("# oKode Graph Index")
        lines.append("")
        lines.append(f"Generated: {graph.get('generated_at', 'unknown')}")
        lines.append(f"Project: {graph.get('project_dir', 'unknown')}")
        lines.append("")

        # --- Project Summary ---
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- Total nodes: {summary.get('total_nodes', 0)}")
        lines.append(f"- Total edges: {summary.get('total_edges', 0)}")
        node_types = summary.get("node_types", {})
        for nt, count in sorted(node_types.items(), key=lambda x: -x[1]):
            lines.append(f"  - {nt}: {count}")
        lines.append("")

        # --- Entrypoints ---
        endpoints = [n for n in nodes if n.get("node_type") in ("route", "endpoint")]
        if endpoints:
            lines.append("## Entrypoints")
            lines.append("")
            for ep in endpoints[:50]:  # Cap at 50
                handler = ep.get("metadata", {}).get("handler", "")
                handler_str = f" -> {handler}" if handler else ""
                lines.append(f"- `{ep['id']}` ({ep.get('file', '?')}:{ep.get('line', '?')}){handler_str}")
            if len(endpoints) > 50:
                lines.append(f"- ... and {len(endpoints) - 50} more")
            lines.append("")

        # --- Hotspots (most connected nodes) ---
        connection_count: dict[str, int] = {}
        for edge in edges:
            connection_count[edge.get("source", "")] = connection_count.get(edge.get("source", ""), 0) + 1
            connection_count[edge.get("target", "")] = connection_count.get(edge.get("target", ""), 0) + 1

        if connection_count:
            lines.append("## Hotspots (Top 10 Most Connected)")
            lines.append("")
            top = sorted(connection_count.items(), key=lambda x: -x[1])[:10]
            for nid, count in top:
                node_info = next((n for n in nodes if n["id"] == nid), None)
                file_info = f" ({node_info['file']})" if node_info and node_info.get("file") else ""
                lines.append(f"- `{nid}` — {count} connections{file_info}")
            lines.append("")

        # --- Risk Boundaries ---
        external_apis = [n for n in nodes if n.get("node_type") in (
            "external_client", "external_fetch", "external_api"
        )]
        env_vars = [n for n in nodes if n.get("node_type") == "env_var"]

        if external_apis or env_vars:
            lines.append("## Risk Boundaries")
            lines.append("")
            if external_apis:
                lines.append("### External APIs")
                for api in external_apis[:20]:
                    lines.append(f"- `{api['id']}` ({api.get('file', '?')}:{api.get('line', '?')})")
                lines.append("")
            if env_vars:
                lines.append("### Environment Variables")
                seen_vars: set[str] = set()
                for ev in env_vars:
                    var_name = ev.get("metadata", {}).get("var_name", ev["label"])
                    if var_name not in seen_vars:
                        seen_vars.add(var_name)
                        lines.append(f"- `{var_name}` ({ev.get('file', '?')}:{ev.get('line', '?')})")
                lines.append("")

        # --- Known Issues ---
        lines.append("## Known Issues")
        lines.append("")
        orphan_nodes = [n for n in nodes if n["id"] not in connection_count]
        if orphan_nodes:
            lines.append(f"- {len(orphan_nodes)} orphan nodes (no edges)")
        lines.append("- Graph may be incomplete without LLM classification (--skip-llm)")
        lines.append("")

        # Truncate to ~200 lines
        if len(lines) > 200:
            lines = lines[:197]
            lines.append("")
            lines.append("... (truncated to 200 lines)")
            lines.append("")

        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Graph index written to %s", index_path)

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _anchor_to_node_id(self, anchor: Anchor) -> str:
        """Convert an anchor into a canonical node ID."""
        atype = anchor.anchor_type
        meta = anchor.metadata

        if atype == "route":
            method = meta.get("method", "ALL")
            path = meta.get("path", anchor.name)
            return f"endpoint:{method}:{path}"

        if atype == "model":
            table = meta.get("table_or_collection", anchor.name.lower())
            return f"collection:{table}"

        if atype == "task":
            return f"task:{anchor.name}"

        if atype == "service_class":
            return f"service:{anchor.name}"

        if atype == "env_var":
            return f"env_var:{meta.get('var_name', anchor.name)}"

        if atype == "external_client":
            return f"external_api:{meta.get('client', anchor.name)}"

        if atype == "external_fetch":
            # Try to extract domain from URL
            url = meta.get("url", anchor.name)
            domain_match = re.search(r"https?://([^/]+)", url)
            domain = domain_match.group(1) if domain_match else url[:60]
            return f"external_api:{domain}"

        if atype == "cache_op":
            return f"cache:{anchor.name}"

        if atype == "subprocess":
            return f"script:{Path(anchor.file).stem}"

        if atype == "db_operation":
            return f"collection:{anchor.name[:60]}"

        if atype == "queue":
            return f"queue:{anchor.name}"

        if atype == "component":
            return f"component:{anchor.name}"

        if atype == "page":
            return f"page:{anchor.name}"

        # Fallback
        return f"{atype}:{anchor.name}"

    def _classify_ring(self, node_type: str, file_path: str) -> str:
        """Classify a node into inner / middle / outer ring."""
        ring = self.RING_MAP.get(node_type, "middle")

        # Additional heuristics based on file path
        normalized = file_path.replace("\\", "/").lower()
        if any(p in normalized for p in ("/api/", "/routes/", "/views/", "/endpoints/", "/controllers/")):
            if ring == "middle":
                ring = "inner"
        if any(p in normalized for p in ("/models/", "/schemas/", "/entities/")):
            if ring == "middle":
                ring = "outer"
        if any(p in normalized for p in ("/services/", "/tasks/", "/workers/", "/jobs/")):
            ring = "middle"

        return ring

    def _create_implicit_edges(self, anchors: list[Anchor],
                                seen: set[tuple[str, str, str]]) -> None:
        """Create edges that can be inferred without LLM classification."""
        # env_var -> file service edge
        for a in anchors:
            if a.anchor_type == "env_var":
                source_module = Path(a.file).stem
                source_id = f"service:{source_module}"
                target_id = f"env_var:{a.metadata.get('var_name', a.name)}"
                key = (source_id, target_id, "uses")
                if key not in seen:
                    seen.add(key)
                    self.edges.append(Edge(
                        source=source_id, target=target_id,
                        edge_type="uses",
                        context=f"Reads environment variable {a.name}",
                        file=a.file, line=a.line,
                    ))
                    # Ensure the service node exists
                    if source_id not in self.nodes:
                        self.nodes[source_id] = Node(
                            id=source_id, node_type="service",
                            label=source_module, file=a.file,
                            line=0, ring="middle",
                        )

            elif a.anchor_type == "external_client":
                source_module = Path(a.file).stem
                source_id = f"service:{source_module}"
                target_id = self._anchor_to_node_id(a)
                key = (source_id, target_id, "calls")
                if key not in seen:
                    seen.add(key)
                    self.edges.append(Edge(
                        source=source_id, target=target_id,
                        edge_type="calls",
                        context=f"Uses external client {a.name}",
                        file=a.file, line=a.line,
                    ))

            elif a.anchor_type == "cache_op":
                source_module = Path(a.file).stem
                source_id = f"service:{source_module}"
                target_id = self._anchor_to_node_id(a)
                edge_type = "reads" if "get" in a.name else "writes"
                key = (source_id, target_id, edge_type)
                if key not in seen:
                    seen.add(key)
                    self.edges.append(Edge(
                        source=source_id, target=target_id,
                        edge_type=edge_type,
                        context=f"Cache operation: {a.name}",
                        file=a.file, line=a.line,
                    ))

    @staticmethod
    def _count_by(items: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            counts[item] = counts.get(item, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: -x[1]))


# ---------------------------------------------------------------------------
# Main Scanner Orchestrator
# ---------------------------------------------------------------------------

class Scanner:
    """Orchestrates the full scan pipeline: detect -> collect -> analyze -> classify -> assemble."""

    def __init__(self, args: argparse.Namespace):
        self.project_dir = Path(args.project_dir).resolve()
        self.output_path = Path(args.output).resolve() if args.output else (
            self.project_dir / ".okode" / "graph.json"
        )
        self.index_path = self.output_path.parent / "graph_index.md"
        self.ring_root = Path(args.ring_root).resolve() if args.ring_root else None
        self.full_scan = args.full
        self.incremental = args.incremental
        self.feature = args.feature
        self.skip_llm = args.skip_llm

        if not self.project_dir.is_dir():
            logger.error("Project directory does not exist: %s", self.project_dir)
            sys.exit(1)

    def run(self) -> None:
        """Execute the full scan pipeline."""
        t_start = time.monotonic()
        logger.info("=" * 60)
        logger.info("oKode Scanner starting")
        logger.info("  Project: %s", self.project_dir)
        logger.info("  Mode: %s", self._mode_label())
        logger.info("  LLM: %s", "disabled" if self.skip_llm else "enabled")
        logger.info("  Output: %s", self.output_path)
        logger.info("=" * 60)

        # --- Framework detection ---
        fw_info = detect_frameworks(self.project_dir)

        # --- Determine which file extensions to scan ---
        lang = fw_info["language"]
        if lang == "python":
            exts = PYTHON_EXTS
        elif lang == "javascript":
            exts = JS_TS_EXTS
        else:
            exts = ALL_EXTS  # scan everything

        # --- Collect files ---
        if self.incremental and not self.full_scan:
            files = get_changed_files(self.project_dir)
            if not files:
                logger.info("No changed files found. Running full collection as fallback.")
                files = collect_files(self.project_dir, exts, self.feature)
        else:
            files = collect_files(self.project_dir, exts, self.feature)

        if not files:
            logger.warning("No source files found. Nothing to scan.")
            return

        # --- Phase 1: Static analysis ---
        logger.info("-" * 40)
        logger.info("Phase 1: Static Analysis")
        t_static = time.monotonic()

        analyzer = StaticAnalyzer(self.project_dir, fw_info["frameworks"])
        anchors = analyzer.analyze_files(files)

        dt_static = time.monotonic() - t_static
        logger.info("Phase 1 complete: %d anchors in %.2fs", len(anchors), dt_static)

        # --- Phase 2: LLM classification ---
        llm_edges: list[Edge] = []
        if not self.skip_llm:
            logger.info("-" * 40)
            logger.info("Phase 2: LLM Classification")
            t_llm = time.monotonic()

            classifier = LLMClassifier(self.project_dir)
            llm_edges = classifier.classify_anchors(anchors)

            dt_llm = time.monotonic() - t_llm
            logger.info("Phase 2 complete: %d edges in %.2fs", len(llm_edges), dt_llm)
        else:
            logger.info("Phase 2: Skipped (--skip-llm)")

        # --- Phase 3: Graph assembly ---
        logger.info("-" * 40)
        logger.info("Phase 3: Graph Assembly")
        t_assemble = time.monotonic()

        assembler = GraphAssembler(self.project_dir, self.ring_root)
        graph = assembler.build_graph(anchors, llm_edges)
        assembler.write_graph(graph, self.output_path)
        assembler.generate_index(graph, self.index_path)

        dt_assemble = time.monotonic() - t_assemble
        logger.info("Phase 3 complete in %.2fs", dt_assemble)

        # --- Save scan state for incremental ---
        save_scan_state(self.project_dir)

        # --- Summary ---
        dt_total = time.monotonic() - t_start
        summary = graph.get("summary", {})
        logger.info("=" * 60)
        logger.info("SCAN COMPLETE")
        logger.info("  Duration:    %.2fs", dt_total)
        logger.info("  Files:       %d", len(files))
        logger.info("  Anchors:     %d", len(anchors))
        logger.info("  Nodes:       %d", summary.get("total_nodes", 0))
        logger.info("  Edges:       %d", summary.get("total_edges", 0))
        logger.info("  Node types:  %s", summary.get("node_types", {}))
        logger.info("  Edge types:  %s", summary.get("edge_types", {}))
        logger.info("  Rings:       %s", summary.get("rings", {}))
        logger.info("  Graph:       %s", self.output_path)
        logger.info("  Index:       %s", self.index_path)
        logger.info("=" * 60)

    def _mode_label(self) -> str:
        parts = []
        if self.full_scan:
            parts.append("full")
        elif self.incremental:
            parts.append("incremental")
        else:
            parts.append("full (default)")
        if self.feature:
            parts.append(f"feature={self.feature}")
        return ", ".join(parts)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="okode_scan",
        description="oKode Code Graph Scanner — hybrid static + LLM analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python okode_scan.py --full --project-dir ./my-project
  python okode_scan.py --incremental --skip-llm
  python okode_scan.py --feature auth --output ./auth_graph.json
  python okode_scan.py --full --skip-llm --project-dir /path/to/project
""",
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--full", action="store_true", default=False,
        help="Full rescan of entire project",
    )
    mode.add_argument(
        "--incremental", action="store_true", default=False,
        help="Only scan files changed since last scan (uses git diff)",
    )

    parser.add_argument(
        "--feature", type=str, default=None,
        help="Scope scan to a specific feature/directory name",
    )
    parser.add_argument(
        "--skip-llm", action="store_true", default=False,
        help="Static pass only — fast, no Claude CLI calls",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output path for graph JSON (default: .okode/graph.json)",
    )
    parser.add_argument(
        "--ring-root", type=str, default=None,
        help="Root directory for ring classification",
    )
    parser.add_argument(
        "--project-dir", type=str, default=".",
        help="Project root directory (default: current working directory)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", default=False,
        help="Enable debug-level logging",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    scanner = Scanner(args)
    scanner.run()


if __name__ == "__main__":
    main()
