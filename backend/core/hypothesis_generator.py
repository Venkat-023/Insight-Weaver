from sqlalchemy.ext.asyncio import AsyncSession

from core.gemma_engine import GemmaEngine
from graph.graph_builder import KnowledgeGraphBuilder
from models.hypothesis import Hypothesis
from reasoning.cross_paper_reasoner import CrossPaperReasoner
from retrieval.vector_store import SearchResult, VectorStore


class HypothesisGenerator:
    def __init__(
        self,
        gemma: GemmaEngine,
        vector_store: VectorStore | None,
        cross_paper_reasoner: CrossPaperReasoner,
        graph_builder: KnowledgeGraphBuilder | None = None,
    ) -> None:
        self.gemma = gemma
        self.vector_store = vector_store
        self.cross_paper_reasoner = cross_paper_reasoner
        self.graph_builder = graph_builder

    async def generate(
        self,
        query: str,
        db: AsyncSession,
        paper_ids: list[int] | None = None,
        num_hypotheses: int = 3,
        use_fast_fallback: bool = False,
    ) -> dict:
        retrieved = self._retrieve(query, paper_ids)
        gaps = self._identify_gaps(retrieved, use_fast_fallback)

        # Cross-paper connections only when not in fast mode and vector store available
        connections: list[dict] = []
        if paper_ids and not use_fast_fallback and self.vector_store is not None:
            for paper_id in paper_ids[:3]:
                try:
                    raw = await self.cross_paper_reasoner.find_unexplored_connections(paper_id, db)
                    connections.extend([item.__dict__ for item in raw])
                except Exception:
                    pass

        graph_context = self._graph_context(query)
        chunks_text = "\n\n".join(
            f'[Paper: "{item.metadata.get("title", "")}" | Section: {item.metadata.get("section")} | Relevance: {item.similarity_score:.3f}] {item.text}'
            for item in retrieved
        )
        context = {
            "query": query,
            "chunks_text": chunks_text,
            "retrieved": retrieved,
            "entities": graph_context.get("nodes", []),
            "relationships": graph_context.get("edges", []),
            "knowledge_gaps": gaps,
            "cross_domain_connections": connections,
            "num_hypotheses": num_hypotheses,
        }

        warnings: list[str] = []
        if use_fast_fallback:
            generated = self._fallback_hypotheses(context, "fast_fallback requested by user")
            warnings = ["Fast fallback mode — deterministic hypotheses returned without calling the AI model."]
        elif len(retrieved) == 0:
            generated = self._fallback_hypotheses(context, "no evidence retrieved")
            warnings = ["No indexed paper chunks found for this query. Upload and process papers first, then generate hypotheses."]
        else:
            try:
                generated = self.gemma.generate_hypothesis(context)
                warnings = []
            except Exception as exc:
                generated = self._fallback_hypotheses(context, str(exc))
                warnings = [f"AI model error ({exc}). Returning deterministic hypotheses from retrieved evidence."]

        valid = [
            item for item in generated.get("hypotheses", [])
            if item.get("confidence", 0) > 0.3 and item.get("supporting_evidence")
        ]
        valid.sort(key=lambda item: item.get("confidence", 0) * item.get("novelty_score", 0), reverse=True)

        stored: list[tuple[Hypothesis, dict]] = []
        for item in valid:
            row = Hypothesis(
                hypothesis_text=item["hypothesis"],
                reasoning=item["reasoning"],
                confidence_score=item["confidence"],
                novelty_score=item["novelty_score"],
                testability=item["testability"],
                supporting_paper_ids=paper_ids or [],
                supporting_evidence=item.get("supporting_evidence", []),
                suggested_experiments=item.get("suggested_experiments", []),
                research_gaps_addressed=item.get("research_gaps_addressed", []),
                cross_domain_insights=[item.get("cross_domain_insight", "")],
                query_context=query,
            )
            db.add(row)
            stored.append((row, item))
        await db.commit()
        for row, item in stored:
            await db.refresh(row)
            item["id"] = row.id

        return {
            "hypotheses": valid,
            "meta_insights": generated.get("meta_insights", {}),
            "warnings": warnings,
        }

    def _retrieve(self, query: str, paper_ids: list[int] | None) -> list[SearchResult]:
        if self.vector_store is None:
            return []
        try:
            if paper_ids:
                merged: list[SearchResult] = []
                for paper_id in paper_ids:
                    merged.extend(self.vector_store.search(query, n_results=20, filter_paper_id=paper_id))
                return sorted(merged, key=lambda item: item.similarity_score, reverse=True)[:20]
            return self.vector_store.search(query, n_results=20)
        except Exception:
            return []

    def _identify_gaps(self, chunks: list[SearchResult], use_fast_fallback: bool = False) -> list[str]:
        joined = " ".join(item.text.lower() for item in chunks[:5])
        fallback: list[str] = []
        if "bias" in joined or "generaliz" in joined:
            fallback.append("Model generalizability across institutions, devices, and patient populations remains under-validated.")
        if "real-time" in joined or "latency" in joined:
            fallback.append("Real-time clinical deployment needs stronger latency and workflow validation.")
        if "federated" in joined or "privacy" in joined:
            fallback.append("Privacy-preserving multi-center training is promising but not yet broadly validated.")
        if "dataset" in joined:
            fallback.append("Dataset diversity and annotation consistency remain limiting factors for reliable translation.")
        if use_fast_fallback or not chunks:
            return fallback[:12] or ["External validation and clinical translation studies remain key gaps."]
        prompt = "Identify up to 12 knowledge gaps from these paper chunks as a JSON object with key 'gaps' (list of strings):\n"
        prompt += "\n\n".join(item.text[:1000] for item in chunks[:10])
        try:
            result = self.gemma.generate_structured(prompt)
            return result.get("gaps", [])[:12]
        except Exception:
            return fallback[:12] or ["Gemma gap detection timed out; using heuristic gaps."]

    def _graph_context(self, query: str) -> dict:
        if not self.graph_builder:
            return {"nodes": [], "edges": []}
        try:
            return self.graph_builder.get_entity_neighborhood(query, 2)
        except Exception:
            return {"nodes": [], "edges": []}

    @staticmethod
    def _fallback_hypotheses(context: dict, error: str) -> dict:
        retrieved: list[SearchResult] = context.get("retrieved", [])
        gaps = context.get("knowledge_gaps", []) or [
            "External validation and clinical translation studies remain key research gaps."
        ]
        query = context.get("query", "the target research area")
        count = max(1, int(context.get("num_hypotheses", 1)))
        evidence = []
        for item in retrieved[:3]:
            evidence.append({
                "paper_title": item.metadata.get("title", ""),
                "section": item.metadata.get("section", ""),
                "excerpt": " ".join(item.text.split()[:45]),
                "relevance": "High-similarity evidence retrieved for this research query.",
            })
        base = {
            "reasoning": (
                "The retrieved literature emphasises model performance, dataset quality, and clinical translation constraints. "
                "A focused validation study can test whether methods that appear strong in curated datasets remain reliable under real deployment conditions. "
                "The hypothesis is conservative because it is grounded in recurring limitations found in the uploaded papers."
            ),
            "supporting_evidence": evidence,
            "confidence": 0.62,
            "novelty_score": 0.58,
            "testability": "high",
            "suggested_experiments": [
                "Run external validation on a held-out multi-center dataset.",
                "Measure accuracy, recall, specificity, and latency under realistic clinical workflow constraints.",
            ],
            "falsifiable_conditions": "The hypothesis is weakened if external validation shows no performance or workflow advantage over the baseline.",
            "research_gaps_addressed": gaps[:2],
            "cross_domain_insight": "Combines retrieval evidence about model accuracy with deployment concerns such as bias, privacy, and latency.",
        }
        hypotheses = []
        for idx in range(count):
            item = dict(base)
            item["id"] = idx + 1
            item["hypothesis"] = (
                f"For {query}, models validated with privacy-preserving multi-center data will generalise better to clinical deployment "
                "than models trained and evaluated on single-centre curated datasets."
            )
            hypotheses.append(item)
        return {
            "hypotheses": hypotheses,
            "meta_insights": {
                "dominant_themes": ["generalizability", "dataset bias", "clinical deployment"],
                "most_promising_direction": "Multi-centre validation with deployment-aware metrics is the clearest next step.",
                "critical_missing_experiments": ["Prospective clinical workflow validation with latency and bias reporting."],
                "fallback_reason": error,
            },
        }

    async def explain_hypothesis(self, hypothesis_id: int, db: AsyncSession) -> dict:
        hypothesis = await db.get(Hypothesis, hypothesis_id)
        if not hypothesis:
            return {"error": "Hypothesis not found"}
        prompt = (
            f"Explain this research hypothesis in a JSON object with keys: "
            f"plain_language, technical, citation_trail, confidence_breakdown. "
            f"Hypothesis: {hypothesis.hypothesis_text}"
        )
        try:
            return self.gemma.generate_structured(prompt)
        except Exception:
            return {
                "plain_language": hypothesis.hypothesis_text,
                "technical": hypothesis.reasoning,
                "citation_trail": hypothesis.supporting_evidence,
                "confidence_breakdown": {
                    "score": hypothesis.confidence_score,
                    "why": "Gemma explanation timed out; returning stored reasoning.",
                },
                "warnings": ["Gemma timeout — stored reasoning returned."],
            }
