"""
LLM-based fact extraction from conversation turns.

Features:
- Extracts atomic, standalone facts from assistant responses
- Coreference resolution (converts relative refs to absolute)
- Deduplication via embedding similarity
- Uses Claude Haiku for cost-effective extraction
"""

import json
import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .models import AtomicFact, FactType
from .config import Config
from .database import Database
from .embedder import Embedder

logger = logging.getLogger(__name__)


# Prompt template for fact extraction
EXTRACTION_PROMPT = '''Extract atomic facts from this conversation turn. Each fact should be:
1. Self-contained (understandable without conversation context)
2. Specific (include file names, function names, exact details)
3. Resolved (replace "it", "this", "the file" with actual names)

Conversation context (for reference resolution):
{context}

Turn to extract from:
{turn}

Output JSON array of facts:
```json
[
  {{
    "text": "Resolved, standalone fact statement",
    "type": "solution|gotcha|tried-failed|decision|context",
    "confidence": 0.0-1.0,
    "entities": ["file.py", "ClassName", "function_name"],
    "file_refs": ["path/to/file.py"],
    "keywords": ["keyword1", "keyword2"]
  }}
]
```

Types:
- solution: Working approach or fix
- gotcha: Important warning or caveat
- tried-failed: Approach that didn't work
- decision: Design or architecture decision
- context: General project context

Only extract facts that would be useful in future sessions. Skip trivial observations.
If no extractable facts, return empty array: []

Output ONLY the JSON array, no other text.'''


