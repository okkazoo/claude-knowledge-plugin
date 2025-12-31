#!/usr/bin/env python3
"""
Helper functions for knowledge-base plugin commands.
"""

import json
import re
from datetime import datetime
from pathlib import Path


def ensure_facts_folder():
    """Ensure the facts/ folder exists."""
    facts_dir = Path('.claude/knowledge/facts')
    facts_dir.mkdir(parents=True, exist_ok=True)
    return facts_dir


def save_fact(fact_text, slug=None):
    """Save a fact/gotcha to facts/ folder."""
    facts_dir = ensure_facts_folder()
    timestamp = datetime.now()
    date_prefix = timestamp.strftime('%Y-%m-%d')

    if not slug:
        words = re.sub(r'[^a-zA-Z0-9\s]', '', fact_text.lower()).split()[:5]
        slug = '-'.join(words) if words else 'fact'
        slug = slug[:50]

    filename = f"{date_prefix}-{slug}.md"
    file_path = facts_dir / filename

    counter = 1
    while file_path.exists():
        filename = f"{date_prefix}-{slug}-{counter}.md"
        file_path = facts_dir / filename
        counter += 1

    content = f"""# Fact: {fact_text[:60]}{'...' if len(fact_text) > 60 else ''}

## Date: {timestamp.strftime('%Y-%m-%d %H:%M')}

{fact_text}
"""

    file_path.write_text(content, encoding='utf-8')
    return file_path


def count_facts():
    """Count total fact files."""
    facts_dir = Path('.claude/knowledge/facts')
    if not facts_dir.exists():
        return 0
    return len([f for f in facts_dir.glob('*.md')])


def get_knowledge_status(full=False):
    """Get formatted knowledge base status."""
    import subprocess

    version_file = Path('VERSION')
    version = version_file.read_text().strip() if version_file.exists() else '0.1.0'

    try:
        result = subprocess.run(['git', 'rev-parse', '--git-dir'],
                              capture_output=True, text=True, timeout=5)
        is_git = result.returncode == 0
    except:
        is_git = False

    if is_git:
        try:
            branch = subprocess.run(['git', 'branch', '--show-current'],
                                   capture_output=True, text=True, timeout=5).stdout.strip()
            git_info = branch or 'unknown'
        except:
            git_info = 'unknown'
    else:
        git_info = 'not a git repo'

    journey_dir = Path('.claude/knowledge/journey')
    journey_count = 0
    if journey_dir.exists():
        for item in journey_dir.iterdir():
            if item.is_dir() and not item.name.startswith(('_', '.')):
                journey_count += 1

    facts_count = count_facts()

    knowledge_json_path = Path('.claude/knowledge/knowledge.json')
    pattern_count = 0
    if knowledge_json_path.exists():
        try:
            data = json.loads(knowledge_json_path.read_text(encoding='utf-8'))
            pattern_count = len(data.get('patterns', []))
        except:
            pass

    checkpoints_dir = Path('.claude/knowledge/checkpoints')
    checkpoint_count = 0
    if checkpoints_dir.exists():
        try:
            checkpoint_count = len([f for f in checkpoints_dir.glob('*.md') if not f.name.startswith('.')])
        except:
            pass

    lines = [
        "# Knowledge Base Status",
        "",
        f"**Version:** {version}  |  **Branch:** {git_info}",
        "",
        "## Stats",
        "| Journeys | Facts | Patterns | Checkpoints |",
        "|----------|-------|----------|-------------|",
        f"| {journey_count}        | {facts_count}     | {pattern_count}        | {checkpoint_count}           |",
        "",
        "---",
        "**Commands:** `/knowledge-base:wip` - `/knowledge-base:checkpoint` - `/knowledge-base:knowledge`"
    ]

    return '\n'.join(lines)


def reset_knowledge(archive=False, dry_run=True):
    """Reset knowledge base to factory defaults."""
    import shutil

    knowledge_dir = Path('.claude/knowledge')

    if dry_run:
        lines = [
            "# Knowledge Base Reset",
            "",
            "This will reset the knowledge base to factory defaults.",
            "",
            "Options:",
            "  1. Archive & Reset - Save current knowledge, then reset",
            "  2. Full Reset - Delete all knowledge permanently",
            "  3. Cancel",
        ]
        return '\n'.join(lines)

    timestamp = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')

    if archive:
        archive_dir = Path(f'.claude/knowledge-archive-{timestamp}')
        if knowledge_dir.exists():
            shutil.copytree(knowledge_dir, archive_dir)

    for subdir in ['journey', 'facts', 'checkpoints', 'versions']:
        folder = knowledge_dir / subdir
        if folder.exists():
            for item in folder.iterdir():
                if item.is_file() and item.name != '.gitkeep':
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)

    (knowledge_dir / 'coderef.json').write_text(json.dumps({
        "version": 1, "updated": None, "files": {}
    }, indent=2))

    (knowledge_dir / 'knowledge.json').write_text(json.dumps({
        "version": 1, "updated": None, "files": {}, "patterns": []
    }, indent=2))

    Path('VERSION').write_text('0.1.0\n')

    return "Knowledge base reset to factory defaults."


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: _wip_helpers.py <command> [args]")
        sys.exit(1)

    command = sys.argv[1]

    if command == 'save_fact':
        if len(sys.argv) < 3:
            print("Error: fact text required")
            sys.exit(1)
        fact_text = ' '.join(sys.argv[2:])
        file_path = save_fact(fact_text)
        print(json.dumps({
            'success': True,
            'file': str(file_path),
            'count': count_facts()
        }))

    elif command == 'knowledge_status':
        full = '-full' in sys.argv
        print(get_knowledge_status(full=full))

    elif command == 'reset_knowledge':
        if '-archive' in sys.argv:
            print(reset_knowledge(archive=True, dry_run=False))
        elif '-force' in sys.argv:
            print(reset_knowledge(archive=False, dry_run=False))
        else:
            print(reset_knowledge(dry_run=True))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
