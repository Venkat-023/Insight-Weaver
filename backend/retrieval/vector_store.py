from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from core.config import get_settings
from ingestion.chunker import Chunk


@dataclass
class SearchResult:
    id: str
    text: str
    metadata: dict[str, Any]
    similarity_score: float


class VectorStore:
    def __init__(self, load_model: bool = True) -> None:
        import chromadb

        settings = get_settings()
        self.client = chromadb.PersistentClient(path=settings.chroma_path)
        self.collection = self.client.get_or_create_collection("scientific_chunks", metadata={"hnsw:space": "cosine"})
        self.model = _get_embedding_model() if load_model else None

    def add_chunks(self, paper_id: int, chunks: list[Chunk], paper_meta: dict) -> list[str]:
        ids: list[str] = []
        for start in range(0, len(chunks), 32):
            batch = chunks[start : start + 32]
            batch_ids = [f"p{paper_id}_{chunk.section}_{chunk.sub_index}" for chunk in batch]
            embeddings = self.model.encode([chunk.content for chunk in batch], normalize_embeddings=True).tolist()
            metadatas = [
                {
                    "paper_id": paper_id,
                    "title": paper_meta.get("title") or "",
                    "section": chunk.section,
                    "importance_score": chunk.importance_score,
                    "year": paper_meta.get("year") or 0,
                    "authors_str": ", ".join(paper_meta.get("authors", [])),
                    "arxiv_id": paper_meta.get("arxiv_id") or "",
                    "workspace_id": paper_meta.get("workspace_id") or "legacy",
                }
                for chunk in batch
            ]
            self.collection.upsert(
                ids=batch_ids,
                embeddings=embeddings,
                documents=[chunk.content for chunk in batch],
                metadatas=metadatas,
            )
            ids.extend(batch_ids)
        return ids

    def search(
        self,
        query: str,
        n_results: int = 15,
        filter_paper_id: int | None = None,
        filter_section: str | None = None,
        workspace_id: str | None = None,
        min_importance: float = 0.0,
    ) -> list[SearchResult]:
        where: dict[str, Any] = {}
        if workspace_id is not None:
            where["workspace_id"] = workspace_id
        if filter_paper_id is not None:
            where["paper_id"] = filter_paper_id
        if filter_section:
            where["section"] = filter_section
        embeddings = self.model.encode([query], normalize_embeddings=True).tolist()
        result = self.collection.query(query_embeddings=embeddings, n_results=n_results, where=where or None)
        return self._to_search_results(result, min_importance)

    def find_cross_paper_similar(
        self,
        chunk_text: str,
        exclude_paper_ids: list[int],
        n_results: int = 10,
        similarity_threshold: float = 0.78,
        workspace_id: str | None = None,
    ) -> list[SearchResult]:
        embeddings = self.model.encode([chunk_text], normalize_embeddings=True).tolist()
        where: dict[str, Any] = {"paper_id": {"$nin": exclude_paper_ids}}
        if workspace_id is not None:
            where = {"$and": [{"paper_id": {"$nin": exclude_paper_ids}}, {"workspace_id": workspace_id}]}
        result = self.collection.query(
            query_embeddings=embeddings,
            n_results=n_results,
            where=where,
        )
        return [item for item in self._to_search_results(result, 0.0) if item.similarity_score >= similarity_threshold]

    def delete_paper(self, paper_id: int) -> None:
        self.collection.delete(where={"paper_id": paper_id})

    def delete_workspace(self, workspace_id: str) -> None:
        self.collection.delete(where={"workspace_id": workspace_id})

    @staticmethod
    def _to_search_results(result: dict, min_importance: float) -> list[SearchResult]:
        output: list[SearchResult] = []
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        for item_id, doc, meta, distance in zip(ids, docs, metas, distances, strict=False):
            if float(meta.get("importance_score", 0)) < min_importance:
                continue
            output.append(SearchResult(item_id, doc, meta, 1.0 - float(distance)))
        return sorted(output, key=lambda item: item.similarity_score, reverse=True)


@lru_cache(maxsize=1)
def _get_embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")
