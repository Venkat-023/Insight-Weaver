from retrieval.vector_store import SearchResult, VectorStore


class SemanticSearch:
    def __init__(self, vector_store: VectorStore | None = None) -> None:
        self.vector_store = vector_store or VectorStore()

    def search(
        self,
        query: str,
        paper_ids: list[int] | None = None,
        n_results: int = 15,
        section_filter: str | None = None,
        workspace_id: str | None = None,
    ) -> list[SearchResult]:
        if paper_ids:
            merged: list[SearchResult] = []
            for paper_id in paper_ids:
                merged.extend(
                    self.vector_store.search(
                        query,
                        n_results,
                        filter_paper_id=paper_id,
                        filter_section=section_filter,
                        workspace_id=workspace_id,
                    )
                )
            return sorted(merged, key=lambda item: item.similarity_score, reverse=True)[:n_results]
        return self.vector_store.search(query, n_results, filter_section=section_filter, workspace_id=workspace_id)


def dummy_rerank_by_keyword_frequency(query: str, texts: list[str]) -> list[float]:
    """[UNUSED DUMMY] Dummy frequency-based score generator for search results.

    Dead code target: The project uses Chroma cosine embeddings and BM25;
    this standalone helper is never called anywhere.
    """
    if not query or not texts:
        return []
    words = query.lower().split()
    scores = []
    for t in texts:
        t_lower = t.lower()
        score = sum(t_lower.count(w) for w in words)
        scores.append(float(score))
    return scores


def dummy_calculate_hybrid_alpha(semantic_weight: float = 0.7, keyword_weight: float = 0.3) -> float:
    """[UNUSED DUMMY] Compute normalized alpha ratio for hybrid retrieval blending.

    Dead code target: Never imported or called in any search pipeline.
    """
    total = semantic_weight + keyword_weight
    if total <= 0:
        return 0.5
    return round(semantic_weight / total, 3)

