#!/usr/bin/env python3
"""
config.py - Shared configuration for worklog hooks
"""

import json
import os
from pathlib import Path


def get_worklog_dir() -> Path:
    """Get the worklog directory, creating if needed."""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    worklog_dir = Path(project_dir) / ".claude" / "echo"
    worklog_dir.mkdir(parents=True, exist_ok=True)
    return worklog_dir


def is_verbose() -> bool:
    """Check if verbose output is enabled. Default: True"""
    # Env var takes priority (WORKLOG_VERBOSE=0 to silence)
    env_val = os.environ.get("WORKLOG_VERBOSE")
    if env_val is not None:
        return env_val != "0"

    # Check config file
    try:
        config_file = get_worklog_dir() / "config.json"
        if config_file.exists():
            config = json.loads(config_file.read_text())
            return config.get("verbose", True)
    except Exception:
        pass

    return True  # Verbose by default


def log_verbose(message: str):
    """Print message if verbose mode is enabled."""
    import sys
    if is_verbose():
        print(message, file=sys.stderr)
