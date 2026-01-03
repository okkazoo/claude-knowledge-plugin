#!/usr/bin/env python
"""
Helper functions for autonomous .wip command and refactor cleanup.

This script provides utilities for:
1. Autonomous .wip: Auto-categorizing journeys based on conversation context
2. Refactor cleanup: Reorganizing and merging overlapping journeys
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import re


# ============================================================================
# AUTONOMOUS .WIP HELPERS
# ============================================================================

def scan_category_folders() -> List[str]:
    """
    Scan .claude/knowledge/journey/ for existing parent category folders.

    Returns:
        List of category folder names (e.g., ['auth', 'api', 'frontend'])
    """
    journey_dir = Path('.claude/knowledge/journey')

    if not journey_dir.exists():
        return []

    categories = []
    for item in journey_dir.iterdir():
        # Skip files and special folders (starting with _ or .)
        if item.is_dir() and not item.name.startswith(('_', '.')):
            categories.append(item.name)

    return sorted(categories)


def get_last_updated(journey_path: Path) -> str:
    """
    Read last_updated timestamp from journey's _meta.md.

    Args:
        journey_path: Path to journey folder

    Returns:
        ISO format timestamp string, or empty string if not found
    """
    meta_file = journey_path / '_meta.md'

    if not meta_file.exists():
        return ''

    meta = parse_meta(meta_file)
    return meta.get('last_updated', '')


def sort_by_last_updated(journeys: List[Dict], descending: bool = True) -> List[Dict]:
    """
    Sort journeys by last_updated timestamp.

    Args:
        journeys: List of journey info dicts
        descending: If True, most recent first. If False, oldest first.

    Returns:
        Sorted list of journeys
    """
    return sorted(
        journeys,
        key=lambda d: d.get('last_updated', ''),
        reverse=descending
    )


def are_similar_names(names: List[str], threshold: float = 0.7) -> bool:
    """
    Check if category names are similar (e.g., 'auth' vs 'authentication').

    Args:
        names: List of category names to compare
        threshold: Similarity threshold (0-1)

    Returns:
        True if names are similar enough to be duplicates
    """
    if len(names) < 2:
        return False

    # Simple heuristic: check if one name is a substring or abbreviation of another
    for i, name1 in enumerate(names):
        for name2 in names[i+1:]:
            # Check if one is substring of other
            if name1 in name2 or name2 in name1:
                return True

            # Check if one is abbreviation (first letters match)
            abbrev1 = ''.join([word[0] for word in name1.split('-') if word])
            abbrev2 = ''.join([word[0] for word in name2.split('-') if word])
            if abbrev1 == name2 or abbrev2 == name1:
                return True

    return False


# ============================================================================
# PATTERN EXTRACTION & STORAGE
# ============================================================================

PATTERN_TYPES = ['solution', 'tried-failed', 'gotcha', 'best-practice']


def extract_patterns_from_content(content: str) -> List[Dict]:
    """
    Extract patterns from journey markdown content.

    Looks for the structured patterns section:
    ### ✅ Solutions Found
    - **[Pattern text]** - context: keywords

    ### ❌ Tried But Failed
    - **[Pattern text]** - Failed because: [reason] - context: keywords

    ### ⚠️ Gotchas
    - **[Pattern text]** - context: keywords

    Returns:
        List of pattern dicts with keys: pattern, type, context, confidence
    """
    patterns = []

    # Pattern regex: - **[text]** - [optional reason] - context: keywords
    # Also matches simpler: - **[text]** - context: keywords
    pattern_re = re.compile(
        r'-\s+\*\*(.+?)\*\*\s*-\s*(?:Failed because:\s*(.+?)\s*-\s*)?context:\s*(.+?)$',
        re.MULTILINE
    )

    current_type = None

    for line in content.split('\n'):
        # Detect section type
        if '### ✅' in line or 'Solutions Found' in line:
            current_type = 'solution'
        elif '### ❌' in line or 'Tried But Failed' in line:
            current_type = 'tried-failed'
        elif '### ⚠️' in line or 'Gotchas' in line:
            current_type = 'gotcha'
        elif '### ' in line and 'Best' in line:
            current_type = 'best-practice'
        elif line.startswith('## ') and current_type:
            # New major section, reset type
            if 'Solutions' not in line and 'Pattern' not in line:
                current_type = None

        # Extract pattern from line
        if current_type and line.strip().startswith('- **'):
            match = pattern_re.match(line.strip())
            if match:
                pattern_text = match.group(1).strip()
                reason = match.group(2).strip() if match.group(2) else None
                context = match.group(3).strip()

                # For tried-failed, include reason in pattern
                if current_type == 'tried-failed' and reason:
                    pattern_text = f"{pattern_text} - {reason}"

                patterns.append({
                    'pattern': pattern_text,
                    'type': current_type,
                    'context': context,
                    'confidence': 0.9  # Default confidence for extracted patterns
                })

    return patterns


def save_patterns_to_knowledge(patterns: List[Dict], source_file: str) -> int:
    """
    Save extracted patterns to knowledge.json.

    Args:
        patterns: List of pattern dicts
        source_file: Path to the source journey file

    Returns:
        Number of patterns saved
    """
    knowledge_json_path = Path('.claude/knowledge/knowledge.json')

    # Load existing data
    if knowledge_json_path.exists():
        try:
            data = json.loads(knowledge_json_path.read_text())
        except (json.JSONDecodeError, Exception):
            data = {'version': 1, 'updated': None, 'files': {}, 'patterns': []}
    else:
        data = {'version': 1, 'updated': None, 'files': {}, 'patterns': []}

    # Ensure patterns array exists
    if 'patterns' not in data:
        data['patterns'] = []

    # Normalize source path
    try:
        rel_path = str(Path(source_file).resolve().relative_to(Path('.claude/knowledge').resolve()))
    except ValueError:
        if '.claude/knowledge/' in source_file:
            rel_path = source_file.split('.claude/knowledge/')[-1]
        else:
            rel_path = source_file
    rel_path = rel_path.replace('\\', '/')

    # Remove existing patterns from this source
    data['patterns'] = [p for p in data['patterns'] if p.get('source') != rel_path]

    # Add new patterns
    now = datetime.now().isoformat()
    for p in patterns:
        data['patterns'].append({
            'pattern': p['pattern'],
            'type': p['type'],
            'context': p['context'],
            'confidence': p.get('confidence', 0.9),
            'source': rel_path,
            'added': now
        })

    data['updated'] = now

    # Write back
    knowledge_json_path.write_text(json.dumps(data, indent=2))
    return len(patterns)


def get_patterns(pattern_type: Optional[str] = None, search: Optional[str] = None) -> List[Dict]:
    """
    Get patterns from knowledge.json.

    Args:
        pattern_type: Filter by type (solution, tried-failed, gotcha, best-practice)
        search: Search in pattern text and context

    Returns:
        List of matching patterns
    """
    knowledge_json_path = Path('.claude/knowledge/knowledge.json')

    if not knowledge_json_path.exists():
        return []

    try:
        data = json.loads(knowledge_json_path.read_text())
    except (json.JSONDecodeError, Exception):
        return []

    patterns = data.get('patterns', [])

    # Filter by type
    if pattern_type:
        patterns = [p for p in patterns if p.get('type') == pattern_type]

    # Filter by search
    if search:
        search_lower = search.lower()
        patterns = [
            p for p in patterns
            if search_lower in p.get('pattern', '').lower()
            or search_lower in p.get('context', '').lower()
        ]

    return patterns


def search_patterns(query: str, limit: int = 10) -> List[Dict]:
    """
    Search patterns by query, returning most relevant matches.

    Args:
        query: Search query
        limit: Maximum results

    Returns:
        List of matching patterns with relevance scores
    """
    patterns = get_patterns()
    query_words = set(query.lower().split())

    scored = []
    for p in patterns:
        # Score based on word overlap
        pattern_words = set(p.get('pattern', '').lower().split())
        context_words = set(p.get('context', '').lower().replace(',', ' ').split())
        all_words = pattern_words | context_words

        overlap = len(query_words & all_words)
        if overlap > 0:
            # Weight: pattern match > context match
            pattern_overlap = len(query_words & pattern_words)
            context_overlap = len(query_words & context_words)
            score = (pattern_overlap * 2) + context_overlap
            scored.append((score, p))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    return [p for _, p in scored[:limit]]


def format_patterns_for_display(patterns: List[Dict]) -> str:
    """
    Format patterns for CLI display.

    Args:
        patterns: List of pattern dicts

    Returns:
        Formatted string for display
    """
    if not patterns:
        return "No patterns found."

    # Group by type
    by_type = {}
    for p in patterns:
        ptype = p.get('type', 'other')
        if ptype not in by_type:
            by_type[ptype] = []
        by_type[ptype].append(p)

    # Format output
    lines = []

    type_icons = {
        'solution': '✅',
        'tried-failed': '❌',
        'gotcha': '⚠️',
        'best-practice': '💡'
    }

    type_order = ['solution', 'tried-failed', 'gotcha', 'best-practice']

    for ptype in type_order:
        if ptype in by_type:
            icon = type_icons.get(ptype, '•')
            lines.append(f"\n{icon} {ptype.replace('-', ' ').title()}:")
            for p in by_type[ptype]:
                source = p.get('source', '')
                if source:
                    source = f" ({Path(source).stem})"
                lines.append(f"  - {p['pattern']}{source}")

    return '\n'.join(lines)


# ============================================================================
# FACT CAPTURE HELPERS
# ============================================================================

def ensure_facts_folder() -> Path:
    """
    Ensure the knowledge/facts/ folder exists.

    Returns:
        Path to facts folder
    """
    facts_dir = Path('.claude/knowledge/facts')
    facts_dir.mkdir(parents=True, exist_ok=True)
    return facts_dir


def save_fact(fact_text: str, slug: Optional[str] = None) -> Path:
    """
    Save a fact/gotcha to knowledge/facts/ folder.

    Args:
        fact_text: The fact/gotcha text to save
        slug: Optional slug for filename (auto-generated if not provided)

    Returns:
        Path to created fact file
    """
    facts_dir = ensure_facts_folder()

    # Generate timestamp
    timestamp = datetime.now()
    date_prefix = timestamp.strftime('%Y-%m-%d')

    # Generate slug from fact text if not provided
    if not slug:
        # Extract first few words for slug
        words = re.sub(r'[^a-zA-Z0-9\s]', '', fact_text.lower()).split()[:5]
        slug = '-'.join(words) if words else 'fact'
        slug = slug[:50]  # Limit length

    # Create filename
    filename = f"{date_prefix}-{slug}.md"
    file_path = facts_dir / filename

    # Handle duplicate filenames
    counter = 1
    while file_path.exists():
        filename = f"{date_prefix}-{slug}-{counter}.md"
        file_path = facts_dir / filename
        counter += 1

    # Create fact file content
    content = f"""# Fact: {fact_text[:60]}{'...' if len(fact_text) > 60 else ''}

