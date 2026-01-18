"""
Configuration management for ok-know plugin.

Loads settings from .claude/knowledge/config.json with sensible defaults.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ExtractionConfig:
    """Settings for automatic fact extraction."""
    enabled: bool = True
    model: str = "haiku"  # Cost-effective extraction
    trigger: str = "every_turn"  # When to extract: every_turn, on_demand
    min_confidence: float = 0.7  # Minimum confidence to store


@dataclass
class EmbeddingsConfig:
    """Settings for semantic embeddings."""
    enabled: bool = True
    model: str = "all-MiniLM-L6-v2"
    dimension: int = 384
    similarity_threshold: float = 0.85  # For deduplication


@dataclass
class SearchConfig:
    """Settings for hybrid search."""
    default_top_k: int = 5
    lexical_weight: float = 0.6
    semantic_weight: float = 0.4
    min_keyword_overlap: int = 2


@dataclass
class Config:
    """Main configuration for ok-know plugin."""

    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)
    search: SearchConfig = field(default_factory=SearchConfig)

    # Storage paths (relative to project root)
    knowledge_dir: str = ".claude/knowledge"
    database_name: str = "memory.db"

    @classmethod
    def load(cls, project_root: Optional[Path] = None) -> "Config":
        """
        Load configuration from config.json.

        Falls back to defaults if file doesn't exist.
        """
        if project_root is None:
            project_root = Path.cwd()

        config_path = project_root / ".claude" / "knowledge" / "config.json"

        config = cls()

        if config_path.exists():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))

                # Load extraction settings
                if "extraction" in data:
                    ext = data["extraction"]
                    config.extraction = ExtractionConfig(
                        enabled=ext.get("enabled", True),
                        model=ext.get("model", "haiku"),
                        trigger=ext.get("trigger", "every_turn"),
                        min_confidence=ext.get("min_confidence", 0.7),
                    )

                # Load embeddings settings
                if "embeddings" in data:
                    emb = data["embeddings"]
                    config.embeddings = EmbeddingsConfig(
                        enabled=emb.get("enabled", True),
                        model=emb.get("model", "all-MiniLM-L6-v2"),
                        dimension=emb.get("dimension", 384),
                        similarity_threshold=emb.get("similarity_threshold", 0.85),
                    )

                # Load search settings
                if "search" in data:
                    srch = data["search"]
                    config.search = SearchConfig(
                        default_top_k=srch.get("default_top_k", 5),
                        lexical_weight=srch.get("lexical_weight", 0.6),
                        semantic_weight=srch.get("semantic_weight", 0.4),
                        min_keyword_overlap=srch.get("min_keyword_overlap", 2),
                    )

                # Load storage settings
                config.knowledge_dir = data.get("knowledge_dir", ".claude/knowledge")
                config.database_name = data.get("database_name", "memory.db")

            except (json.JSONDecodeError, KeyError):
                pass  # Use defaults on error

        return config

    def save(self, project_root: Optional[Path] = None) -> None:
        """Save configuration to config.json."""
        if project_root is None:
            project_root = Path.cwd()

        config_path = project_root / ".claude" / "knowledge" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "extraction": {
                "enabled": self.extraction.enabled,
                "model": self.extraction.model,
                "trigger": self.extraction.trigger,
                "min_confidence": self.extraction.min_confidence,
            },
            "embeddings": {
                "enabled": self.embeddings.enabled,
                "model": self.embeddings.model,
                "dimension": self.embeddings.dimension,
                "similarity_threshold": self.embeddings.similarity_threshold,
            },
            "search": {
                "default_top_k": self.search.default_top_k,
                "lexical_weight": self.search.lexical_weight,
                "semantic_weight": self.search.semantic_weight,
                "min_keyword_overlap": self.search.min_keyword_overlap,
            },
            "knowledge_dir": self.knowledge_dir,
            "database_name": self.database_name,
        }

        config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @property
    def db_path(self) -> Path:
        """Get the full path to the database file."""
        return Path(self.knowledge_dir) / self.database_name
