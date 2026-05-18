from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass
from typing import Any

import re

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.gemma_engine import GemmaEngine
from models.entity import Entity, EntityRelationship, PaperEntity
from models.paper import Chunk, Paper
from retrieval.semantic_search import SemanticSearch
from retrieval.vector_store import SearchResult, VectorStore


@dataclass
class GraphFact:
    source: str
    relationship: str
    target: str
    confidence: float
    evidence: str
    paper_id: int | None
    kind: str = "explicit"


class GraphRAG:
    ENTITY_STOPWORDS = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "based",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "our",
        "paper",
        "section",
        "show",
        "shows",
        "study",
        "table",
        "text",
        "that",
        "the",
        "their",
        "these",
        "this",
        "those",
        "to",
        "using",
        "we",
        "with",
    }

    def __init__(
        self,
        vector_store: VectorStore | None,
        primary_gemma: GemmaEngine | None = None,
        fallback_gemma: GemmaEngine | None = None,
    ) -> None:
        self.vector_store = vector_store
        self.primary_gemma = primary_gemma
        self.fallback_gemma = fallback_gemma

    async def answer(
        self,
        query: str,
        db: AsyncSession,
        paper_ids: list[int] | None = None,
        n_results: int = 8,
        include_graph: bool = True,
        use_gemma: bool = False,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        warnings: list[str] = []
        semantic_results = await self._db_chunk_search(query, db, paper_ids, max(n_results, 8), workspace_id)
        if self.vector_store is not None:
            try:
                vector_results = SemanticSearch(self.vector_store).search(
                    query,
                    paper_ids,
                    max(n_results, 4),
                    workspace_id=workspace_id,
                )
                semantic_results = self._merge_results(vector_results, semantic_results, max(n_results, 8))
            except Exception as exc:
                warnings.append(f"Vector rerank failed; used fast database retrieval. Detail: {exc}")
        if not semantic_results:
            warnings.append("No chunk matches found in the local database or vector index.")
        graph_context = await self._graph_context(query, semantic_results, db, paper_ids, workspace_id) if include_graph else self._empty_graph()
        expanded_results = self._expanded_retrieval(query, semantic_results, graph_context, paper_ids, n_results)
        model_used = "fast-extractive-graphrag"
        answer = self._fast_answer(query, expanded_results, graph_context)
        if use_gemma:
            if not self.primary_gemma:
                warnings.append("Gemma summary requested but no summarizer was configured; returned fast GraphRAG answer.")
                return self._response(answer, model_used, warnings, expanded_results, graph_context, started, n_results)
            model_used = self.primary_gemma.model_name
            try:
                summary = self._summarize_with_gemma(query, answer, expanded_results, graph_context)
                answer = f"### Gemma Summary\n{summary}\n\n{answer}"
                model_used = f"fast-extractive-graphrag + {self.primary_gemma.model_name} summary"
            except Exception as exc:
                warnings.append(f"Gemma summary skipped after timeout/error; fast GraphRAG answer is still valid. Detail: {exc}")
                model_used = "fast-extractive-graphrag"

        return self._response(answer, model_used, warnings, expanded_results, graph_context, started, n_results)

    def _response(
        self,
        answer: str,
        model_used: str,
        warnings: list[str],
        expanded_results: list[SearchResult],
        graph_context: dict[str, Any],
        started: float,
        n_results: int,
    ) -> dict[str, Any]:
        return {
            "answer": answer,
            "model": model_used,
            "warnings": warnings,
            "results": [self._result_payload(item) for item in expanded_results[:n_results]],
            "graph_context": graph_context,
            "query_time_ms": int((time.perf_counter() - started) * 1000),
        }

    async def _db_chunk_search(
        self,
        query: str,
        db: AsyncSession,
        paper_ids: list[int] | None,
        n_results: int,
        workspace_id: str | None = None,
    ) -> list[SearchResult]:
        terms = self._query_terms(query)
        stmt = select(Chunk, Paper).join(Paper, Paper.id == Chunk.paper_id)
        if workspace_id:
            stmt = stmt.where(Paper.workspace_id == workspace_id)
        if paper_ids:
            stmt = stmt.where(Chunk.paper_id.in_(paper_ids))
        stmt = stmt.where(Chunk.importance_score >= 0.4).order_by(Chunk.importance_score.desc()).limit(200)
        rows = (await db.execute(stmt)).all()
        if not terms:
            rows = rows[: max(n_results * 2, 12)]
        scored: list[SearchResult] = []
        avg_dl = sum(len(chunk.content.split()) for chunk, _ in rows) / max(len(rows), 1)
        for chunk, paper in rows:
            bm25 = self._bm25_score(terms, chunk.content, avg_dl)
            if terms and bm25 <= 0:
                continue
            score = (
                0.45 * min(bm25 / max(len(terms), 1), 1.0)
                + 0.40 * float(chunk.importance_score or 0)
                + 0.15 * self._lexical_score(query, chunk.content)
            )
            scored.append(
                SearchResult(
                    id=chunk.chroma_embedding_id or f"db-{chunk.id}",
                    text=chunk.content,
                    metadata={
                        "paper_id": chunk.paper_id,
                        "title": paper.title,
                        "section": chunk.section,
                        "importance_score": chunk.importance_score,
                        "year": paper.publication_year or 0,
                        "authors_str": ", ".join(paper.authors or []),
                        "arxiv_id": paper.arxiv_id or "",
                        "source": "database",
                    },
                    similarity_score=round(score, 4),
                )
            )
        return sorted(scored, key=lambda item: item.similarity_score, reverse=True)[:n_results]

    async def _graph_context(
        self,
        query: str,
        results: list[SearchResult],
        db: AsyncSession,
        paper_ids: list[int] | None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        candidate_paper_ids = paper_ids or self._paper_ids_from_results(results)
        entities = self._filter_entities(await self._candidate_entities(query, candidate_paper_ids, db, workspace_id))
        facts = await self._relationship_facts([entity.id for entity in entities], candidate_paper_ids, db)
        if len(facts) < 4:
            co_mentions = await self._co_mention_facts([entity.id for entity in entities], candidate_paper_ids, db)
            facts = self._merge_facts(facts, co_mentions, 32)
        papers = await self._papers(candidate_paper_ids, db, workspace_id)
        return {
            "entities": [
                {
                    "id": entity.id,
                    "name": entity.name,
                    "type": entity.entity_type,
                    "paper_count": entity.paper_count,
                }
                for entity in entities
            ],
            "relationships": [fact.__dict__ for fact in self._filter_facts(facts)],
            "papers": papers,
        }

    async def _candidate_entities(self, query: str, paper_ids: list[int], db: AsyncSession, workspace_id: str | None = None) -> list[Entity]:
        by_paper: list[Entity] = []
        if paper_ids:
            stmt = (
                select(Entity)
                .join(PaperEntity, PaperEntity.entity_id == Entity.id)
                .where(PaperEntity.paper_id.in_(paper_ids))
                .order_by(PaperEntity.frequency.desc(), Entity.paper_count.desc())
                .limit(24)
            )
            if workspace_id:
                stmt = stmt.where(Entity.workspace_id == workspace_id)
            rows = await db.execute(stmt)
            by_paper = list(rows.scalars().all())

        terms = self._query_terms(query)
        by_name: list[Entity] = []
        if terms:
            stmt = (
                select(Entity)
                .where(or_(*(Entity.normalized_name.ilike(f"%{term}%") for term in terms)))
                .order_by(Entity.paper_count.desc())
                .limit(16)
            )
            name_stmt = select(Entity).where(or_(*(Entity.name.ilike(f"%{term}%") for term in terms))).order_by(Entity.paper_count.desc()).limit(16)
            if workspace_id:
                stmt = stmt.where(Entity.workspace_id == workspace_id)
                name_stmt = name_stmt.where(Entity.workspace_id == workspace_id)
            rows = await db.execute(stmt)
            by_name = list(rows.scalars().all())
            name_rows = await db.execute(name_stmt)
            by_name.extend(list(name_rows.scalars().all()))

        merged: dict[int, Entity] = {}
        for entity in [*by_name, *by_paper]:
            merged[entity.id] = entity
        return list(merged.values())[:32]

    async def _relationship_facts(
        self,
        entity_ids: list[int],
        paper_ids: list[int],
        db: AsyncSession,
    ) -> list[GraphFact]:
        if not entity_ids:
            return []
        filters = [
            or_(
                EntityRelationship.source_entity_id.in_(entity_ids),
                EntityRelationship.target_entity_id.in_(entity_ids),
            )
        ]
        if paper_ids:
            filters.append(EntityRelationship.paper_id.in_(paper_ids))

        rows = await db.execute(
            select(EntityRelationship, Entity.name, EntityRelationship.target_entity_id)
            .join(Entity, Entity.id == EntityRelationship.source_entity_id)
            .where(*filters)
            .order_by(EntityRelationship.confidence.desc())
            .limit(32)
        )
        relationships = rows.all()
        target_ids = {target_id for _, _, target_id in relationships}
        target_names: dict[int, str] = {}
        if target_ids:
            target_rows = await db.execute(select(Entity.id, Entity.name).where(Entity.id.in_(target_ids)))
            target_names = dict(target_rows.all())
        facts = []
        for rel, source_name, target_id in relationships:
            target_name = target_names.get(target_id, str(target_id))
            if not self._valid_entity_name(source_name) or not self._valid_entity_name(target_name):
                continue
            facts.append(
                GraphFact(
                    source=source_name,
                    relationship=rel.relationship_type,
                    target=target_name,
                    confidence=rel.confidence,
                    evidence=rel.evidence_text or "",
                    paper_id=rel.paper_id,
                    kind="explicit",
                )
            )
        return facts

    async def _co_mention_facts(
        self,
        entity_ids: list[int],
        paper_ids: list[int],
        db: AsyncSession,
    ) -> list[GraphFact]:
        if not entity_ids or not paper_ids:
            return []
        rows = await db.execute(
            select(PaperEntity.paper_id, Entity.id, Entity.name, Entity.entity_type, PaperEntity.frequency)
            .join(Entity, Entity.id == PaperEntity.entity_id)
            .where(PaperEntity.entity_id.in_(entity_ids), PaperEntity.paper_id.in_(paper_ids))
            .order_by(PaperEntity.frequency.desc())
            .limit(240)
        )
        by_paper: dict[int, list[tuple[int, str, str, int]]] = {}
        for paper_id, entity_id, name, entity_type, frequency in rows.all():
            by_paper.setdefault(int(paper_id), []).append((int(entity_id), name, entity_type, int(frequency or 1)))

        facts: list[GraphFact] = []
        seen: set[tuple[str, str, int]] = set()
        for paper_id, paper_entities in by_paper.items():
            valid_entities = [item for item in paper_entities if self._valid_entity_name(item[1])]
            ranked = sorted(valid_entities, key=lambda item: (self._entity_strength(item[1], item[2]), item[3]), reverse=True)[:8]
            for idx, left in enumerate(ranked):
                for right in ranked[idx + 1 : idx + 4]:
                    if self._too_similar_entities(left[1], right[1]):
                        continue
                    key = tuple(sorted([left[1], right[1]])) + (paper_id,)
                    if key in seen:
                        continue
                    seen.add(key)
                    confidence = min(
                        0.92,
                        0.35
                        + (left[3] + right[3]) * 0.035
                        + self._entity_strength(left[1], left[2]) * 0.04
                        + self._entity_strength(right[1], right[2]) * 0.04,
                    )
                    facts.append(
                        GraphFact(
                            source=left[1],
                            relationship="co_mentioned_with",
                            target=right[1],
                            confidence=confidence,
                            evidence=f"Fast local graph: both entities occur in paper {paper_id}.",
                            paper_id=paper_id,
                            kind="co_mention",
                        )
                    )
                    if len(facts) >= 32:
                        return facts
        return self._filter_facts(facts)

    async def _papers(self, paper_ids: list[int], db: AsyncSession, workspace_id: str | None = None) -> list[dict[str, Any]]:
        if not paper_ids:
            return []
        stmt = select(Paper).where(Paper.id.in_(paper_ids)).limit(20)
        if workspace_id:
            stmt = stmt.where(Paper.workspace_id == workspace_id)
        rows = await db.execute(stmt)
        return [
            {
                "id": paper.id,
                "title": paper.title,
                "year": paper.publication_year,
                "arxiv_id": paper.arxiv_id,
            }
            for paper in rows.scalars().all()
        ]

    def _expanded_retrieval(
        self,
        query: str,
        seed_results: list[SearchResult],
        graph_context: dict[str, Any],
        paper_ids: list[int] | None,
        n_results: int,
    ) -> list[SearchResult]:
        entity_terms = {
            term.lower()
            for entity in graph_context.get("entities", [])[:10]
            for term in entity["name"].split()
            if len(term) >= 4 and term.lower() not in self.ENTITY_STOPWORDS
        }
        if not entity_terms:
            return seed_results[:n_results]
        boosted = []
        for item in seed_results:
            content = item.text.lower()
            bonus = min(0.08, sum(0.015 for term in entity_terms if term in content))
            boosted.append(SearchResult(item.id, item.text, item.metadata, item.similarity_score + bonus))
        return sorted(boosted, key=lambda item: item.similarity_score, reverse=True)[:n_results]

    def _summarize_with_gemma(
        self,
        query: str,
        fast_answer: str,
        results: list[SearchResult],
        graph_context: dict[str, Any],
    ) -> str:
        evidence = "\n".join(
            f"- paper_id={item.metadata.get('paper_id')}, title={item.metadata.get('title', '')}: {self._best_excerpt(query, item.text, 28)}"
            for item in results[:4]
        )
        relationships = graph_context.get("relationships", [])[:6]
        prompt = f"""
Summarize this GraphRAG evidence for a scientist.
Return exactly these sections with 1-2 concrete bullets each:
Key finding:
Evidence:
Graph signal:
Limitations:
Next experiment:

Rules:
- Use only the supplied evidence.
- Do not mention generic tokens as concepts.
- Every bullet must contain a concrete method, dataset, metric, disease, paper, or relationship.
- Include uncertainty if evidence is weak.

Question: {query}

Fast answer:
{fast_answer[:1800]}

Evidence:
{evidence}

Graph relationships:
{relationships}
"""
        return self.primary_gemma.generate(prompt, temperature=0.1, num_predict=220, num_ctx=1536).strip()

    @staticmethod
    def _build_prompt(query: str, results: list[SearchResult], graph_context: dict[str, Any]) -> str:
        chunks = "\n\n".join(
            (
                f"[Chunk {idx} | paper_id={item.metadata.get('paper_id')} | "
                f"title={item.metadata.get('title', '')} | section={item.metadata.get('section', '')} | "
                f"similarity={item.similarity_score:.3f}]\n{item.text[:1400]}"
            )
            for idx, item in enumerate(results, 1)
        )
        entities = graph_context.get("entities", [])
        relationships = graph_context.get("relationships", [])
        return f"""
You are a scientific GraphRAG assistant using Gemma.

Question:
{query}

Retrieved paper chunks:
{chunks}

Knowledge graph entities:
{entities}

Knowledge graph relationships:
{relationships}

Answer requirements:
- Use only the retrieved chunks and graph context.
- Cite evidence inline with paper_id/title or chunk numbers.
- Explain how graph relationships changed or strengthened the answer.
- If evidence is weak, say what is missing.
- Keep the answer concise and research-focused.
"""

    @staticmethod
    def _fast_answer(query: str, results: list[SearchResult], graph_context: dict[str, Any]) -> str:
        if not results:
            return (
                f"No indexed evidence was found for '{query}'. Upload and process papers first, then retry GraphRAG."
            )
        evidence_lines = []
        top_sentences = GraphRAG._best_sentences(query, results)
        for idx, item in enumerate(results[:5], 1):
            title = item.metadata.get("title") or f"paper {item.metadata.get('paper_id', 'unknown')}"
            section = item.metadata.get("section") or "unknown section"
            excerpt = GraphRAG._best_excerpt(query, item.text, 42)
            evidence_lines.append(
                f"{idx}. {title} ({section}, paper_id={item.metadata.get('paper_id')}, score={item.similarity_score:.2f}): {excerpt}"
            )

        entities = [item for item in graph_context.get("entities", []) if GraphRAG._valid_entity_name(item.get("name", ""))][:8]
        relationships = graph_context.get("relationships", [])[:6]
        entity_text = ", ".join(f"{item['name']} [{item['type']}]" for item in entities) or "No graph entities matched yet."
        if relationships:
            relation_text = "\n".join(
                (
                    f"- {rel['source']} --{rel['relationship']}--> {rel['target']} "
                    f"(confidence {float(rel.get('confidence') or 0):.2f}, paper_id={rel.get('paper_id')})"
                )
                for rel in relationships
            )
        else:
            relation_text = "- No explicit graph relationships matched; answer is based on retrieved chunks."

        direct_answer = " ".join(top_sentences[:3]) if top_sentences else GraphRAG._best_excerpt(query, results[0].text, 70)
        key_methods = [item["name"] for item in entities if item.get("type") in {"METHOD", "CONCEPT"}][:4]
        key_targets = [item["name"] for item in entities if item.get("type") in {"DISEASE", "PATHWAY", "CHEMICAL", "GENE", "PROTEIN"}][:4]
        relationship_point = (
            f"{relationships[0]['source']} is connected to {relationships[0]['target']} through {relationships[0]['relationship']} "
            f"in paper {relationships[0].get('paper_id')}."
            if relationships
            else "No high-confidence entity relationship was found; rely on retrieved text until more papers are processed."
        )
        confidence = "high" if len(results) >= 5 and relationships else "moderate" if len(results) >= 3 else "low"
        return (
            f"### Key Finding\n{direct_answer}\n\n"
            f"### Evidence Strength\n{confidence.capitalize()} support from {len(results)} retrieved chunks and "
            f"{len(relationships)} validated graph relationship(s).\n\n"
            f"### Important Concepts\n"
            f"- Methods/concepts: {', '.join(key_methods) if key_methods else 'No strong method/concept entities found.'}\n"
            f"- Targets/domains: {', '.join(key_targets) if key_targets else 'No strong disease/pathway/target entities found.'}\n"
            f"- Graph signal: {relationship_point}\n\n"
            "### Best Evidence\n"
            + "\n".join(evidence_lines)
            + "\n\n### Graph Grounding\n"
            + f"Key entities: {entity_text}\n"
            + relation_text
            + "\n\n### What To Check Next\n"
            "- Inspect the highest-scoring chunk before trusting the conclusion.\n"
            "- Prefer claims supported by both retrieved text and graph relationships.\n"
            "- If graph relationships are weak, compare against the source chunks before treating the link as a discovery."
        )

    @staticmethod
    def _paper_ids_from_results(results: list[SearchResult]) -> list[int]:
        ids: list[int] = []
        for item in results:
            paper_id = item.metadata.get("paper_id")
            if paper_id is not None and int(paper_id) not in ids:
                ids.append(int(paper_id))
        return ids

    @staticmethod
    def _query_terms(query: str) -> list[str]:
        stopwords = {
            "and", "the", "for", "with", "from", "that", "this", "into", "using", "about", "what", "does", "show",
            "study", "paper", "method", "result", "data", "model", "approach", "analysis", "also", "however",
        }
        terms = [term.lower().strip(" ,.;:()[]{}?") for term in re.split(r"\W+", query)]
        return [term for term in terms if len(term) >= 4 and term not in stopwords][:8]

    @staticmethod
    def _bm25_score(query_terms: list[str], text: str, avg_dl: float) -> float:
        if not query_terms:
            return 0.4
        k1, b = 1.5, 0.75
        words = re.findall(r"\b[a-z0-9-]+\b", text.lower())
        dl = max(len(words), 1)
        counts = Counter(words)
        score = 0.0
        for term in query_terms:
            tf = counts.get(term, 0)
            if tf:
                score += tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / max(avg_dl, 1)))
        return score

    @classmethod
    def _valid_entity_name(cls, name: str) -> bool:
        cleaned = " ".join(str(name or "").strip().split())
        lowered = cleaned.lower()
        if not cleaned or lowered in cls.ENTITY_STOPWORDS:
            return False
        if len(cleaned) < 3:
            return False
        if len(cleaned) > 90:
            return False
        if re.fullmatch(r"[\W\d_]+", cleaned):
            return False
        words = re.findall(r"[A-Za-z][A-Za-z0-9-]*", cleaned)
        if not words:
            return False
        if len(words) == 1:
            word = words[0]
            if word.lower() in cls.ENTITY_STOPWORDS:
                return False
            if len(word) < 4 and not word.isupper():
                return False
            if word.istitle() and word.lower() in {"figure", "result", "method", "data", "model", "task"}:
                return False
        return True

    @classmethod
    def _entity_strength(cls, name: str, entity_type: str | None = None) -> float:
        cleaned = " ".join(str(name or "").split())
        words = re.findall(r"[A-Za-z][A-Za-z0-9-]*", cleaned)
        if not cls._valid_entity_name(cleaned):
            return 0.0
        score = 1.0
        if len(words) >= 2:
            score += 1.0
        if any(word.isupper() and len(word) >= 2 for word in words):
            score += 0.7
        if entity_type in {"METHOD", "DISEASE", "PATHWAY", "CHEMICAL", "GENE", "PROTEIN"}:
            score += 0.8
        if cleaned.lower() in cls.ENTITY_STOPWORDS:
            score -= 2.0
        return max(0.0, score)

    @classmethod
    def _filter_entities(cls, entities: list[Entity]) -> list[Entity]:
        unique: dict[str, Entity] = {}
        for entity in entities:
            if not cls._valid_entity_name(entity.name):
                continue
            key = entity.name.lower()
            existing = unique.get(key)
            if existing is None or cls._entity_strength(entity.name, entity.entity_type) > cls._entity_strength(existing.name, existing.entity_type):
                unique[key] = entity
        return sorted(
            unique.values(),
            key=lambda item: (cls._entity_strength(item.name, item.entity_type), item.paper_count or 0),
            reverse=True,
        )[:24]

    @classmethod
    def _filter_facts(cls, facts: list[GraphFact]) -> list[GraphFact]:
        filtered = [
            fact
            for fact in facts
            if cls._valid_entity_name(fact.source)
            and cls._valid_entity_name(fact.target)
            and not cls._too_similar_entities(fact.source, fact.target)
        ]
        return sorted(filtered, key=lambda item: (item.confidence, cls._entity_strength(item.source) + cls._entity_strength(item.target)), reverse=True)[:32]

    @staticmethod
    def _too_similar_entities(left: str, right: str) -> bool:
        a = str(left).lower().strip()
        b = str(right).lower().strip()
        if a == b:
            return True
        if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
            return True
        return False

    @staticmethod
    def _lexical_score(query: str, text: str) -> float:
        terms = GraphRAG._query_terms(query)
        if not terms:
            return 0.4
        lowered = text.lower()
        hits = sum(lowered.count(term) for term in terms)
        coverage = sum(1 for term in terms if term in lowered) / len(terms)
        return min(1.0, 0.25 + coverage * 0.55 + min(hits, 10) * 0.03)

    @staticmethod
    def _best_sentences(query: str, results: list[SearchResult]) -> list[str]:
        candidates: list[tuple[float, str]] = []
        for item in results[:6]:
            for sentence in re.split(r"(?<=[.!?])\s+", item.text):
                sentence = " ".join(sentence.split())
                if 45 <= len(sentence) <= 320:
                    candidates.append((GraphRAG._lexical_score(query, sentence), sentence))
        return [sentence for _, sentence in sorted(candidates, key=lambda pair: pair[0], reverse=True)[:5]]

    @staticmethod
    def _best_excerpt(query: str, text: str, max_words: int) -> str:
        sentences = GraphRAG._best_sentences(query, [SearchResult("excerpt", text, {}, 0)])
        source = sentences[0] if sentences else text
        return " ".join(source.split()[:max_words])

    @staticmethod
    def _merge_results(first: list[SearchResult], second: list[SearchResult], limit: int) -> list[SearchResult]:
        merged: dict[str, SearchResult] = {}
        for item in [*first, *second]:
            existing = merged.get(item.id)
            if existing is None or item.similarity_score > existing.similarity_score:
                merged[item.id] = item
        return sorted(merged.values(), key=lambda item: item.similarity_score, reverse=True)[:limit]

    @staticmethod
    def _merge_facts(first: list[GraphFact], second: list[GraphFact], limit: int) -> list[GraphFact]:
        merged: dict[tuple[str, str, str, int | None], GraphFact] = {}
        for item in [*first, *second]:
            key = (item.source, item.relationship, item.target, item.paper_id)
            existing = merged.get(key)
            if existing is None or item.confidence > existing.confidence:
                merged[key] = item
        return sorted(merged.values(), key=lambda item: item.confidence, reverse=True)[:limit]

    @staticmethod
    def _result_payload(item: SearchResult) -> dict[str, Any]:
        return {
            "id": item.id,
            "text": item.text,
            "metadata": item.metadata,
            "similarity_score": item.similarity_score,
        }

    @staticmethod
    def _empty_graph() -> dict[str, list[Any]]:
        return {"entities": [], "relationships": [], "papers": []}
