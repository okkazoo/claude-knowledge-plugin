"""
AtomicFact data model for ok-know knowledge storage.

Each fact is a standalone, resolved statement that can be retrieved
without needing the original conversation context.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional
import uuid


class FactType(Enum):
    """Classification of atomic facts."""
    SOLUTION = "solution"       # Working approach/fix
    GOTCHA = "gotcha"           # Important warning/caveat
    TRIED_FAILED = "tried-failed"  # Approach that didn't work
    DECISION = "decision"       # Architectural/design decision
    CONTEXT = "context"         # General project context


@dataclass
class AtomicFact:
    """
    A single, standalone piece of knowledge.

    Designed to be self-contained - the text should make sense
    without needing to read the original conversation.

    Example transformation:
    - Before: "The hook isn't working because it returns early"
    - After: "pre-search.py hook returns early when search pattern < 2 chars"
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""  # Resolved, standalone statement
    timestamp: datetime = field(default_factory=datetime.now)

    # Classification
    fact_type: FactType = FactType.CONTEXT
    confidence: float = 1.0  # 0.0 - 1.0

    # References for context
    entities: List[str] = field(default_factory=list)  # Files, functions, classes
    file_refs: List[str] = field(default_factory=list)  # Referenced file paths
    keywords: List[str] = field(default_factory=list)  # For BM25/FTS5 search

    # Embeddings (populated by embedder module)
    embedding: Optional[List[float]] = None  # 384-dim vector for all-MiniLM-L6-v2

    # Source tracking
    source_turn: Optional[int] = None  # Which conversation turn this came from
    source_type: str = "auto"  # "auto" (extracted) or "manual" (user added)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON/SQLite storage."""
        return {
            "id": self.id,
            "text": self.text,
            "timestamp": self.timestamp.isoformat(),
            "fact_type": self.fact_type.value,
            "confidence": self.confidence,
            "entities": self.entities,
            "file_refs": self.file_refs,
            "keywords": self.keywords,
            "embedding": self.embedding,
            "source_turn": self.source_turn,
            "source_type": self.source_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AtomicFact":
        """Create AtomicFact from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            text=data.get("text", ""),
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.now(),
            fact_type=FactType(data.get("fact_type", "context")),
            confidence=data.get("confidence", 1.0),
            entities=data.get("entities", []),
            file_refs=data.get("file_refs", []),
            keywords=data.get("keywords", []),
            embedding=data.get("embedding"),
            source_turn=data.get("source_turn"),
            source_type=data.get("source_type", "auto"),
        )

    def __repr__(self) -> str:
        return f"AtomicFact(id={self.id[:8]}..., type={self.fact_type.value}, text={self.text[:50]}...)"
