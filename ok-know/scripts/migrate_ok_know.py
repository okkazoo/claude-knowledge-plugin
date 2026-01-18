#!/usr/bin/env python3
"""
Migration script: Convert ok-know v1 data to v2 SQLite format.

Migrates:
- knowledge.json patterns → facts table
- journey/**/*.md entries → facts table
- facts/*.md files → facts table

Creates backup in .claude/knowledge/legacy/
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for core imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import Database
from core.config import Config
from core.models import AtomicFact, FactType
from core.embedder import Embedder


def parse_frontmatter(content: str) -> tuple:
    """Parse YAML frontmatter from markdown file."""
    if not content.startswith('---'):
        return {}, content

    try:
        end = content.index('---', 3)
        frontmatter = content[3:end].strip()
        body = content[end + 3:].strip()

        # Simple YAML parsing
        meta = {}
        for line in frontmatter.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip().strip('"\'')
                if value.startswith('[') and value.endswith(']'):
                    # Parse simple list
                    value = [v.strip().strip('"\'') for v in value[1:-1].split(',')]
                meta[key] = value

        return meta, body
    except (ValueError, IndexError):
        return {}, content


def migrate_patterns(knowledge_json: Path, db: Database, embedder: Embedder) -> int:
    """Migrate patterns from knowledge.json."""
    if not knowledge_json.exists():
        return 0

    try:
        data = json.loads(knowledge_json.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, IOError):
        print(f"Warning: Could not read {knowledge_json}")
        return 0

    patterns = data.get('patterns', [])
    count = 0

    type_map = {
        'solution': FactType.SOLUTION,
        'gotcha': FactType.GOTCHA,
        'tried-failed': FactType.TRIED_FAILED,
        'best-practice': FactType.DECISION,
    }

    for p in patterns:
        text = p.get('pattern', p.get('text', ''))
        if not text:
            continue

        ptype = p.get('type', 'context')
        fact_type = type_map.get(ptype, FactType.CONTEXT)

        context = p.get('context', [])
        if isinstance(context, str):
            context = context.split(',')
        keywords = [c.strip().lower() for c in context if c.strip()]

        fact = AtomicFact(
            text=text,
            fact_type=fact_type,
            confidence=1.0,
            keywords=keywords,
            source_type="migrated",
        )

        # Add embedding
        if embedder.is_available():
            fact.embedding = embedder.embed(text)

        db.add_fact(fact)
        count += 1

    return count


def migrate_journey_files(journey_dir: Path, db: Database, embedder: Embedder) -> int:
    """Migrate journey markdown files."""
    if not journey_dir.exists():
        return 0

    count = 0

    for md_file in journey_dir.glob('**/*.md'):
        if md_file.name.startswith('_'):
            continue

        try:
            content = md_file.read_text(encoding='utf-8')
        except IOError:
            continue

        meta, body = parse_frontmatter(content)

        # Skip if no meaningful content
        if len(body) < 20:
            continue

        # Extract fact type from metadata or filename
        fact_type = FactType.CONTEXT
        if 'type' in meta:
            type_map = {
                'solution': FactType.SOLUTION,
                'gotcha': FactType.GOTCHA,
                'tried-failed': FactType.TRIED_FAILED,
                'decision': FactType.DECISION,
            }
            fact_type = type_map.get(meta['type'], FactType.CONTEXT)

        # Build fact text from title + body summary
        title = meta.get('title', md_file.stem.replace('-', ' '))
        text = f"{title}: {body[:200].strip()}"
        if len(body) > 200:
            text = text[:197] + "..."

        # Extract keywords
        keywords = meta.get('keywords', [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(',')]

        # Extract file refs
        file_refs = []
        file_patterns = re.findall(r'`([^`]+\.[a-z]+)`', body)
        file_refs.extend(file_patterns[:5])

        fact = AtomicFact(
            text=text,
            fact_type=fact_type,
            confidence=0.9,
            keywords=keywords,
            file_refs=file_refs,
            source_type="migrated",
        )

        if embedder.is_available():
            fact.embedding = embedder.embed(text)

        db.add_fact(fact)
        count += 1

    return count


def migrate_facts_files(facts_dir: Path, db: Database, embedder: Embedder) -> int:
    """Migrate facts/*.md files."""
    if not facts_dir.exists():
        return 0

    count = 0

    for md_file in facts_dir.glob('*.md'):
        try:
            content = md_file.read_text(encoding='utf-8')
        except IOError:
            continue

        meta, body = parse_frontmatter(content)

        if len(body) < 10:
            continue

        # Get title and text
        title = meta.get('title', md_file.stem.replace('-', ' '))
        text = f"{title}: {body[:150].strip()}" if body else title

        # Determine type
        fact_type = FactType.CONTEXT
        if 'gotcha' in md_file.name.lower() or 'warning' in body.lower():
            fact_type = FactType.GOTCHA
        elif 'solution' in md_file.name.lower() or 'fix' in body.lower():
            fact_type = FactType.SOLUTION

        keywords = meta.get('keywords', [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(',')]

        fact = AtomicFact(
            text=text,
            fact_type=fact_type,
            confidence=0.8,
            keywords=keywords,
            source_type="migrated",
        )

        if embedder.is_available():
            fact.embedding = embedder.embed(text)

        db.add_fact(fact)
        count += 1

    return count


def backup_legacy(knowledge_dir: Path) -> Path:
    """Create backup of legacy files."""
    legacy_dir = knowledge_dir / 'legacy'
    legacy_dir.mkdir(exist_ok=True)

    # Move knowledge.json
    knowledge_json = knowledge_dir / 'knowledge.json'
    if knowledge_json.exists():
        legacy_json = legacy_dir / 'knowledge.json'
        if not legacy_json.exists():
            knowledge_json.rename(legacy_json)
            print(f"Backed up: knowledge.json -> legacy/")

    return legacy_dir


def main():
    print("ok-know v1 → v2 Migration")
    print("=" * 40)

    knowledge_dir = Path('.claude/knowledge')
    if not knowledge_dir.exists():
        print("No .claude/knowledge directory found. Nothing to migrate.")
        return

    # Initialize components
    config = Config.load()
    db = Database(config)
    embedder = Embedder(config)

    if embedder.is_available():
        print("Embeddings: enabled (will compute for all facts)")
    else:
        print("Embeddings: disabled (install sentence-transformers for semantic search)")

    # Create backup
    backup_legacy(knowledge_dir)

    # Migrate patterns
    knowledge_json = knowledge_dir / 'legacy' / 'knowledge.json'
    if not knowledge_json.exists():
        knowledge_json = knowledge_dir / 'knowledge.json'

    pattern_count = migrate_patterns(knowledge_json, db, embedder)
    print(f"Migrated {pattern_count} patterns from knowledge.json")

    # Migrate journey files
    journey_dir = knowledge_dir / 'journey'
    journey_count = migrate_journey_files(journey_dir, db, embedder)
    print(f"Migrated {journey_count} journey entries")

    # Migrate facts files
    facts_dir = knowledge_dir / 'facts'
    facts_count = migrate_facts_files(facts_dir, db, embedder)
    print(f"Migrated {facts_count} fact files")

    # Summary
    print("=" * 40)
    total = pattern_count + journey_count + facts_count
    print(f"Total migrated: {total} facts")

    stats = db.get_stats()
    print(f"Database now contains: {stats['total_facts']} facts")
    print(f"  With embeddings: {stats.get('with_embeddings', 0)}")

    db.close()
    print("\nMigration complete!")
    print("Original files preserved in .claude/knowledge/legacy/")


if __name__ == "__main__":
    main()