## Date: {timestamp.strftime('%Y-%m-%d %H:%M')}

{fact_text}
"""

    file_path.write_text(content, encoding='utf-8')

    # Index the fact for pre-search discovery
    index_fact(file_path)

    return file_path


def index_fact(fact_file: Path) -> int:
    """
    Index a fact file into knowledge.json for pre-search discovery.

    Args:
        fact_file: Path to the fact file

    Returns:
        Number of keywords indexed
    """
    knowledge_json_path = Path('.claude/knowledge/knowledge.json')

    # Load existing data
    if knowledge_json_path.exists():
        try:
            data = json.loads(knowledge_json_path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, Exception):
            data = {'version': 1, 'updated': None, 'files': {}, 'patterns': []}
    else:
        data = {'version': 1, 'updated': None, 'files': {}, 'patterns': []}

    # Get relative path from knowledge base
    knowledge_base = Path('.claude/knowledge')
    try:
        rel_path = str(fact_file.resolve().relative_to(knowledge_base.resolve()))
    except ValueError:
        rel_path = f"facts/{fact_file.name}"
    rel_path = rel_path.replace('\\', '/')

    # Read fact content and extract keywords
    try:
        content = fact_file.read_text(encoding='utf-8')
    except Exception:
        return 0

    # Extract title
    title = fact_file.stem
    for line in content.split('\n'):
        if line.startswith('# Fact:'):
            title = line.replace('# Fact:', '').strip()
            break

    # Extract keywords from fact text
    # Get text after "## Date:" line
    fact_text = ''
    capture = False
    for line in content.split('\n'):
        if line.startswith('## Date:'):
            capture = True
            continue
        if capture:
            fact_text += line + ' '

    # Simple keyword extraction
    stopwords = {'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been',
                 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
                 'could', 'should', 'may', 'might', 'must', 'to', 'of', 'in',
                 'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'and',
                 'or', 'but', 'if', 'then', 'because', 'so', 'this', 'that',
                 'it', 'its', 'you', 'your', 'use', 'using', 'used'}

    words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b', fact_text.lower())
    keywords = [w for w in words if w not in stopwords]

    # Deduplicate while preserving order, limit to 15
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)
            if len(unique_keywords) >= 15:
                break

    # Update entry
    now = datetime.now().isoformat()
    data['files'][rel_path] = {
        'modified': now,
        'title': f"Fact: {title[:60]}",
        'keywords': unique_keywords
    }
    data['updated'] = now

    # Write back
    knowledge_json_path.write_text(json.dumps(data, indent=2), encoding='utf-8')

    return len(unique_keywords)


def create_backup() -> Path:
    """
    Create timestamped backup of journey directory.

    Returns:
        Path to backup directory
    """
    timestamp = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    backup_dir = Path(f'.claude/knowledge/savepoints/refactor-backup-{timestamp}')
    journey_dir = Path('.claude/knowledge/journey')

    # Create backup
    if journey_dir.exists():
        shutil.copytree(journey_dir, backup_dir, dirs_exist_ok=True)

    # Create backup manifest
    manifest = {
        'timestamp': timestamp,
        'type': 'journey-refactor-backup',
        'original_path': str(journey_dir),
        'restore_command': f'cp -r {backup_dir}/* {journey_dir}/'
    }

    manifest_file = backup_dir / 'BACKUP_INFO.json'
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding='utf-8')

    return backup_dir


def merge_journeys(main_topic: str, merge_topics: List[str], target_dir: Path):
    """
    Merge multiple journeys into one, handling filename conflicts.

    Args:
        main_topic: The primary topic (canonical name)
        merge_topics: List of topics to merge into main
        target_dir: Target directory for merged journey
    """
    target_dir.mkdir(parents=True, exist_ok=True)

    all_keywords = set()
    earliest_created = None
    latest_updated = None
    all_entry_files = []

    # Collect from all topics
    for topic in [main_topic] + merge_topics:
        item_dir = find_journey_dir(topic)

        if not item_dir or not item_dir.exists():
            continue

        meta_file = item_dir / '_meta.md'
        if meta_file.exists():
            meta = parse_meta(meta_file)

            # Collect metadata
            all_keywords.update(meta.get('keywords', []))

            created = meta.get('created', '')
            if created and (not earliest_created or created < earliest_created):
                earliest_created = created

            updated = meta.get('last_updated', '')
            if updated and (not latest_updated or updated > latest_updated):
                latest_updated = updated

        # Copy entry files with conflict handling
        for entry_file in item_dir.glob('*.md'):
            if entry_file.name == '_meta.md':
                continue

            target_file = target_dir / entry_file.name

            # Handle filename conflicts
            if target_file.exists():
                # Prefix with original topic name
                name_parts = entry_file.stem.split('-', 4)  # Split timestamp parts
                if len(name_parts) >= 4:
                    # Insert topic name before description
                    new_name = f"{'-'.join(name_parts[:3])}-{topic}-{name_parts[3]}{entry_file.suffix}"
                else:
                    new_name = f"{topic}-{entry_file.name}"

                target_file = target_dir / new_name

            shutil.copy2(entry_file, target_file)
            all_entry_files.append(target_file.name)

    # Create merged _meta.md
    merged_meta = {
        'topic': main_topic,
        'created': earliest_created or datetime.now().isoformat(),
        'last_updated': latest_updated or datetime.now().isoformat(),
        'status': 'active',
        'completed_date': None,
        'keywords': sorted(list(all_keywords)),
        'merged_from': merge_topics,
        'merge_date': datetime.now().isoformat()
    }

    write_meta(target_dir / '_meta.md', merged_meta)


def move_journey(source_path: Path, target_path: Path):
    """
    Move a journey to a new location.

    Args:
        source_path: Current journey directory
        target_path: New journey directory location
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source_path), str(target_path))


