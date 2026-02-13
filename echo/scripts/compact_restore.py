#!/usr/bin/env python3
"""
compact_restore.py - Restore context after auto-compaction

Reads .compact_handover.md and injects it as additionalContext
so Claude picks up where it left off after compaction.
"""

import json
import sys
from pathlib import Path

from config import get_worklog_dir, log_verbose


def main():
    try:
        worklog_dir = get_worklog_dir()
        handover_file = worklog_dir / ".compact_handover.md"

        if not handover_file.exists():
            # No handover data — output empty context
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": ""
                }
            }
            print(json.dumps(output))
            return

        content = handover_file.read_text(encoding="utf-8", errors="ignore").strip()

        if not content:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": ""
                }
            }
            print(json.dumps(output))
            return

        # Inject handover as context
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": f"Echo: Restored after compaction:\n\n{content}"
            }
        }

        log_verbose("✓ Echo: restored session context after compaction")
        print(json.dumps(output))

        # Clean up handover file after restoring
        try:
            handover_file.unlink()
        except Exception:
            pass

    except Exception:
        # On error, output empty context
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": ""
            }
        }
        print(json.dumps(output))


if __name__ == "__main__":
    main()
