from dataclasses import dataclass
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.gemma_engine import GemmaEngine
from graph.graph_builder import KnowledgeGraphBuilder
from models.hypothesis import Contradiction as ContradictionModel
from models.paper import Chunk, Paper
from retrieval.vector_store import VectorStore


@dataclass
class UnexploredConnection:
    source_paper_id: int
    target_paper_id: int
    target_paper_title: str
    similarity_score: float
    connection_score: float
    source_excerpt: str
    target_excerpt: str
    shared_concepts: list[str]


class CrossPaperReasoner:
    def __init__(
        self,
        vector_store: VectorStore | None,
        gemma: GemmaEngine,
        graph_builder: KnowledgeGraphBuilder | None = None,
    ) -> None:
        self.vector_store = vector_store
        self.gemma = gemma
        self.graph_builder = graph_builder

    async def find_unexplored_connections(
        self, paper_id: int, db: AsyncSession
    ) -> list[UnexploredConnection]:
        if self.vector_store is None:
            return []
        result = await db.execute(
            select(Chunk)
            .where(Chunk.paper_id == paper_id)
            .order_by(Chunk.importance_score.desc())
            .limit(5)
        )
        source_chunks = result.scalars().all()
        best: dict[int, UnexploredConnection] = {}
        for chunk in source_chunks:
            try:
                similar_items = self.vector_store.find_cross_paper_similar(chunk.content, [paper_id])
            except Exception:
                continue
            for similar in similar_items:
                target_id = int(similar.metadata.get("paper_id", 0))
                if not target_id:
                    continue
                score = similar.similarity_score
                existing = best.get(target_id)
                if existing and existing.connection_score >= score:
                    continue
                best[target_id] = UnexploredConnection(
                    source_paper_id=paper_id,
                    target_paper_id=target_id,
                    target_paper_title=similar.metadata.get("title", ""),
                    similarity_score=score,
                    connection_score=score,
                    source_excerpt=chunk.content[:150],
                    target_excerpt=similar.text[:150],
                    shared_concepts=[],
                )
        return sorted(best.values(), key=lambda item: item.connection_score, reverse=True)[:10]

    async def detect_contradictions(
        self, topic: str, paper_ids: list[int], db: AsyncSession
    ) -> list[dict]:
        if not paper_ids or len(paper_ids) < 2:
            return []

        # Gather text per paper (use vector store if available, else skip retrieval)
        paper_chunks: dict[int, str] = {}
        if self.vector_store is not None:
            for paper_id in paper_ids:
                try:
                    results = self.vector_store.search(topic, n_results=5, filter_paper_id=paper_id)
                    paper_chunks[paper_id] = "\n\n".join(item.text for item in results)
                except Exception:
                    paper_chunks[paper_id] = ""
        else:
            for paper_id in paper_ids:
                paper_chunks[paper_id] = ""

        found: list[dict] = []
        for paper_a_id, paper_b_id in combinations(paper_ids, 2):
            text_a = paper_chunks.get(paper_a_id, "")
            text_b = paper_chunks.get(paper_b_id, "")
            if not text_a or not text_b:
                found.append({
                    "paper_a_id": paper_a_id,
                    "paper_b_id": paper_b_id,
                    "topic": topic,
                    "has_contradiction": False,
                    "severity": "LOW",
                    "contradiction_type": "insufficient_data",
                    "paper_a_claim": "",
                    "paper_b_claim": "",
                    "explanation": "Not enough indexed text for these papers to run contradiction analysis. Upload and process the papers first.",
                    "resolution_suggestion": "Ensure papers are fully processed (status: completed) before running contradiction analysis.",
                })
                continue
            try:
                verdict = self.gemma.detect_contradiction(text_a, text_b, topic)
            except Exception as exc:
                verdict = {
                    "has_contradiction": False,
                    "severity": "LOW",
                    "contradiction_type": "model_error",
                    "paper_a_claim": "",
                    "paper_b_claim": "",
                    "explanation": f"Model error during contradiction analysis: {exc}",
                    "resolution_suggestion": "Retry with a smaller topic scope.",
                }
            row_data = {**verdict, "paper_a_id": paper_a_id, "paper_b_id": paper_b_id, "topic": topic}
            found.append(row_data)
            if verdict.get("has_contradiction") is True and verdict.get("severity") != "LOW":
                row = ContradictionModel(
                    paper_a_id=paper_a_id,
                    paper_b_id=paper_b_id,
                    severity=verdict.get("severity", "MEDIUM"),
                    contradiction_type=verdict.get("contradiction_type", "interpretation"),
                    paper_a_claim=verdict.get("paper_a_claim"),
                    paper_b_claim=verdict.get("paper_b_claim"),
                    explanation=verdict.get("explanation"),
                    resolution_suggestion=verdict.get("resolution_suggestion"),
                    topic=topic,
                )
                db.add(row)
        await db.commit()
        return found

    async def analyze_research_landscape(self, topic: str, db: AsyncSession) -> dict:
        papers = (
            await db.execute(
                select(Paper).where(Paper.raw_text.ilike(f"%{topic}%")).limit(100)
            )
        ).scalars().all()
        years = [paper.publication_year for paper in papers if paper.publication_year]

        prompt = (
            f"Identify key milestones, paradigm shifts, open questions, and trending direction "
            f"for the research topic '{topic}' based on {len(papers)} papers. "
            "Return JSON with keys: key_milestones (list), paradigm_shifts (list), "
            "open_questions (list), trending_direction (string)."
        )
        try:
            analysis = self.gemma.generate_structured(prompt)
            # Ensure required keys exist
            analysis.setdefault("key_milestones", [])
            analysis.setdefault("paradigm_shifts", [])
            analysis.setdefault("open_questions", [])
            analysis.setdefault("trending_direction", "")
        except Exception as exc:
            analysis = {
                "key_milestones": ["Papers were indexed; detailed milestone extraction requires a longer model response."],
                "paradigm_shifts": ["The field is moving toward real-world clinical deployment and validation."],
                "open_questions": [f"Model analysis error: {exc}"],
                "trending_direction": "Clinical deployment, privacy-preserving validation, multi-center studies.",
                "warnings": ["Gemma analysis failed — showing deterministic fallback."],
            }

        return {
            "topic": topic,
            "paper_count": len(papers),
            "year_range": [min(years), max(years)] if years else None,
            **analysis,
        }