def rollback_from_backup(backup_path: Path):
    """
    Restore journeys from backup.

    Args:
        backup_path: Path to backup directory
    """
    journey_dir = Path('.claude/knowledge/journey')

    # Remove current (broken) state
    if journey_dir.exists():
        shutil.rmtree(journey_dir)

    # Restore from backup
    shutil.copytree(backup_path, journey_dir)


# ============================================================================
# KNOWLEDGE STATUS HELPERS
# ============================================================================

def get_knowledge_status() -> str:
    """
    Get formatted knowledge base status with full tree view.

    Returns:
        Formatted status string for display
    """
    from pathlib import Path
    import subprocess

    # ANSI color codes
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    RESET = '\033[0m'

    # Gather git info
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
            status = subprocess.run(['git', 'status', '--short'],
                                   capture_output=True, text=True, timeout=5).stdout.strip()
            git_status = status if status else 'Clean'
            git_info = branch or 'unknown'
        except:
            git_info = 'unknown'
            git_status = 'unknown'
    else:
        git_info = 'not a git repo'
        git_status = 'Not a git repository'

    # Count journeys (excluding memory folder)
    journey_dir = Path('.claude/knowledge/journey')
    journey_count = 0
    journeys_detail = []

    if journey_dir.exists():
        for category in journey_dir.iterdir():
            if category.is_dir() and category.name not in ('memory', '_', '.') and not category.name.startswith(('_', '.')):
                category_journeys = []
                for journey in category.iterdir():
                    if journey.is_dir() and not journey.name.startswith(('_', '.')):
                        meta_file = journey / '_meta.md'
                        entry_count = len([f for f in journey.glob('*.md') if f.name != '_meta.md'])

                        meta = parse_meta(meta_file) if meta_file.exists() else {}
                        last_updated = meta.get('last_updated', 'unknown')
                        keywords = meta.get('keywords', [])
                        if isinstance(keywords, str):
                            keywords = [k.strip() for k in keywords.split(',')]

                        journey_count += 1
                        category_journeys.append({
                            'name': journey.name,
                            'entries': entry_count,
                            'updated': _format_relative_time(last_updated),
                            'keywords': keywords[:3]  # Limit to 3 keywords
                        })

                if category_journeys:
                    # Sort by updated (most recent first based on name which contains timestamp)
                    category_journeys.sort(key=lambda x: x['name'], reverse=True)
                    journeys_detail.append({
                        'category': category.name,
                        'journeys': category_journeys
                    })

    # Count facts
    facts_dir = Path('.claude/knowledge/facts')
    facts_count = 0
    facts_detail = []

    if facts_dir.exists():
        fact_files = sorted([f for f in facts_dir.glob('*.md') if not f.name.startswith('.')], reverse=True)
        facts_count = len(fact_files)

        for fact_file in fact_files[:5]:  # Last 5 facts
            try:
                content = fact_file.read_text(encoding='utf-8')
                title = ''
                for line in content.split('\n'):
                    if line.startswith('# Fact:'):
                        title = line.replace('# Fact:', '').strip()[:50]
                        break

                # Extract date from filename
                date_match = fact_file.stem[:10] if len(fact_file.stem) >= 10 else 'unknown'

                facts_detail.append({
                    'date': date_match,
                    'title': title or fact_file.stem
                })
            except:
                pass

    # Count savepoints
    savepoints_dir = Path('.claude/knowledge/savepoints')
    savepoint_count = 0
    savepoints_detail = []

    if savepoints_dir.exists():
        savepoint_dirs = sorted([d for d in savepoints_dir.iterdir() if d.is_dir()], reverse=True)
        savepoint_count = len(savepoint_dirs)
        savepoints_detail = [d.name for d in savepoint_dirs[:5]]

    # Build output
    lines = []
    dotted_line = '·' * 34

    lines.append("Knowledge Base Status")
    lines.append("")
    lines.append(f"Branch: {git_info}")
    lines.append("")

    # Stats
    lines.append("STATS")
    lines.append(dotted_line)
    lines.append(f"{GREEN}Journeys: {journey_count}{RESET}  |  {BLUE}Facts: {facts_count}{RESET}  |  Savepoints: {savepoint_count}")
    lines.append("")
    lines.append("")

    # Facts - BLUE header with count, dotted line below
    lines.append(f"{BLUE}FACTS [{facts_count}]{RESET}")
    lines.append(f"{BLUE}{dotted_line}{RESET}")
    if facts_detail:
        facts_dir_path = Path('.claude/knowledge/facts')
        if facts_dir_path.exists():
            all_facts = sorted([f.name for f in facts_dir_path.glob('*.md') if not f.name.startswith('.')], reverse=True)
            for fact_name in all_facts:
                lines.append(fact_name)
    else:
        lines.append("No facts yet.")
    lines.append("")
    lines.append("")

    # Journeys - GREEN header with count, dotted line below, tree structure
    lines.append(f"{GREEN}JOURNEYS [{journey_count}]{RESET}")
    lines.append(f"{GREEN}{dotted_line}{RESET}")
    if journeys_detail:
        for cat_idx, cat in enumerate(journeys_detail):
            # Category header
            lines.append(f"{cat['category']}/")

            # Get all entry files for this category's journeys
            journey_entries = []
            for j in cat['journeys']:
                journey_path = Path(f".claude/knowledge/journey/{cat['category']}/{j['name']}")
                if journey_path.exists():
                    entry_files = sorted([f.name for f in journey_path.glob('*.md') if f.name != '_meta.md'])
                    journey_entries.extend(entry_files)

            # Display entries with tree structure
            for e_idx, entry_name in enumerate(journey_entries):
                is_last = (e_idx == len(journey_entries) - 1)
                prefix = "└── " if is_last else "├── "
                lines.append(f"{prefix}{entry_name}")

            # Blank line between categories (except last)
            if cat_idx < len(journeys_detail) - 1:
                lines.append("")
    else:
        lines.append("No journeys yet.")
    lines.append("")
    lines.append("")

    # Patterns section (from knowledge.json)
    lines.append("PATTERNS")
    lines.append(dotted_line)
    knowledge_json_path = Path('.claude/knowledge/knowledge.json')
    if knowledge_json_path.exists():
        try:
            kdata = json.loads(knowledge_json_path.read_text(encoding='utf-8'))
            patterns = kdata.get('patterns', [])
            if patterns:
                # Group by source and collect keywords
                by_source = {}
                for p in patterns:
                    source = p.get('source', 'unknown')
                    # Extract journey name from source path
                    parts = source.replace('\\', '/').split('/')
                    if len(parts) >= 2:
                        source_name = parts[1] + '/'  # e.g., "template-setup/"
                    else:
                        source_name = parts[0] + '/' if parts else 'unknown/'

                    if source_name not in by_source:
                        by_source[source_name] = {'count': 0, 'keywords': []}
                    by_source[source_name]['count'] += 1
                    # Collect keywords from context
                    context = p.get('context', '')
                    if context:
                        by_source[source_name]['keywords'].extend(
                            [k.strip() for k in context.split(',')]
                        )

                # Format each source with top keywords
                for source_name, info in sorted(by_source.items()):
                    # Get top 3 most common keywords
                    from collections import Counter
                    keyword_counts = Counter(info['keywords'])
                    top_keywords = [kw for kw, _ in keyword_counts.most_common(3)]
                    keywords_str = ', '.join(top_keywords) if top_keywords else 'misc'
                    lines.append(f"{source_name} - {info['count']} patterns - [{keywords_str}]")
            else:
                lines.append("No patterns indexed yet.")
        except Exception:
            lines.append("No patterns indexed yet.")
    else:
        lines.append("No patterns indexed yet.")
    lines.append("")
    lines.append("")

    # Git Status (no icons)
    lines.append("GIT STATUS")
    lines.append(dotted_line)
    if git_status == 'Clean':
        lines.append("Working tree clean")
    elif git_status == 'Not a git repository':
        lines.append("Not a git repository")
    else:
        for line in git_status.split('\n')[:5]:
            lines.append(line)
    lines.append("")
    lines.append("")

    # Savepoints (no icons)
    if savepoint_count > 0:
        lines.append("SAVEPOINTS")
        lines.append(dotted_line)
        for c in savepoints_detail:
            lines.append(c)
        if savepoint_count > 5:
            lines.append(f"... and {savepoint_count - 5} more")
        lines.append("")
        lines.append("")

    return '\n'.join(lines)


