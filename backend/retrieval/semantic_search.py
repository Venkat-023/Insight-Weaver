from retrieval.vector_store import SearchResult, VectorStore


class SemanticSearch:
    def __init__(self, vector_store: VectorStore | None = None) -> None:
        self.vector_store = vector_store or VectorStore()

    def search(self, query: str, paper_ids: list[int] | None = None, n_results: int = 15, section_filter: str | None = None) -> list[SearchResult]:
        if paper_ids:
            merged: list[SearchResult] = []
            for paper_id in paper_ids:
                merged.extend(self.vector_store.search(query, n_results, filter_paper_id=paper_id, filter_section=section_filter))
            return sorted(merged, key=lambda item: item.similarity_score, reverse=True)[:n_results]
        return self.vector_store.search(query, n_results, filter_section=section_filter)