def _parse_json_from_response(response: str) -> List[dict]:
    """Extract JSON array from LLM response."""
    # Try to find JSON array in response
    patterns = [
        r'```json\s*(.*?)\s*```',  # Code block
        r'```\s*(.*?)\s*```',  # Generic code block
        r'(\[[\s\S]*\])',  # Raw array
    ]

    for pattern in patterns:
        match = re.search(pattern, response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

    # Last resort: try parsing entire response
    try:
        return json.loads(response.strip())
    except json.JSONDecodeError:
        return []


def _call_claude_api(prompt: str, model: str = "claude-3-haiku-20240307") -> Optional[str]:
    """
    Call Claude API for fact extraction.

    Tries multiple methods:
    1. Anthropic Python SDK
    2. Claude CLI subprocess
    """
    # Method 1: Try Anthropic SDK
    try:
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Anthropic SDK failed: {e}")

    # Method 2: Try Claude CLI
    try:
        result = subprocess.run(
            ["claude", "--print", "--model", "haiku", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    except Exception as e:
        logger.debug(f"Claude CLI failed: {e}")

    return None


class Extractor:
    """
    Extract atomic facts from conversation turns.

    Uses Claude Haiku for cost-effective extraction (~$0.001/turn).
    """

    def __init__(
        self,
        db: Optional[Database] = None,
        embedder: Optional[Embedder] = None,
        config: Optional[Config] = None,
        project_root: Optional[Path] = None
    ):
        """
        Initialize extractor.

        Args:
            db: Database instance for deduplication check
            embedder: Embedder for embedding new facts
            config: Configuration object
            project_root: Project root directory
        """
        self.project_root = project_root or Path.cwd()
        self.config = config or Config.load(self.project_root)
        self.db = db or Database(self.config, self.project_root)
        self.embedder = embedder or Embedder(self.config)

        # State for deferred extraction
        self._pending_turn: Optional[str] = None
        self._pending_context: Optional[str] = None

    def queue_for_extraction(self, turn: str, context: str = "") -> None:
        """
        Queue a turn for extraction on next call.

        Implements deferred extraction pattern:
        - Queue the current turn
        - Extract on next prompt submission

        Args:
            turn: The assistant's response to extract from
            context: Recent conversation context for coreference resolution
        """
        self._pending_turn = turn
        self._pending_context = context

    def extract_pending(self) -> List[AtomicFact]:
        """
        Extract facts from the queued turn.

        Call this at the start of each new turn to process
        the previous turn's content.

        Returns:
            List of extracted AtomicFacts
        """
        if not self._pending_turn:
            return []

        turn = self._pending_turn
        context = self._pending_context or ""

        # Clear pending state
        self._pending_turn = None
        self._pending_context = None

        return self.extract_from_turn(turn, context)

    def extract_from_turn(
        self,
        turn: str,
        context: str = "",
        turn_number: Optional[int] = None
    ) -> List[AtomicFact]:
        """
        Extract atomic facts from a conversation turn.

        Args:
            turn: The assistant's response to extract from
            context: Recent conversation for coreference resolution
            turn_number: Optional turn number for tracking

        Returns:
            List of extracted AtomicFacts (already deduplicated)
        """
        if not self.config.extraction.enabled:
            return []

        # Skip very short turns
        if len(turn.strip()) < 50:
            return []

        # Build extraction prompt
        prompt = EXTRACTION_PROMPT.format(
            context=context[:2000] if context else "No additional context",
            turn=turn[:4000]  # Limit turn length
        )

        # Get model setting
        model_map = {
            "haiku": "claude-3-haiku-20240307",
            "sonnet": "claude-sonnet-4-20250514",
            "opus": "claude-opus-4-20250514",
        }
        model = model_map.get(
            self.config.extraction.model,
            "claude-3-haiku-20240307"
        )

        # Call LLM
        response = _call_claude_api(prompt, model)
        if not response:
            logger.warning("Fact extraction failed: no LLM response")
            return []

        # Parse response
        raw_facts = _parse_json_from_response(response)
        if not raw_facts:
            return []

        # Convert to AtomicFact objects
        facts = []
        for raw in raw_facts:
            try:
                # Skip low confidence facts
                confidence = raw.get("confidence", 0.8)
                if confidence < self.config.extraction.min_confidence:
                    continue

                fact = AtomicFact(
                    text=raw.get("text", ""),
                    fact_type=FactType(raw.get("type", "context")),
                    confidence=confidence,
                    entities=raw.get("entities", []),
                    file_refs=raw.get("file_refs", []),
                    keywords=raw.get("keywords", []),
                    source_turn=turn_number,
                    source_type="auto",
                )

                # Skip if text is too short
                if len(fact.text) < 20:
                    continue

                facts.append(fact)

            except (ValueError, KeyError) as e:
                logger.debug(f"Skipping invalid fact: {e}")
                continue

        # Add embeddings
        if self.embedder.is_available() and facts:
            texts = [f.text for f in facts]
            embeddings = self.embedder.embed_batch(texts)
            for fact, embedding in zip(facts, embeddings):
                fact.embedding = embedding

        # Deduplicate against existing facts
        facts = self._deduplicate(facts)

        return facts

    def _deduplicate(self, facts: List[AtomicFact]) -> List[AtomicFact]:
        """Remove facts that are too similar to existing ones."""
        if not self.embedder.is_available():
            # Without embeddings, do simple text comparison
            existing_texts = set()
            for fact, _ in self.db.search_fts("*", 1000):  # Get all
                existing_texts.add(fact.text.lower())

            return [
                f for f in facts
                if f.text.lower() not in existing_texts
            ]

        # Get existing embeddings
        existing_embeddings = [
            emb for _, emb in self.db.get_all_embeddings()
        ]

        if not existing_embeddings:
            return facts

        # Filter out duplicates
        unique_facts = []
        threshold = self.config.embeddings.similarity_threshold

        for fact in facts:
            if fact.embedding is None:
                unique_facts.append(fact)
                continue

            is_dup = self.embedder.is_duplicate(
                fact.embedding,
                existing_embeddings,
                threshold
            )

            if not is_dup:
                unique_facts.append(fact)
                # Add to existing for checking subsequent facts
                existing_embeddings.append(fact.embedding)

        return unique_facts

    def extract_and_store(
        self,
        turn: str,
        context: str = "",
        turn_number: Optional[int] = None
    ) -> List[str]:
        """
        Extract facts and store them in the database.

        Args:
            turn: The assistant's response
            context: Recent conversation context
            turn_number: Optional turn number

        Returns:
            List of stored fact IDs
        """
        facts = self.extract_from_turn(turn, context, turn_number)

        stored_ids = []
        for fact in facts:
            fact_id = self.db.add_fact(fact)
            stored_ids.append(fact_id)
            logger.info(f"Stored fact: {fact.text[:50]}...")

        return stored_ids


def manual_fact(
    text: str,
    fact_type: FactType = FactType.CONTEXT,
    file_refs: Optional[List[str]] = None,
    project_root: Optional[Path] = None
) -> AtomicFact:
    """
    Create a fact from manual input.

    Args:
        text: The fact text
        fact_type: Type of fact
        file_refs: Optional file references
        project_root: Project root directory

    Returns:
        AtomicFact ready to be stored
    """
    config = Config.load(project_root)
    embedder = Embedder(config)

    # Extract keywords from text
    keywords = re.findall(r'[a-zA-Z0-9_-]+', text.lower())
    keywords = [k for k in keywords if len(k) >= 3][:10]

    # Extract entities (rough heuristic)
    entities = []
    # File patterns
    entities.extend(re.findall(r'[\w-]+\.[a-z]+', text))
    # CamelCase (likely class names)
    entities.extend(re.findall(r'[A-Z][a-z]+[A-Z]\w*', text))
    # Function patterns
    entities.extend(re.findall(r'\w+\(\)', text))

    fact = AtomicFact(
        text=text,
        fact_type=fact_type,
        confidence=1.0,
        entities=list(set(entities)),
        file_refs=file_refs or [],
        keywords=keywords,
        source_type="manual",
    )

    # Add embedding
    if embedder.is_available():
        fact.embedding = embedder.embed(text)

    return fact