def reset_knowledge(archive: bool = False, dry_run: bool = True) -> str:
    """
    Reset knowledge base to factory defaults.

    Args:
        archive: If True, archive current knowledge before reset
        dry_run: If True, only show what would be affected (default)

    Returns:
        Formatted status string for display
    """
    from pathlib import Path
    import shutil

    knowledge_dir = Path('.claude/knowledge')
    lines = []

    # Collect what will be affected
    affected = {
        'journeys': [],
        'facts': [],
        'savepoints': [],
    }

    # Count journeys
    journey_dir = knowledge_dir / 'journey'
    if journey_dir.exists():
        for category in journey_dir.iterdir():
            if category.is_dir() and not category.name.startswith(('_', '.')):
                for journey in category.iterdir():
                    if journey.is_dir() and not journey.name.startswith(('_', '.')):
                        entry_count = len([f for f in journey.glob('*.md') if f.name != '_meta.md'])
                        affected['journeys'].append({
                            'path': str(journey.relative_to(knowledge_dir)),
                            'entries': entry_count
                        })

    # Count facts
    facts_dir = knowledge_dir / 'facts'
    if facts_dir.exists():
        for fact in facts_dir.glob('*.md'):
            if not fact.name.startswith('.'):
                affected['facts'].append(fact.name)

    # Count savepoints
    savepoints_dir = knowledge_dir / 'savepoints'
    if savepoints_dir.exists():
        for cp in savepoints_dir.iterdir():
            if cp.is_dir() and not cp.name.startswith('.'):
                affected['savepoints'].append(cp.name)

    # Calculate totals
    total_journeys = len(affected['journeys'])
    total_facts = len(affected['facts'])
    total_savepoints = len(affected['savepoints'])
    total_items = total_journeys + total_facts + total_savepoints

    if dry_run:
        # Show what will be affected
        lines.append("# Knowledge Base Reset")
        lines.append("")
        lines.append("─" * 50)
        lines.append("")
        lines.append("## ⚠️  Items to be Reset")
        lines.append("")

        if total_items == 0:
            lines.append("  _Knowledge base is already empty._")
            lines.append("")
            lines.append("─" * 50)
            lines.append("")
            lines.append("Nothing to reset.")
            return '\n'.join(lines)

        # Journeys
        lines.append(f"### 📁 Journeys ({total_journeys})")
        if affected['journeys']:
            for j in affected['journeys'][:5]:
                lines.append(f"  • {j['path']} ({j['entries']} entries)")
            if total_journeys > 5:
                lines.append(f"  _... and {total_journeys - 5} more_")
        else:
            lines.append("  _None_")
        lines.append("")

        # Facts
        lines.append(f"### 💡 Facts ({total_facts})")
        if affected['facts']:
            for f in affected['facts'][:5]:
                lines.append(f"  • {f}")
            if total_facts > 5:
                lines.append(f"  _... and {total_facts - 5} more_")
        else:
            lines.append("  _None_")
        lines.append("")

        # Savepoints
        lines.append(f"### 📍 Savepoints ({total_savepoints})")
        if affected['savepoints']:
            for c in affected['savepoints'][:5]:
                lines.append(f"  • {c}")
            if total_savepoints > 5:
                lines.append(f"  _... and {total_savepoints - 5} more_")
        else:
            lines.append("  _None_")
        lines.append("")

        lines.append("─" * 50)
        lines.append("")
        lines.append(f"**Total items:** {total_items}")
        lines.append("")
        lines.append("─" * 50)
        lines.append("")
        lines.append("## Choose Reset Option")
        lines.append("")
        lines.append("  **[1] Archive & Reset**")
        lines.append("      Save current knowledge to timestamped archive,")
        lines.append("      then reset to factory defaults.")
        lines.append("")
        lines.append("  **[2] Full Reset**")
        lines.append("      Delete all knowledge permanently.")
        lines.append("      ⚠️  This cannot be undone!")
        lines.append("")
        lines.append("  **[3] Cancel**")
        lines.append("      Abort reset, keep everything.")
        lines.append("")

        return '\n'.join(lines)

    else:
        # Actually perform the reset
        timestamp = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')

        if archive and total_items > 0:
            # Create archive
            archive_dir = Path(f'.claude/knowledge-archive-{timestamp}')
            archive_dir.mkdir(parents=True, exist_ok=True)

            # Copy knowledge contents to archive
            if knowledge_dir.exists():
                for item in knowledge_dir.iterdir():
                    if item.is_dir():
                        shutil.copytree(item, archive_dir / item.name, dirs_exist_ok=True)
                    elif item.is_file() and not item.name.startswith('.'):
                        shutil.copy2(item, archive_dir / item.name)

            lines.append(f"✓ Archived to: .claude/knowledge-archive-{timestamp}/")

        # Reset journey folders (keep structure, remove content)
        def safe_rmtree(path):
            """Safely remove directory tree, handling Windows permission issues."""
            import stat
            import time

            def handle_remove_readonly(func, path, exc):
                """Handle read-only files on Windows."""
                os.chmod(path, stat.S_IWRITE)
                func(path)

            try:
                shutil.rmtree(path, onerror=handle_remove_readonly)
            except Exception as e:
                # Fallback: try removing files one by one
                try:
                    for root, dirs, files in os.walk(path, topdown=False):
                        for name in files:
                            file_path = os.path.join(root, name)
                            try:
                                os.chmod(file_path, stat.S_IWRITE)
                                os.remove(file_path)
                            except:
                                pass
                        for name in dirs:
                            dir_path = os.path.join(root, name)
                            try:
                                os.rmdir(dir_path)
                            except:
                                pass
                    os.rmdir(path)
                except:
                    pass

        if journey_dir.exists():
            for category in list(journey_dir.iterdir()):
                if category.is_dir() and not category.name.startswith(('_', '.')):
                    safe_rmtree(category)

        # Clear facts folder contents (keep folder)
        if facts_dir.exists():
            for f in facts_dir.glob('*.md'):
                if not f.name.startswith('.'):
                    try:
                        f.unlink()
                    except:
                        pass

        # Reset savepoints (keep .gitkeep)
        if savepoints_dir.exists():
            for item in savepoints_dir.iterdir():
                if item.is_dir():
                    safe_rmtree(item)

        # Reset coderef.json
        coderef_file = knowledge_dir / 'coderef.json'
        coderef_content = {
            "version": 1,
            "updated": datetime.now().isoformat(),
            "files": {}
        }
        coderef_file.write_text(json.dumps(coderef_content, indent=2), encoding='utf-8')

        # Reset knowledge.json
        knowledge_json = knowledge_dir / 'knowledge.json'
        knowledge_content = {
            "version": 1,
            "updated": None,
            "files": {}
        }
        knowledge_json.write_text(json.dumps(knowledge_content, indent=2), encoding='utf-8')

        lines.append("✓ Reset coderef.json")
        lines.append("✓ Reset knowledge.json")
        lines.append("✓ Cleared journeys")
        lines.append("✓ Cleared facts")
        lines.append("✓ Cleared savepoints")
        lines.append("")
        lines.append("─" * 50)
        lines.append("")
        lines.append("✅ **Knowledge base reset to factory defaults.**")

        return '\n'.join(lines)


