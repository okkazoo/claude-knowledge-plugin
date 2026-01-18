"""
Hybrid search module combining keyword (FTS5) and semantic search.

Uses Reciprocal Rank Fusion (RRF) to merge results from both methods.
Adapts retrieval strategy based on query complexity.
"""

import re
from typing import List, Optional, Tuple, Dict
from pathlib import Path

from .models import AtomicFact, FactType
from .config import Config
from .database import Database
from .embedder import Embedder


# Common stop words for keyword extraction
STOP_WORDS = {
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
    'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
    'from', 'as', 'into', 'through', 'during', 'before', 'after', 'above',
    'below', 'between', 'under', 'again', 'further', 'then', 'once',
    'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each', 'few',
    'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
    'own', 'same', 'so', 'than', 'too', 'very', 'just', 'and', 'but',
    'if', 'or', 'because', 'until', 'while', 'this', 'that', 'these',
    'those', 'am', 'it', 'its', 'i', 'me', 'my', 'you', 'your', 'we', 'our',
    'they', 'them', 'their', 'what', 'which', 'who', 'whom', 'any', 'both',
    'let', 'get', 'got', 'make', 'made', 'want', 'please', 'help', 'try',
    'also', 'like', 'using', 'use', 'about', 'know', 'think',
}


def extract_keywords(text: str, min_length: int = 3) -> List[str]:
    """Extract meaningful keywords from text."""
    words = re.findall(r'[a-zA-Z0-9_-]+', text.lower())
    keywords = []
    for word in words:
        if len(word) >= min_length and word not in STOP_WORDS:
            keywords.append(word)
    return list(set(keywords))


def reciprocal_rank_fusion(
    ranked_lists: List[List[Tuple[str, float]]],
    k: int = 60
) -> List[Tuple[str, float]]:
    """
    Merge multiple ranked lists using Reciprocal Rank Fusion.

    RRF score = sum(1 / (k + rank)) for each list where item appears.

    Args:
        ranked_lists: List of ranked result lists, each containing (id, score) tuples
        k: Constant to prevent high scores for top ranks (default 60)

    Returns:
        Merged list of (id, rrf_score) tuples, sorted by score descending
    """
    rrf_scores: Dict[str, float] = {}

    for ranked_list in ranked_lists:
        for rank, (item_id, _) in enumerate(ranked_list, start=1):
            if item_id not in rrf_scores:
                rrf_scores[item_id] = 0.0
            rrf_scores[item_id] += 1.0 / (k + rank)

    # Sort by RRF score descending
    sorted_results = sorted(rrf_scores.items(), key=lambda x: -x[1])
    return sorted_results


