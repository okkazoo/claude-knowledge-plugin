#!/usr/bin/env python
"""
oKode Post-Task Hook

After Write or Edit tool use, incrementally updates the code graph
by calling okode_sync.py on the modified file. Drift warnings are
emitted to stderr so Claude can see them.

Exit 0 always — never block tool execution.
"""

import json
import subprocess
import sys
from pathlib import Path

# Source file extensions that should trigger graph updates
SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".svelte",
}


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    # Only act on Write or Edit tool invocations
    tool_name = input_data.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        sys.exit(0)

    # Extract the file path from tool_input
    tool_input = input_data.get("tool_input", {})
    file_path_str = tool_input.get("file_path", "")
    if not file_path_str:
        sys.exit(0)

    file_path = Path(file_path_str)

    # Only process source files
    if file_path.suffix.lower() not in SOURCE_EXTENSIONS:
        sys.exit(0)

    # Determine project directory from cwd
    project_dir = Path(input_data.get("cwd", ".")).resolve()

    # Find the sync script — check plugin root first, then project paths
    plugin_root = Path(__file__).resolve().parent.parent
    sync_script = plugin_root / "skills" / "okode" / "scripts" / "okode_sync.py"

    if not sync_script.is_file():
        # Fallback: check project-local .claude paths
        for candidate in [
            project_dir / ".claude" / "skills" / "okode" / "scripts" / "okode_sync.py",
            project_dir / ".claude" / "hooks" / "okode_sync.py",
        ]:
            if candidate.is_file():
                sync_script = candidate
                break
        else:
            sys.exit(0)

    try:
        result = subprocess.run(
            [sys.executable, str(sync_script), "--files", str(file_path)],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=25,
        )

        # Check output for drift warnings and relay to stderr
        combined_output = (result.stdout or "") + "\n" + (result.stderr or "")
        drift_lines = []
        for line in combined_output.splitlines():
            lower = line.lower()
            if any(
                kw in lower
                for kw in ["drift", "warning", "mismatch", "stale", "orphan"]
            ):
                drift_lines.append(line.strip())

        if drift_lines:
            msg = "oKode drift warning:\n" + "\n".join(f"  {d}" for d in drift_lines)
            print(msg, file=sys.stderr)

    except subprocess.TimeoutExpired:
        print("oKode: sync timed out for " + str(file_path), file=sys.stderr)
    except Exception as exc:
        print(f"oKode: sync error — {exc}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never crash, never block
        sys.exit(0)