def _format_relative_time(timestamp: str) -> str:
    """Format timestamp as relative time (e.g., '2 days ago')."""
    if not timestamp or timestamp == 'unknown':
        return 'unknown'

    try:
        # Parse ISO format
        if 'T' in timestamp:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        else:
            dt = datetime.fromisoformat(timestamp)

        now = datetime.now()
        if dt.tzinfo:
            now = datetime.now(dt.tzinfo)

        diff = now - dt

        if diff.days == 0:
            hours = diff.seconds // 3600
            if hours == 0:
                return 'just now'
            elif hours == 1:
                return '1 hour ago'
            else:
                return f'{hours} hours ago'
        elif diff.days == 1:
            return 'yesterday'
        elif diff.days < 7:
            return f'{diff.days} days ago'
        elif diff.days < 30:
            weeks = diff.days // 7
            return f'{weeks} week{"s" if weeks > 1 else ""} ago'
        else:
            months = diff.days // 30
            return f'{months} month{"s" if months > 1 else ""} ago'
    except:
        return timestamp[:10] if len(timestamp) >= 10 else timestamp


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def parse_meta(meta_file: Path) -> Dict:
    """
    Parse YAML frontmatter from _meta.md file.

    Args:
        meta_file: Path to _meta.md file

    Returns:
        Dict of metadata
    """
    if not meta_file.exists():
        return {}

    content = meta_file.read_text(encoding='utf-8')

    # Extract YAML frontmatter
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 2:
            yaml_content = parts[1].strip()

            # Simple YAML parser (handles basic key: value pairs)
            meta = {}
            for line in yaml_content.split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()

                    # Handle arrays [item1, item2]
                    if value.startswith('[') and value.endswith(']'):
                        value = [v.strip() for v in value[1:-1].split(',')]
                    # Handle null
                    elif value.lower() in ('null', 'none', '~'):
                        value = None

                    meta[key] = value

            return meta

    return {}


def write_meta(meta_file: Path, meta: Dict):
    """
    Write metadata to _meta.md file.

    Args:
        meta_file: Path to _meta.md file
        meta: Metadata dict
    """
    lines = ['---']

    for key, value in meta.items():
        if isinstance(value, list):
            value_str = '[' + ', '.join(str(v) for v in value) + ']'
        elif value is None:
            value_str = 'null'
        else:
            value_str = str(value)

        lines.append(f'{key}: {value_str}')

    lines.append('---')
    lines.append(f'\n# {meta.get("topic", "Journey")}\n')
    lines.append(f'\nWork in progress.\n')

    meta_file.write_text('\n'.join(lines), encoding='utf-8')


def find_journey_dir(topic: str) -> Optional[Path]:
    """
    Find journey directory by topic name, searching all categories.

    Args:
        topic: Topic name to search for

    Returns:
        Path to journey directory, or None if not found
    """
    journey_dir = Path('.claude/knowledge/journey')

    if not journey_dir.exists():
        return None

    # Search in root level
    candidate = journey_dir / topic
    if candidate.exists() and candidate.is_dir():
        return candidate

    # Search in category subdirectories
    for category_dir in journey_dir.iterdir():
        if not category_dir.is_dir() or category_dir.name.startswith(('_', '.')):
            continue

        candidate = category_dir / topic
        if candidate.exists() and candidate.is_dir():
            return candidate

    return None


def create_entry(category: str, topic: str, content: str, slug: Optional[str] = None) -> Dict:
    """
    Create a journey entry file with auto-generated timestamp filename.

    Args:
        category: Parent category (e.g., 'infrastructure', 'dashboard')
        topic: Journey topic name (e.g., 'knowledge-search-system')
        content: Full markdown content for the entry
        slug: Optional slug for filename (auto-generated from content title if not provided)

    Returns:
        Dict with keys: success, file, category, topic, patterns_indexed
    """
    journey_dir = Path('.claude/knowledge/journey')
    topic_dir = journey_dir / category / topic

    # Create directory if needed
    topic_dir.mkdir(parents=True, exist_ok=True)

    # Generate timestamp
    now = datetime.now()
    timestamp_prefix = now.strftime('%Y-%m-%d-%H-%M')

    # Generate slug from content if not provided
    if not slug:
        # Try to extract from first heading
        for line in content.split('\n'):
            if line.startswith('# '):
                title = line[2:].strip()
                # Remove "WIP:" prefix if present
                if title.lower().startswith('wip:'):
                    title = title[4:].strip()
                # Convert to slug
                words = re.sub(r'[^a-zA-Z0-9\s]', '', title.lower()).split()[:4]
                slug = '-'.join(words) if words else 'entry'
                break
        if not slug:
            slug = 'entry'

    slug = slug[:40]  # Limit length

    # Create filename
    filename = f"{timestamp_prefix}-{slug}.md"
    file_path = topic_dir / filename

    # Handle duplicate filenames
    counter = 1
    while file_path.exists():
        filename = f"{timestamp_prefix}-{slug}-{counter}.md"
        file_path = topic_dir / filename
        counter += 1

    # Write entry file
    file_path.write_text(content, encoding='utf-8')

    # Extract keywords from content for meta
    # Look for context: lines in patterns section
    entry_keywords = set()
    for line in content.split('\n'):
        if 'context:' in line.lower():
            # Extract keywords after "context:"
            match = re.search(r'context:\s*(.+?)(?:\s*$|\s*-)', line, re.IGNORECASE)
            if match:
                kws = [k.strip() for k in match.group(1).split(',')]
                entry_keywords.update(kws)

    # Add topic words as keywords
    topic_words = topic.replace('-', ' ').split()
    entry_keywords.update(topic_words)

    # Create/update meta
    keywords_str = ', '.join(sorted(entry_keywords)[:15])  # Limit to 15 keywords
    create_or_update_meta(category, topic, keywords_str)

    # Extract and index patterns
    patterns = extract_patterns_from_content(content)
    patterns_count = 0
    if patterns:
        patterns_count = save_patterns_to_knowledge(patterns, str(file_path))

    return {
        'success': True,
        'file': str(file_path),
        'category': category,
        'topic': topic,
        'patterns_indexed': patterns_count
    }


