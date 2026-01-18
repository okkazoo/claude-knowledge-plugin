"""
SQLite database layer for ok-know knowledge storage.

Features:
- FTS5 full-text search for fast keyword matching
- BLOB storage for embeddings
- Entity and file reference tables for efficient lookups
- ACID transactions for concurrent access
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
import struct

from .models import AtomicFact, FactType
from .config import Config


def _pack_embedding(embedding: List[float]) -> bytes:
    """Pack embedding list into bytes for BLOB storage."""
    return struct.pack(f'{len(embedding)}f', *embedding)


def _unpack_embedding(blob: bytes, dimension: int = 384) -> List[float]:
    """Unpack bytes back into embedding list."""
    return list(struct.unpack(f'{dimension}f', blob))


class Database:
    """
    SQLite database for atomic fact storage.

    Uses FTS5 for full-text search and BLOB for embeddings.
    """

    SCHEMA_VERSION = 1

    def __init__(self, config: Optional[Config] = None, project_root: Optional[Path] = None):
        """
        Initialize database connection.

        Args:
            config: Configuration object. Loads from file if not provided.
            project_root: Project root directory. Uses cwd if not provided.
        """
        self.project_root = project_root or Path.cwd()
        self.config = config or Config.load(self.project_root)

        self.db_path = self.project_root / self.config.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn: Optional[sqlite3.Connection] = None
        self._connect()
        self._init_schema()

    def _connect(self) -> None:
        """Establish database connection."""
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # Enable foreign keys
        self.conn.execute("PRAGMA foreign_keys = ON")

    def _init_schema(self) -> None:
        """Initialize database schema if not exists."""
        cursor = self.conn.cursor()

        # Check schema version
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_info (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        version_row = cursor.execute(
            "SELECT value FROM schema_info WHERE key = 'version'"
        ).fetchone()

        current_version = int(version_row['value']) if version_row else 0

        if current_version < self.SCHEMA_VERSION:
            self._create_tables()
            cursor.execute(
                "INSERT OR REPLACE INTO schema_info (key, value) VALUES ('version', ?)",
                (str(self.SCHEMA_VERSION),)
            )
            self.conn.commit()

    def _create_tables(self) -> None:
        """Create all required tables."""
        cursor = self.conn.cursor()

        # Main facts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                fact_type TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                source_turn INTEGER,
                source_type TEXT DEFAULT 'auto',
                keywords_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Entity references (files, functions, classes mentioned)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_value TEXT NOT NULL,
                FOREIGN KEY (fact_id) REFERENCES facts(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_entities_fact_id ON entities(fact_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_entities_value ON entities(entity_value)
        """)

        # File references
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_refs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                FOREIGN KEY (fact_id) REFERENCES facts(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_refs_fact_id ON file_refs(fact_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_refs_path ON file_refs(file_path)
        """)

        # FTS5 virtual table for full-text search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
                text,
                keywords,
                content='facts',
                content_rowid='rowid'
            )
        """)

        # Triggers to keep FTS in sync
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
                INSERT INTO facts_fts(rowid, text, keywords)
                VALUES (NEW.rowid, NEW.text, NEW.keywords_json);
            END
        """)
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
                INSERT INTO facts_fts(facts_fts, rowid, text, keywords)
                VALUES ('delete', OLD.rowid, OLD.text, OLD.keywords_json);
            END
        """)
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
                INSERT INTO facts_fts(facts_fts, rowid, text, keywords)
                VALUES ('delete', OLD.rowid, OLD.text, OLD.keywords_json);
                INSERT INTO facts_fts(rowid, text, keywords)
                VALUES (NEW.rowid, NEW.text, NEW.keywords_json);
            END
        """)

        # Embeddings table (separate for efficient vector operations)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                fact_id TEXT PRIMARY KEY,
                embedding BLOB NOT NULL,
                dimension INTEGER DEFAULT 384,
                FOREIGN KEY (fact_id) REFERENCES facts(id) ON DELETE CASCADE
            )
        """)

        self.conn.commit()

    def add_fact(self, fact: AtomicFact) -> str:
        """
        Add a new fact to the database.

        Args:
            fact: AtomicFact to store

        Returns:
            The fact ID
        """
        cursor = self.conn.cursor()

        # Insert main fact
        cursor.execute("""
            INSERT OR REPLACE INTO facts
            (id, text, timestamp, fact_type, confidence, source_turn, source_type, keywords_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fact.id,
            fact.text,
            fact.timestamp.isoformat(),
            fact.fact_type.value,
            fact.confidence,
            fact.source_turn,
            fact.source_type,
            json.dumps(fact.keywords),
        ))

        # Insert entities
        for entity in fact.entities:
            # Try to determine entity type
            entity_type = "unknown"
            if entity.endswith(('.py', '.js', '.ts', '.tsx', '.jsx', '.md', '.json')):
                entity_type = "file"
            elif entity[0].isupper():
                entity_type = "class"
            elif '(' in entity or entity.startswith('def '):
                entity_type = "function"

            cursor.execute("""
                INSERT INTO entities (fact_id, entity_type, entity_value)
                VALUES (?, ?, ?)
            """, (fact.id, entity_type, entity))

        # Insert file references
        for file_ref in fact.file_refs:
            cursor.execute("""
                INSERT INTO file_refs (fact_id, file_path)
                VALUES (?, ?)
            """, (fact.id, file_ref))

        # Insert embedding if present
        if fact.embedding:
            embedding_blob = _pack_embedding(fact.embedding)
            cursor.execute("""
                INSERT OR REPLACE INTO embeddings (fact_id, embedding, dimension)
                VALUES (?, ?, ?)
            """, (fact.id, embedding_blob, len(fact.embedding)))

        self.conn.commit()
        return fact.id

    def get_fact(self, fact_id: str) -> Optional[AtomicFact]:
        """Get a single fact by ID."""
        cursor = self.conn.cursor()

        row = cursor.execute(
            "SELECT * FROM facts WHERE id = ?", (fact_id,)
        ).fetchone()

        if not row:
            return None

        return self._row_to_fact(row)

    def _row_to_fact(self, row: sqlite3.Row) -> AtomicFact:
        """Convert a database row to an AtomicFact."""
        cursor = self.conn.cursor()

        # Get entities
        entities = [
            r['entity_value']
            for r in cursor.execute(
                "SELECT entity_value FROM entities WHERE fact_id = ?",
                (row['id'],)
            ).fetchall()
        ]

        # Get file refs
        file_refs = [
            r['file_path']
            for r in cursor.execute(
                "SELECT file_path FROM file_refs WHERE fact_id = ?",
                (row['id'],)
            ).fetchall()
        ]

        # Get embedding
        embedding = None
        emb_row = cursor.execute(
            "SELECT embedding, dimension FROM embeddings WHERE fact_id = ?",
            (row['id'],)
        ).fetchone()
        if emb_row:
            embedding = _unpack_embedding(emb_row['embedding'], emb_row['dimension'])

        # Parse keywords
        keywords = []
        if row['keywords_json']:
            try:
                keywords = json.loads(row['keywords_json'])
            except json.JSONDecodeError:
                pass

        return AtomicFact(
            id=row['id'],
            text=row['text'],
            timestamp=datetime.fromisoformat(row['timestamp']),
            fact_type=FactType(row['fact_type']),
            confidence=row['confidence'],
            entities=entities,
            file_refs=file_refs,
            keywords=keywords,
            embedding=embedding,
            source_turn=row['source_turn'],
            source_type=row['source_type'],
        )

    def delete_fact(self, fact_id: str) -> bool:
        """Delete a fact by ID. Returns True if deleted."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def search_fts(self, query: str, limit: int = 10) -> List[Tuple[AtomicFact, float]]:
        """
        Full-text search using FTS5.

        Args:
            query: Search query (supports FTS5 query syntax)
            limit: Maximum results to return

        Returns:
            List of (fact, score) tuples, sorted by relevance
        """
        cursor = self.conn.cursor()

        # Use FTS5 MATCH with BM25 ranking
        rows = cursor.execute("""
            SELECT facts.*, bm25(facts_fts) as score
            FROM facts_fts
            JOIN facts ON facts.rowid = facts_fts.rowid
            WHERE facts_fts MATCH ?
            ORDER BY score
            LIMIT ?
        """, (query, limit)).fetchall()

        results = []
        for row in rows:
            fact = self._row_to_fact(row)
            # BM25 returns negative values (lower is better), convert to positive
            score = -row['score']
            results.append((fact, score))

        return results

    def get_recent_facts(self, limit: int = 10, fact_type: Optional[FactType] = None) -> List[AtomicFact]:
        """Get most recent facts, optionally filtered by type."""
        cursor = self.conn.cursor()

        if fact_type:
            rows = cursor.execute("""
                SELECT * FROM facts
                WHERE fact_type = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (fact_type.value, limit)).fetchall()
        else:
            rows = cursor.execute("""
                SELECT * FROM facts
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,)).fetchall()

        return [self._row_to_fact(row) for row in rows]

    def get_facts_by_file(self, file_path: str) -> List[AtomicFact]:
        """Get all facts referencing a specific file."""
        cursor = self.conn.cursor()

        fact_ids = cursor.execute("""
            SELECT DISTINCT fact_id FROM file_refs
            WHERE file_path LIKE ?
        """, (f"%{file_path}%",)).fetchall()

        facts = []
        for row in fact_ids:
            fact = self.get_fact(row['fact_id'])
            if fact:
                facts.append(fact)

        return facts

    def get_all_embeddings(self) -> List[Tuple[str, List[float]]]:
        """
        Get all fact IDs and their embeddings.

        Returns:
            List of (fact_id, embedding) tuples
        """
        cursor = self.conn.cursor()

        rows = cursor.execute("""
            SELECT fact_id, embedding, dimension FROM embeddings
        """).fetchall()

        return [
            (row['fact_id'], _unpack_embedding(row['embedding'], row['dimension']))
            for row in rows
        ]

    def update_embedding(self, fact_id: str, embedding: List[float]) -> None:
        """Update or insert embedding for a fact."""
        cursor = self.conn.cursor()

        embedding_blob = _pack_embedding(embedding)
        cursor.execute("""
            INSERT OR REPLACE INTO embeddings (fact_id, embedding, dimension)
            VALUES (?, ?, ?)
        """, (fact_id, embedding_blob, len(embedding)))

        self.conn.commit()

    def get_stats(self) -> dict:
        """Get statistics about the knowledge base."""
        cursor = self.conn.cursor()

        total = cursor.execute("SELECT COUNT(*) as c FROM facts").fetchone()['c']

        by_type = {}
        for row in cursor.execute("""
            SELECT fact_type, COUNT(*) as c FROM facts GROUP BY fact_type
        """).fetchall():
            by_type[row['fact_type']] = row['c']

        with_embeddings = cursor.execute(
            "SELECT COUNT(*) as c FROM embeddings"
        ).fetchone()['c']

        return {
            "total_facts": total,
            "by_type": by_type,
            "with_embeddings": with_embeddings,
        }

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
