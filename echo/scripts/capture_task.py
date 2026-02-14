#!/usr/bin/env python3
"""
capture_task.py - Captures user prompts on UserPromptSubmit hook

Receives JSON via stdin with the user's prompt and logs it to .current_tasks
for later inclusion in session summaries.
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from config import get_worklog_dir, log_verbose


# Words that don't indicate a real task
STOP_WORDS = {
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
    "please", "thanks", "help", "yes", "yeah", "yep", "nope", "sure", "okay",
    "ok", "let", "lets", "got", "right", "good", "great", "looks", "sounds",
    "go", "ahead", "done", "fine", "cool", "nice", "perfect", "lgtm",
}

MIN_KEYWORDS = 2


def extract_keywords(text: str) -> list:
    """Extract meaningful keywords from text, filtering stop words."""
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    return [w for w in words if w not in STOP_WORDS]


def main():
    try:
        # Read hook input from stdin
        input_data = sys.stdin.read()
        if not input_data.strip():
            return

        data = json.loads(input_data)

        # Extract the prompt from the hook input
        # UserPromptSubmit provides: {"prompt": "...", ...}
        prompt = data.get("prompt", "").strip()

        # Skip prompts with fewer than 2 meaningful keywords
        if len(extract_keywords(prompt)) < MIN_KEYWORDS:
            return

        # Prepare the task entry
        entry = {
            "ts": datetime.now().isoformat(),
            "prompt": prompt.strip()
        }

        # Append to current tasks file
        worklog_dir = get_worklog_dir()
        tasks_file = worklog_dir / ".current_tasks"

        with open(tasks_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        # Verbose output
        short_prompt = prompt[:50] + "..." if len(prompt) > 50 else prompt
        log_verbose(f"✓ Task: {short_prompt}")

    except Exception:
        # Fail silently - never break the workflow
        pass


if __name__ == "__main__":
    main()