def create_or_update_meta(category: str, topic: str, keywords: str, description: str = None) -> Path:
    """
    Create or update _meta.md for a journey.

    Args:
        category: Parent category (e.g., 'infrastructure')
        topic: Journey topic name (e.g., 'knowledge-search-system')
        keywords: Comma-separated keywords
        description: Optional description of the journey

    Returns:
        Path to the _meta.md file
    """
    journey_dir = Path('.claude/knowledge/journey')
    topic_dir = journey_dir / category / topic

    # Create directory if needed
    topic_dir.mkdir(parents=True, exist_ok=True)

    meta_file = topic_dir / '_meta.md'
    now = datetime.now()
    timestamp = now.strftime('%Y-%m-%d %H:%M')

    # Parse keywords
    keyword_list = [k.strip() for k in keywords.split(',') if k.strip()]

    if meta_file.exists():
        # Update existing meta
        existing_meta = parse_meta(meta_file)
        existing_meta['last_updated'] = timestamp

        # Merge keywords
        existing_keywords = existing_meta.get('keywords', [])
        if isinstance(existing_keywords, str):
            existing_keywords = [k.strip() for k in existing_keywords.split(',')]
        all_keywords = list(set(existing_keywords + keyword_list))
        existing_meta['keywords'] = all_keywords

        write_meta(meta_file, existing_meta)
    else:
        # Create new meta
        meta = {
            'topic': topic,
            'status': 'active',
            'created': timestamp,
            'last_updated': timestamp,
            'keywords': keyword_list
        }

        # Write as markdown format (not YAML frontmatter for consistency)
        content = f"""# Journey: {topic.replace('-', ' ').title()}

## Status: active

## Created: {timestamp}

## Last Updated: {timestamp}

## Keywords
{', '.join(keyword_list)}

## Description
{description or f"Work in progress on {topic.replace('-', ' ')}"}
"""
        meta_file.write_text(content, encoding='utf-8')

    return meta_file


def normalize_topic_name(topic: str) -> str:
    """
    Normalize topic name to kebab-case.

    Args:
        topic: Raw topic name

    Returns:
        Normalized kebab-case name
    """
    # Convert to lowercase
    normalized = topic.lower()

    # Replace spaces and underscores with hyphens
    normalized = re.sub(r'[\s_]+', '-', normalized)

    # Remove special characters except hyphens
    normalized = re.sub(r'[^a-z0-9-]+', '', normalized)

    # Remove multiple consecutive hyphens
    normalized = re.sub(r'-+', '-', normalized)

    # Remove leading/trailing hyphens
    normalized = normalized.strip('-')

    return normalized


# ============================================================================
# KNOWLEDGE AUDIT HELPERS
# ============================================================================

def _extract_keywords(text: str) -> set:
    """Extract meaningful keywords from text for similarity comparison."""
    # Remove common words
    stopwords = {'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been',
                 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                 'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                 'can', 'need', 'to', 'of', 'in', 'for', 'on', 'with', 'at',
                 'by', 'from', 'as', 'into', 'through', 'during', 'before',
                 'after', 'above', 'below', 'between', 'under', 'again',
                 'further', 'then', 'once', 'here', 'there', 'when', 'where',
                 'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more',
                 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
                 'own', 'same', 'so', 'than', 'too', 'very', 'just', 'and',
                 'but', 'if', 'or', 'because', 'until', 'while', 'this', 'that',
                 'these', 'those', 'it', 'its', 'they', 'them', 'their', 'what',
                 'which', 'who', 'whom', 'use', 'using', 'used'}

    # Extract words
    words = re.findall(r'[a-zA-Z0-9]+', text.lower())
    # Filter stopwords and short words
    return {w for w in words if w not in stopwords and len(w) > 2}


def _calculate_similarity(text1: str, text2: str) -> float:
    """Calculate Jaccard similarity between two texts."""
    words1 = _extract_keywords(text1)
    words2 = _extract_keywords(text2)

    if not words1 or not words2:
        return 0.0

    intersection = len(words1 & words2)
    union = len(words1 | words2)

    return intersection / union if union > 0 else 0.0


def find_similar_facts(new_text: str, threshold: float = 0.5) -> List[Dict]:
    """
    Find existing facts similar to new text (for dupe-check in .wip).

    Args:
        new_text: The new fact text to compare
        threshold: Similarity threshold (0-1), default 0.5

    Returns:
        List of similar facts with similarity scores
    """
    facts_dir = Path('.claude/knowledge/facts')
    similar = []

    if not facts_dir.exists():
        return []

    for fact_file in facts_dir.glob('*.md'):
        if fact_file.name.startswith('.'):
            continue

        try:
            content = fact_file.read_text(encoding='utf-8')
            # Extract the actual fact text (after the date line)
            lines = content.split('\n')
            fact_text = ''
            capture = False
            for line in lines:
                if line.startswith('## Date:'):
                    capture = True
                    continue
                if capture:
                    fact_text += line + ' '

            fact_text = fact_text.strip()
            if not fact_text:
                continue

            similarity = _calculate_similarity(new_text, fact_text)

            if similarity >= threshold:
                similar.append({
                    'file': fact_file.name,
                    'path': str(fact_file),
                    'text': fact_text[:100] + ('...' if len(fact_text) > 100 else ''),
                    'similarity': round(similarity, 2)
                })

        except Exception:
            pass

    # Sort by similarity descending
    similar.sort(key=lambda x: x['similarity'], reverse=True)
    return similar


