#!/usr/bin/env python
"""
oKode Pre-Session Hook

Injects the graph index into Claude's context at session start.
Reads .okode/graph_index.md and recent drift warnings from .okode/history/.

Exit 0 always — never block session start.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def get_recent_drift_warnings(history_dir: Path, hours: int = 24) -> str:
    """Scan recent diff files in .okode/history/ for drift warnings."""
    if not history_dir.is_dir():
        return ""

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    warnings = []

    try:
        for diff_file in sorted(history_dir.iterdir(), reverse=True):
            if not diff_file.is_file():
                continue

            # Check file modification time against cutoff
            mtime = datetime.fromtimestamp(diff_file.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                break

            content = diff_file.read_text(encoding="utf-8", errors="replace")

            # Extract lines that look like drift warnings
            for line in content.splitlines():
                lower = line.lower()
                if any(
                    kw in lower
                    for kw in ["drift", "warning", "mismatch", "stale", "orphan"]
                ):
                    warnings.append(line.strip())
    except Exception:
        pass

    if not warnings:
        return "No drift warnings in the last 24 hours."

    # Deduplicate and limit
    seen = set()
    unique = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    unique = unique[:20]

    return "Drift warnings (last 24h):\n" + "\n".join(f"- {w}" for w in unique)


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except Exception:
        input_data = {}

    # Determine project directory from input JSON
    project_dir = Path(input_data.get("cwd", ".")).resolve()
    okode_dir = project_dir / ".okode"
    graph_index_path = okode_dir / "graph_index.md"

    if graph_index_path.is_file():
        try:
            content = graph_index_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            content = "(Error reading graph_index.md)"

        drift_summary = get_recent_drift_warnings(okode_dir / "history")

        context = (
            f"# oKode Graph Index\n\n{content}\n\n"
            f"## Recent Changes\n\n{drift_summary}"
        )
    else:
        context = (
            "oKode: No code graph found. "
            "Run /okode-scan --full to build the code graph."
        )

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }

    json.dump(output, sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never crash, never block session start
        fallback = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "oKode: Pre-session hook encountered an error. Graph context unavailable.",
            }
        }
        json.dump(fallback, sys.stdout)
        sys.exit(0)