class Searcher:
    """
    Hybrid search combining keyword (FTS5) and semantic (embedding) search.

    Uses adaptive retrieval based on query complexity:
    - Simple queries (< 5 words): Top 3 results
    - Moderate queries: Top 7 results
    - Complex queries: Top 15 + related facts
    """

    def __init__(
        self,
        db: Optional[Database] = None,
        embedder: Optional[Embedder] = None,
        config: Optional[Config] = None,
        project_root: Optional[Path] = None
    ):
        """
        Initialize searcher.

        Args:
            db: Database instance. Creates new one if not provided.
            embedder: Embedder instance. Creates new one if not provided.
            config: Configuration object.
            project_root: Project root directory.
        """
        self.project_root = project_root or Path.cwd()
        self.config = config or Config.load(self.project_root)
        self.db = db or Database(self.config, self.project_root)
        self.embedder = embedder or Embedder(self.config)

    def _adaptive_top_k(self, query: str) -> int:
        """Determine top_k based on query complexity."""
        word_count = len(query.split())

        if word_count < 5:
            return 3
        elif word_count < 15:
            return 7
        else:
            return 15

    def search_keyword(
        self,
        query: str,
        limit: int = 10
    ) -> List[Tuple[AtomicFact, float]]:
        """
        Keyword search using FTS5.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of (fact, score) tuples
        """
        # Extract keywords and build FTS5 query
        keywords = extract_keywords(query)

        if not keywords:
            return []

        # Use OR for broader matching, quoted phrases for exact matches
        fts_query = " OR ".join(keywords)

        try:
            return self.db.search_fts(fts_query, limit)
        except Exception:
            # FTS5 query syntax error - try simpler query
            try:
                # Fall back to single keyword
                return self.db.search_fts(keywords[0], limit)
            except Exception:
                return []

    def search_semantic(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.3
    ) -> List[Tuple[AtomicFact, float]]:
        """
        Semantic search using embeddings.

        Args:
            query: Search query
            limit: Maximum results
            threshold: Minimum similarity threshold

        Returns:
            List of (fact, similarity) tuples
        """
        if not self.embedder.is_available():
            return []

        # Get query embedding
        query_embedding = self.embedder.embed(query)
        if query_embedding is None:
            return []

        # Get all embeddings from database
        all_embeddings = self.db.get_all_embeddings()
        if not all_embeddings:
            return []

        # Find similar facts
        similar = self.embedder.find_similar(
            query_embedding,
            all_embeddings,
            top_k=limit,
            threshold=threshold
        )

        # Load full facts
        results = []
        for fact_id, similarity in similar:
            fact = self.db.get_fact(fact_id)
            if fact:
                results.append((fact, similarity))

        return results

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        fact_types: Optional[List[FactType]] = None,
        file_filter: Optional[str] = None
    ) -> List[Tuple[AtomicFact, float]]:
        """
        Hybrid search combining keyword and semantic search.

        Uses Reciprocal Rank Fusion to merge results.

        Args:
            query: Search query
            top_k: Number of results. Auto-determined if not provided.
            fact_types: Filter by fact types
            file_filter: Filter by file path (substring match)

        Returns:
            List of (fact, score) tuples, sorted by relevance
        """
        if top_k is None:
            top_k = self._adaptive_top_k(query)

        # Get keyword results
        keyword_limit = top_k * 2  # Get more for fusion
        keyword_results = self.search_keyword(query, keyword_limit)

        # Convert to ranked list format
        keyword_ranked = [
            (fact.id, score)
            for fact, score in keyword_results
        ]

        # Get semantic results
        semantic_results = []
        if self.embedder.is_available():
            semantic_results = self.search_semantic(query, keyword_limit)

        semantic_ranked = [
            (fact.id, score)
            for fact, score in semantic_results
        ]

        # Apply RRF fusion
        if keyword_ranked and semantic_ranked:
            # Apply configured weights through multiplying ranks
            # Higher weight = results appear earlier = lower effective rank
            lexical_weight = self.config.search.lexical_weight
            semantic_weight = self.config.search.semantic_weight

            # Weight by repeating entries (simple approximation)
            weighted_lists = []

            # Add keyword results weighted
            if lexical_weight > 0:
                for _ in range(int(lexical_weight * 10)):
                    weighted_lists.append(keyword_ranked)

            # Add semantic results weighted
            if semantic_weight > 0:
                for _ in range(int(semantic_weight * 10)):
                    weighted_lists.append(semantic_ranked)

            fused = reciprocal_rank_fusion(weighted_lists)
        elif keyword_ranked:
            fused = keyword_ranked
        elif semantic_ranked:
            fused = semantic_ranked
        else:
            return []

        # Load facts and apply filters
        results = []
        seen_ids = set()

        for fact_id, rrf_score in fused:
            if fact_id in seen_ids:
                continue
            seen_ids.add(fact_id)

            fact = self.db.get_fact(fact_id)
            if fact is None:
                continue

            # Apply type filter
            if fact_types and fact.fact_type not in fact_types:
                continue

            # Apply file filter
            if file_filter:
                if not any(file_filter in f for f in fact.file_refs):
                    continue

            results.append((fact, rrf_score))

            if len(results) >= top_k:
                break

        return results

    def search_by_file(self, file_path: str) -> List[AtomicFact]:
        """Get all facts related to a specific file."""
        return self.db.get_facts_by_file(file_path)

    def get_related_facts(
        self,
        fact: AtomicFact,
        top_k: int = 5
    ) -> List[Tuple[AtomicFact, float]]:
        """
        Get facts related to a given fact.

        Uses entity overlap and semantic similarity.

        Args:
            fact: The fact to find related facts for
            top_k: Number of related facts to return

        Returns:
            List of (fact, similarity) tuples
        """
        if fact.embedding is None or not self.embedder.is_available():
            # Fall back to entity-based search
            results = []
            for entity in fact.entities[:3]:  # Limit entities
                keyword_results = self.search_keyword(entity, 5)
                for related_fact, score in keyword_results:
                    if related_fact.id != fact.id:
                        results.append((related_fact, score))
            return results[:top_k]

        # Semantic search for related facts
        all_embeddings = self.db.get_all_embeddings()

        # Filter out the source fact
        filtered = [
            (id_, emb) for id_, emb in all_embeddings
            if id_ != fact.id
        ]

        if not filtered:
            return []

        similar = self.embedder.find_similar(
            fact.embedding,
            filtered,
            top_k=top_k,
            threshold=0.5
        )

        results = []
        for fact_id, similarity in similar:
            related = self.db.get_fact(fact_id)
            if related:
                results.append((related, similarity))

        return results


# Convenience function for quick searches
def quick_search(
    query: str,
    top_k: int = 5,
    project_root: Optional[Path] = None
) -> List[Tuple[AtomicFact, float]]:
    """
    Perform a quick hybrid search.

    Creates temporary instances for one-off searches.
    """
    searcher = Searcher(project_root=project_root)
    return searcher.search(query, top_k)