def audit_knowledge() -> str:
    """
    Full knowledge base audit.

    Checks:
    1. Redundant/overlapping facts
    2. Journey consolidation opportunities
    3. Cross-reference validation (coderef.json, knowledge.json)

    Returns:
        Formatted audit report
    """
    lines = []
    issues_found = 0
    dotted_line = '─' * 50

    lines.append("# Knowledge Base Audit")
    lines.append("")
    lines.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append("")
    lines.append(dotted_line)

    # =========================================================================
    # 1. FACT REDUNDANCY CHECK
    # =========================================================================
    lines.append("")
    lines.append("## 1. Fact Redundancy Check")
    lines.append("")

    facts_dir = Path('.claude/knowledge/facts')
    fact_groups = []  # Groups of similar facts

    if facts_dir.exists():
        fact_files = sorted([f for f in facts_dir.glob('*.md') if not f.name.startswith('.')])

        # Compare each fact to others
        fact_contents = []
        for f in fact_files:
            try:
                content = f.read_text(encoding='utf-8')
                # Extract fact text
                fact_text = ''
                capture = False
                for line in content.split('\n'):
                    if line.startswith('## Date:'):
                        capture = True
                        continue
                    if capture:
                        fact_text += line + ' '
                fact_contents.append({
                    'file': f.name,
                    'text': fact_text.strip(),
                    'path': str(f)
                })
            except:
                pass

        # Find groups of similar facts
        used = set()
        for i, fact1 in enumerate(fact_contents):
            if i in used:
                continue

            group = [fact1]
            for j, fact2 in enumerate(fact_contents[i+1:], i+1):
                if j in used:
                    continue

                sim = _calculate_similarity(fact1['text'], fact2['text'])
                if sim >= 0.4:  # 40% similarity threshold
                    group.append(fact2)
                    used.add(j)

            if len(group) > 1:
                used.add(i)
                fact_groups.append(group)

        if fact_groups:
            lines.append(f"**Found {len(fact_groups)} groups of potentially redundant facts:**")
            lines.append("")

            for idx, group in enumerate(fact_groups, 1):
                issues_found += 1
                lines.append(f"### Group {idx} ({len(group)} facts)")
                for fact in group:
                    lines.append(f"  - `{fact['file']}`")
                    lines.append(f"    _{fact['text'][:80]}{'...' if len(fact['text']) > 80 else ''}_")
                lines.append("")
                lines.append(f"  **Suggestion:** Consolidate into single fact, delete older ones")
                lines.append("")
        else:
            lines.append("✓ No redundant facts found")
            lines.append("")

    else:
        lines.append("_No facts folder found_")
        lines.append("")

    lines.append(dotted_line)

    # =========================================================================
    # 2. JOURNEY CONSOLIDATION CHECK
    # =========================================================================
    lines.append("")
    lines.append("## 2. Journey Consolidation Opportunities")
    lines.append("")

    journey_dir = Path('.claude/knowledge/journey')
    consolidation_suggestions = []

    if journey_dir.exists():
        # Collect all journeys with their metadata
        all_journeys = []
        for category_dir in journey_dir.iterdir():
            if not category_dir.is_dir() or category_dir.name.startswith(('_', '.')):
                continue

            for journey_subdir in category_dir.iterdir():
                if not journey_subdir.is_dir() or journey_subdir.name.startswith(('_', '.')):
                    continue

                meta_file = journey_subdir / '_meta.md'
                meta = parse_meta(meta_file) if meta_file.exists() else {}

                keywords = meta.get('keywords', [])
                if isinstance(keywords, str):
                    keywords = [k.strip() for k in keywords.split(',')]

                all_journeys.append({
                    'topic': meta.get('topic', journey_subdir.name),
                    'name': journey_subdir.name,
                    'category': category_dir.name,
                    'path': str(journey_subdir),
                    'keywords': set(k.lower() for k in keywords),
                    'entry_count': len([f for f in journey_subdir.glob('*.md') if f.name != '_meta.md'])
                })

        # Find journeys that could be consolidated
        used = set()
        for i, j1 in enumerate(all_journeys):
            if i in used:
                continue

            similar = [j1]
            for k, j2 in enumerate(all_journeys[i+1:], i+1):
                if k in used:
                    continue

                # Check name similarity
                name_sim = _calculate_similarity(j1['topic'], j2['topic'])

                # Check keyword overlap
                overlap = len(j1['keywords'] & j2['keywords'])
                keyword_score = overlap / max(len(j1['keywords'] | j2['keywords']), 1)

                if name_sim >= 0.5 or keyword_score >= 0.4 or overlap >= 3:
                    similar.append(j2)
                    used.add(k)

            if len(similar) > 1:
                used.add(i)
                consolidation_suggestions.append(similar)

        if consolidation_suggestions:
            lines.append(f"**Found {len(consolidation_suggestions)} potential consolidation opportunities:**")
            lines.append("")

            for idx, group in enumerate(consolidation_suggestions, 1):
                issues_found += 1
                lines.append(f"### Group {idx}")
                common_keywords = set.intersection(*[j['keywords'] for j in group]) if group else set()
                lines.append(f"  Common keywords: {', '.join(common_keywords) if common_keywords else 'none'}")
                lines.append("")

                for j in group:
                    lines.append(f"  - `{j['category']}/{j['name']}/` ({j['entry_count']} entries)")

                # Suggest parent folder name
                if common_keywords:
                    suggested_parent = '-'.join(sorted(common_keywords)[:2])
                else:
                    suggested_parent = group[0]['name'].split('-')[0]

                lines.append("")
                lines.append(f"  **Suggestion:** Combine under `{suggested_parent}/`")
                lines.append("")
        else:
            lines.append("✓ No consolidation opportunities found")
            lines.append("")

    else:
        lines.append("_No journey folder found_")
        lines.append("")

    lines.append(dotted_line)

    # =========================================================================
    # 3. CROSS-REFERENCE VALIDATION
    # =========================================================================
    lines.append("")
    lines.append("## 3. Index File Cross-Reference")
    lines.append("")

    knowledge_dir = Path('.claude/knowledge')

    # Check knowledge.json
    lines.append("### knowledge.json")
    knowledge_json_path = knowledge_dir / 'knowledge.json'
    kj_issues = []

    if knowledge_json_path.exists():
        try:
            kj_data = json.loads(knowledge_json_path.read_text(encoding='utf-8'))

            # Check files references
            files = kj_data.get('files', {})
            for rel_path, info in files.items():
                full_path = knowledge_dir / rel_path
                if not full_path.exists():
                    kj_issues.append(f"Missing file: `{rel_path}`")
                    issues_found += 1

            # Check pattern sources
            patterns = kj_data.get('patterns', [])
            source_files = set()
            for p in patterns:
                source = p.get('source', '')
                if source:
                    source_files.add(source)

            for source in source_files:
                full_path = knowledge_dir / source
                if not full_path.exists():
                    kj_issues.append(f"Pattern source missing: `{source}`")
                    issues_found += 1

            if kj_issues:
                for issue in kj_issues:
                    lines.append(f"  ⚠️  {issue}")
            else:
                lines.append(f"  ✓ All {len(files)} file references valid")
                lines.append(f"  ✓ All {len(source_files)} pattern sources valid")

        except json.JSONDecodeError:
            lines.append("  ⚠️  Invalid JSON format")
            issues_found += 1
    else:
        lines.append("  _File not found_")

    lines.append("")

    # Check coderef.json
    lines.append("### coderef.json")
    coderef_path = knowledge_dir / 'coderef.json'

    if coderef_path.exists():
        try:
            cr_data = json.loads(coderef_path.read_text(encoding='utf-8'))
            files = cr_data.get('files', {})

            if files:
                lines.append(f"  ✓ Contains {len(files)} file references")
            else:
                lines.append("  ✓ Empty (no code indexed yet)")

        except json.JSONDecodeError:
            lines.append("  ⚠️  Invalid JSON format")
            issues_found += 1
    else:
        lines.append("  _File not found_")

    lines.append("")

    # Check commit-history.md for orphaned knowledge references
    lines.append("### commit-history.md")
    commit_history_path = knowledge_dir / 'commit-history.md'
    ch_issues = []
    ch_valid_refs = 0
    ch_orphaned_refs = 0

    if commit_history_path.exists():
        try:
            content = commit_history_path.read_text(encoding='utf-8')

            # Extract knowledge file references (format: - path/to/file.md or - journey/... or - facts/...)
            # Look for lines starting with "- " under "**Knowledge used:**" sections
            refs = re.findall(r'^\s*-\s+([^\s]+\.md)\s*$', content, re.MULTILINE)

            for ref in refs:
                # Normalize path
                ref_normalized = ref.replace('\\', '/')

                # Try multiple possible base paths
                found = False
                for base in [knowledge_dir, knowledge_dir / 'journey', knowledge_dir / 'facts']:
                    full_path = base / ref_normalized
                    if full_path.exists():
                        found = True
                        ch_valid_refs += 1
                        break

                # Also check if it's an absolute-ish path within knowledge
                if not found and ref_normalized.startswith(('journey/', 'facts/')):
                    full_path = knowledge_dir / ref_normalized
                    if full_path.exists():
                        found = True
                        ch_valid_refs += 1

                if not found:
                    ch_issues.append(f"Orphaned reference: `{ref}`")
                    ch_orphaned_refs += 1
                    issues_found += 1

            if ch_issues:
                for issue in ch_issues[:5]:
                    lines.append(f"  ⚠️  {issue}")
                if len(ch_issues) > 5:
                    lines.append(f"  ... and {len(ch_issues) - 5} more orphaned references")
                lines.append("")
                lines.append(f"  **Tip:** These references point to deleted knowledge files.")
                lines.append(f"  They can be safely removed from commit-history.md")
            else:
                if ch_valid_refs > 0:
                    lines.append(f"  ✓ All {ch_valid_refs} knowledge references valid")
                else:
                    lines.append("  ✓ No knowledge references yet")

        except Exception as e:
            lines.append(f"  ⚠️  Error reading: {e}")
            issues_found += 1
    else:
        lines.append("  _File not found (will be created on first save commit)_")

    lines.append("")
    lines.append(dotted_line)

    # =========================================================================
    # SUMMARY
    # =========================================================================
    lines.append("")
    lines.append("## Summary")
    lines.append("")

    if issues_found == 0:
        lines.append("✅ **Knowledge base is clean - no issues found!**")
    else:
        lines.append(f"⚠️  **Found {issues_found} issue(s) to address**")
        lines.append("")
        lines.append("To fix issues:")
        lines.append("1. Review redundant facts and consolidate manually")
        lines.append("2. Reorganize journeys using suggested groupings")
        lines.append("3. Delete orphaned references or run re-indexing")
        lines.append("4. Clean orphaned entries from commit-history.md")

    lines.append("")

    return '\n'.join(lines)


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: _wip_helpers.py <command> [args]")
        print("\nCommands:")
        print("  scan_categories          - List parent category folders")
        print("  save_fact <text>         - Save a fact to knowledge/facts/")
        print("  knowledge_status         - Show knowledge base status")
        print("  reset_knowledge          - Show what would be reset (dry run)")
        print("  reset_knowledge -archive - Archive current knowledge, then reset")
        print("  reset_knowledge -force   - Full reset without archive")
        print("")
        print("Pattern commands:")
        print("  extract_patterns <file>  - Extract patterns from journey file")
        print("  search_patterns <query>  - Search patterns by keywords")
        print("  list_patterns [type]     - List all patterns (optionally by type)")
        print("  index_all_patterns       - Re-index patterns from all journeys")
        print("")
        print("Audit commands:")
        print("  audit_knowledge          - Full knowledge base audit")
        print("  find_similar_facts <txt> - Find facts similar to text (dupe-check)")
        print("")
        print("Meta commands:")
        print("  create_entry <cat> <topic> <content> [slug] - Create journey entry file (auto-timestamps)")
        print("  create_or_update_meta <category> <topic> <keywords> - Create/update journey _meta.md")
        sys.exit(1)

    command = sys.argv[1]

    if command == 'scan_categories':
        print(json.dumps(scan_category_folders()))

    elif command == 'save_fact':
        if len(sys.argv) < 3:
            print("Error: fact text required")
            sys.exit(1)
        fact_text = ' '.join(sys.argv[2:])
        file_path = save_fact(fact_text)
        print(json.dumps({
            'success': True,
            'file': str(file_path)
        }))

    elif command == 'knowledge_status':
        print(get_knowledge_status())

    elif command == 'reset_knowledge':
        if '-archive' in sys.argv:
            print(reset_knowledge(archive=True, dry_run=False))
        elif '-force' in sys.argv:
            print(reset_knowledge(archive=False, dry_run=False))
        else:
            print(reset_knowledge(dry_run=True))

    # Pattern commands
    elif command == 'extract_patterns':
        if len(sys.argv) < 3:
            print(json.dumps({'error': 'File path required'}))
            sys.exit(1)
        filepath = sys.argv[2]
        try:
            content = Path(filepath).read_text(encoding='utf-8')
            patterns = extract_patterns_from_content(content)
            if patterns:
                count = save_patterns_to_knowledge(patterns, filepath)
                print(json.dumps({
                    'success': True,
                    'patterns': patterns,
                    'count': count
                }, indent=2))
            else:
                print(json.dumps({
                    'success': True,
                    'patterns': [],
                    'count': 0,
                    'message': 'No patterns found in structured format'
                }))
        except Exception as e:
            print(json.dumps({'error': str(e)}))

    elif command == 'search_patterns':
        if len(sys.argv) < 3:
            print(json.dumps({'error': 'Search query required'}))
            sys.exit(1)
        query = ' '.join(sys.argv[2:])
        patterns = search_patterns(query)
        print(json.dumps({
            'query': query,
            'results': patterns,
            'count': len(patterns)
        }, indent=2))

    elif command == 'list_patterns':
        # Filter out flags from args
        args = [a for a in sys.argv[2:] if not a.startswith('-')]
        pattern_type = args[0] if args else None
        patterns = get_patterns(pattern_type=pattern_type)
        if '-format' in sys.argv or '--format' in sys.argv:
            print(format_patterns_for_display(patterns))
        else:
            print(json.dumps({
                'patterns': patterns,
                'count': len(patterns)
            }, indent=2))

    elif command == 'index_all_patterns':
        # Re-index patterns from all journey files
        journey_dir = Path('.claude/knowledge/journey')
        total_patterns = 0
        files_processed = 0

        if journey_dir.exists():
            for md_file in journey_dir.rglob('*.md'):
                if md_file.name == '_meta.md':
                    continue
                try:
                    content = md_file.read_text(encoding='utf-8')
                    patterns = extract_patterns_from_content(content)
                    if patterns:
                        count = save_patterns_to_knowledge(patterns, str(md_file))
                        total_patterns += count
                        files_processed += 1
                except Exception:
                    pass

        print(json.dumps({
            'success': True,
            'files_processed': files_processed,
            'total_patterns': total_patterns
        }))

    # Audit commands
    elif command == 'audit_knowledge':
        print(audit_knowledge())

    elif command == 'find_similar_facts':
        if len(sys.argv) < 3:
            print(json.dumps({'error': 'Fact text required'}))
            sys.exit(1)
        text = ' '.join(sys.argv[2:])
        threshold = 0.5
        # Check for threshold flag
        if '-t' in sys.argv:
            try:
                idx = sys.argv.index('-t')
                threshold = float(sys.argv[idx + 1])
                # Remove threshold args from text
                text = ' '.join([a for i, a in enumerate(sys.argv[2:]) if i != idx-2 and i != idx-1])
            except:
                pass
        similar = find_similar_facts(text, threshold)
        print(json.dumps({
            'query': text[:50],
            'threshold': threshold,
            'similar': similar,
            'count': len(similar)
        }, indent=2))

    # Meta commands
    elif command == 'create_or_update_meta':
        if len(sys.argv) < 5:
            print(json.dumps({'error': 'Usage: create_or_update_meta <category> <topic> <keywords>'}))
            sys.exit(1)
        category = sys.argv[2]
        topic = sys.argv[3]
        keywords = sys.argv[4]
        description = sys.argv[5] if len(sys.argv) > 5 else None
        meta_file = create_or_update_meta(category, topic, keywords, description)
        print(json.dumps({
            'success': True,
            'file': str(meta_file),
            'category': category,
            'topic': topic
        }))

    elif command == 'create_entry':
        if len(sys.argv) < 5:
            print(json.dumps({'error': 'Usage: create_entry <category> <topic> <content> [slug]'}))
            sys.exit(1)
        category = sys.argv[2]
        topic = sys.argv[3]
        content = sys.argv[4]
        slug = sys.argv[5] if len(sys.argv) > 5 else None
        result = create_entry(category, topic, content, slug)
        print(json.dumps(result, indent=2))

    elif command == 'create_entry_stdin':
        # Read JSON from stdin to avoid shell escaping issues with special characters
        data = json.load(sys.stdin)
        result = create_entry(
            data['category'],
            data['topic'],
            data['content'],
            data.get('slug')
        )
        print(json.dumps(result, indent=2))

    elif command == 'save_fact_stdin':
        # Read JSON from stdin to avoid shell escaping issues with special characters
        data = json.load(sys.stdin)
        file_path = save_fact(data['text'], data.get('slug'))
        print(json.dumps({
            'success': True,
            'file': str(file_path)
        }))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
