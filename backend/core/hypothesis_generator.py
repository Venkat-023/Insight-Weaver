from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.gemma_engine import GemmaEngine
from graph.graph_builder import KnowledgeGraphBuilder
from models.entity import Entity, PaperEntity
from models.hypothesis import Hypothesis
from models.paper import Chunk, Paper
from reasoning.cross_paper_reasoner import CrossPaperReasoner
from retrieval.vector_store import SearchResult, VectorStore
from preprocessing.cleaner import ScientificTextCleaner


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
        workspace_id: str = "legacy",
    ) -> dict:
        retrieved = self._retrieve(query, paper_ids, workspace_id)
        if not retrieved:
            retrieved = await self._db_retrieve(query, db, paper_ids, workspace_id)
        top_entities = await self._entities_for_papers(db, paper_ids, workspace_id)
        gaps = self._identify_gaps(retrieved, use_fast_fallback)

        # Cross-paper connections only when not in fast mode and vector store available
        connections: list[dict] = []
        if paper_ids and not use_fast_fallback and self.vector_store is not None:
            for paper_id in paper_ids[:3]:
                try:
                    raw = await self.cross_paper_reasoner.find_unexplored_connections(paper_id, db, workspace_id)
                    connections.extend([item.__dict__ for item in raw])
                except Exception:
                    pass

        graph_context = self._graph_context(query)
        chunks_text = self._build_gemma_context_for_hypothesis(retrieved, top_entities, gaps, query)
        context = {
            "query": query,
            "chunks_text": chunks_text,
            "retrieved": retrieved,
            "entities": top_entities or graph_context.get("nodes", []),
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
                workspace_id=workspace_id,
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

    def _retrieve(self, query: str, paper_ids: list[int] | None, workspace_id: str = "legacy") -> list[SearchResult]:
        if self.vector_store is None:
            return []
        try:
            if paper_ids:
                merged: list[SearchResult] = []
                for paper_id in paper_ids:
                    merged.extend(self.vector_store.search(query, n_results=20, filter_paper_id=paper_id, workspace_id=workspace_id))
                return sorted(merged, key=lambda item: item.similarity_score, reverse=True)[:20]
            return self.vector_store.search(query, n_results=20, workspace_id=workspace_id)
        except Exception:
            return []

    async def _db_retrieve(
        self,
        query: str,
        db: AsyncSession,
        paper_ids: list[int] | None,
        workspace_id: str,
    ) -> list[SearchResult]:
        terms = [term for term in query.lower().split() if len(term) >= 4]
        stmt = select(Chunk, Paper).join(Paper, Paper.id == Chunk.paper_id).where(Paper.workspace_id == workspace_id)
        if paper_ids:
            stmt = stmt.where(Chunk.paper_id.in_(paper_ids))
        stmt = stmt.order_by(Chunk.importance_score.desc()).limit(40)
        rows = (await db.execute(stmt)).all()
        scored: list[SearchResult] = []
        for chunk, paper in rows:
            lowered = chunk.content.lower()
            coverage = sum(1 for term in terms if term in lowered) / max(len(terms), 1)
            score = min(1.0, 0.35 + coverage * 0.45 + float(chunk.importance_score or 0) * 0.2)
            scored.append(
                SearchResult(
                    id=chunk.chroma_embedding_id or f"db-{chunk.id}",
                    text=chunk.content,
                    metadata={
                        "paper_id": chunk.paper_id,
                        "title": paper.title,
                        "section": chunk.section,
                        "importance_score": chunk.importance_score,
                        "workspace_id": workspace_id,
                    },
                    similarity_score=round(score, 4),
                )
            )
        return sorted(scored, key=lambda item: item.similarity_score, reverse=True)[:20]

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

    async def _entities_for_papers(self, db: AsyncSession, paper_ids: list[int] | None, workspace_id: str) -> dict[str, list[str]]:
        if not paper_ids:
            return {}
        rows = await db.execute(
            select(Entity.entity_type, Entity.name, PaperEntity.frequency)
            .join(PaperEntity, PaperEntity.entity_id == Entity.id)
            .where(PaperEntity.paper_id.in_(paper_ids), Entity.workspace_id == workspace_id)
            .order_by(PaperEntity.frequency.desc(), Entity.paper_count.desc())
            .limit(80)
        )
        grouped: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for entity_type, name, frequency in rows.all():
            grouped[entity_type].append((name, int(frequency or 1)))
        return {
            entity_type: [name for name, _ in sorted(items, key=lambda item: (-item[1], item[0].lower()))[:8]]
            for entity_type, items in grouped.items()
        }

    def _graph_context(self, query: str) -> dict:
        if not self.graph_builder:
            return {"nodes": [], "edges": []}
        try:
            return self.graph_builder.get_entity_neighborhood(query, 2)
        except Exception:
            return {"nodes": [], "edges": []}

    @staticmethod
    def _build_gemma_context_for_hypothesis(
        chunks: list[SearchResult],
        entities: dict[str, list[str]],
        gaps: list[str],
        query: str,
    ) -> str:
        cleaner = ScientificTextCleaner()
        parts = [f"RESEARCH QUERY: {query}\n", "=== RETRIEVED EVIDENCE FROM PAPERS ==="]
        for item in chunks[:6]:
            text = cleaner.clean(item.text, mode="aggressive")[:350]
            title = str(item.metadata.get("title", "Unknown"))[:50]
            section = item.metadata.get("section", "")
            parts.append(f'[Paper: "{title}" | Section: {section} | Relevance: {item.similarity_score:.3f}]\n{text}')
        if entities:
            parts.append("\n=== KEY ENTITIES FOUND ===")
            for entity_type, names in entities.items():
                if names:
                    parts.append(f"{entity_type}: {', '.join(names[:5])}")
        if gaps:
            parts.append("\n=== RESEARCH GAPS IDENTIFIED ===")
            parts.extend(f"- {gap}" for gap in gaps[:5])
        return "\n".join(parts)[:2200]

    @staticmethod
    def _fallback_hypotheses(context: dict, error: str) -> dict:
        retrieved: list[SearchResult] = context.get("retrieved", [])
        entities = context.get("entities", {}) if isinstance(context.get("entities"), dict) else {}
        gaps = context.get("knowledge_gaps", []) or ["Evidence-specific validation remains a key research gap."]
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
        evidence_sentences: list[str] = []
        for item in retrieved[:4]:
            for sentence in item.text.split(". "):
                if len(sentence) > 60 and any(
                    keyword in sentence.lower()
                    for keyword in ["significant", "improve", "novel", "outperform", "demonstrate", "suggest"]
                ):
                    evidence_sentences.append(sentence.strip())
                    break

        diseases = entities.get("DISEASE", [])
        methods = entities.get("METHOD", [])
        proteins = entities.get("PROTEIN", []) or entities.get("GENE", [])
        chemicals = entities.get("CHEMICAL", [])
        datasets = entities.get("DATASET", [])
        hypotheses: list[dict] = []

        if diseases and methods:
            hypotheses.append({
                "hypothesis": (
                    f"Applying {methods[0]} to larger multi-institutional cohorts of {diseases[0]} patients may improve "
                    "generalization beyond the populations studied in the uploaded literature."
                ),
                "reasoning": (
                    f"The retrieved papers connect {methods[0]} with {diseases[0]}, but the evidence still needs broader validation. "
                    "A multi-site evaluation directly tests whether the observed signal is robust across acquisition settings and patient populations."
                ),
                "supporting_evidence": evidence or [{"excerpt": evidence_sentences[0] if evidence_sentences else f"{methods[0]} and {diseases[0]} were extracted from the processed papers.", "relevance": "entity-grounded"}],
                "confidence": 0.72,
                "novelty_score": 0.65,
                "testability": "high",
                "suggested_experiments": [
                    f"Collect {diseases[0]} data from at least three independent sites.",
                    f"Evaluate {methods[0]} against the strongest baseline with confidence intervals.",
                ],
                "falsifiable_conditions": "The hypothesis is weakened if external cohorts show no improvement over simpler baselines.",
                "research_gaps_addressed": gaps[:2],
                "cross_domain_insight": f"Links a method entity ({methods[0]}) with a disease target ({diseases[0]}).",
            })

        if proteins and chemicals:
            hypotheses.append({
                "hypothesis": (
                    f"The interaction between {proteins[0]} and {chemicals[0]} may reveal a testable intervention path when combined "
                    "with existing approved therapies."
                ),
                "reasoning": (
                    f"The graph and retrieved evidence surface {proteins[0]} and {chemicals[0]} together, suggesting a mechanistic relationship "
                    "that can be tested under controlled perturbation."
                ),
                "supporting_evidence": evidence or [{"excerpt": evidence_sentences[0] if evidence_sentences else f"{proteins[0]} and {chemicals[0]} were extracted from the processed papers.", "relevance": "entity-grounded"}],
                "confidence": 0.68,
                "novelty_score": 0.8,
                "testability": "medium",
                "suggested_experiments": [
                    f"Measure {proteins[0]} activity after {chemicals[0]} exposure across dose levels.",
                    "Run combination-response analysis against a standard therapy comparator.",
                ],
                "falsifiable_conditions": "The hypothesis is weakened if perturbation does not change the proposed target activity.",
                "research_gaps_addressed": gaps[:2],
                "cross_domain_insight": "Combines molecular target evidence with intervention design.",
            })

        if methods and datasets:
            hypotheses.append({
                "hypothesis": (
                    f"Training {methods[0]} on a privacy-preserving federated version of {datasets[0]} could retain competitive performance "
                    "while reducing centralized data exposure."
                ),
                "reasoning": (
                    f"The papers use {methods[0]} and reference {datasets[0]}, making privacy-preserving replication a concrete next experiment "
                    "rather than a generic deployment claim."
                ),
                "supporting_evidence": evidence or [{"excerpt": f"{methods[0]} and {datasets[0]} were identified in the uploaded evidence.", "relevance": "entity-grounded"}],
                "confidence": 0.7,
                "novelty_score": 0.72,
                "testability": "high",
                "suggested_experiments": [
                    f"Split {datasets[0]} into simulated institutions and train {methods[0]} federated baselines.",
                    "Compare central, federated, and differentially-private variants on the same metrics.",
                ],
                "falsifiable_conditions": "The hypothesis is weakened if federated training materially degrades all target metrics.",
                "research_gaps_addressed": gaps[:2],
                "cross_domain_insight": "Connects model evaluation with privacy-preserving deployment.",
            })

        if not hypotheses and evidence_sentences:
            hypotheses.append({
                "hypothesis": (
                    f"For {query}, the reported finding that {evidence_sentences[0][:140]} may hold under a broader untested condition "
                    "that can be validated experimentally."
                ),
                "reasoning": "This fallback is derived from a concrete retrieved sentence instead of a generic recommendation.",
                "supporting_evidence": [{"excerpt": evidence_sentences[0], "relevance": "direct"}],
                "confidence": 0.55,
                "novelty_score": 0.6,
                "testability": "medium",
                "suggested_experiments": ["Design a controlled extension study around the retrieved claim."],
                "falsifiable_conditions": "The hypothesis is weakened if the effect disappears under the extended condition.",
                "research_gaps_addressed": gaps[:2],
                "cross_domain_insight": "Uses retrieved evidence as the hypothesis anchor.",
            })

        while len(hypotheses) < count:
            anchor = ", ".join([*(methods[:1]), *(diseases[:1]), *(proteins[:1]), *(datasets[:1])]) or query
            hypotheses.append({
                "hypothesis": f"The uploaded evidence around {anchor} suggests a focused validation study could expose a currently untested boundary condition.",
                "reasoning": "This is grounded in the strongest extracted entities and retrieved evidence available for the current workspace.",
                "supporting_evidence": evidence or [{"excerpt": evidence_sentences[0] if evidence_sentences else f"Evidence retrieved for {query}.", "relevance": "workspace evidence"}],
                "confidence": 0.52,
                "novelty_score": 0.55,
                "testability": "medium",
                "suggested_experiments": ["Run a controlled validation over the top extracted entity or method."],
                "falsifiable_conditions": "The hypothesis is weakened if validation shows no measurable difference.",
                "research_gaps_addressed": gaps[:2],
                "cross_domain_insight": "Generated from current retrieved evidence rather than a global template.",
            })
            if not retrieved and not entities:
                break
        for idx, item in enumerate(hypotheses[:count], 1):
            item["id"] = idx
        return {
            "hypotheses": hypotheses[:count],
            "meta_insights": {
                "dominant_themes": [name for names in entities.values() for name in names[:1]][:4],
                "most_promising_direction": hypotheses[0]["hypothesis"] if hypotheses else "Upload papers to generate evidence-grounded hypotheses.",
                "critical_missing_experiments": hypotheses[0].get("suggested_experiments", []) if hypotheses else [],
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
