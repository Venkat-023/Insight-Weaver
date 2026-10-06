"""Retrieval-Augmented Generation (GraphRAG) evaluation and grounding metrics.

Provides scoring algorithms for evaluating the quality, factual grounding,
and diversity of evidence retrieved from scientific paper collections.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


def _tokenize_text(text: str) -> list[str]:
    """Helper to tokenize scientific text into lowercased alphanumeric words."""
    if not text:
        return []
    return [w.lower() for w in re.findall(r"\b[a-zA-Z0-9_\-]{2,}\b", text)]


def compute_context_relevance_score(retrieved_chunks: list[str], query: str) -> float:
    """Calculate the relevance score of retrieved chunks against the search query.

    Uses term overlap and query keyword coverage to evaluate whether retrieved
    context contains the necessary vocabulary to address the user's research question.

    Args:
        retrieved_chunks: List of chunk text passages returned from vector/graph search.
        query: User's scientific question or hypothesis prompt.

    Returns:
        Score between 0.0 and 1.0 indicating retrieval relevance.
    """
    if not retrieved_chunks or not query:
        return 0.0

    query_tokens = set(_tokenize_text(query))
    if not query_tokens:
        return 0.0

    # Stopwords specific to scientific inquiry
    academic_stopwords = {"what", "which", "where", "how", "does", "effect", "impact", "paper", "show"}
    informative_tokens = query_tokens - academic_stopwords
    target_tokens = informative_tokens or query_tokens

    covered_tokens: set[str] = set()
    total_chunk_len = 0

    for chunk in retrieved_chunks:
        chunk_tokens = set(_tokenize_text(chunk))
        covered_tokens.update(target_tokens.intersection(chunk_tokens))
        total_chunk_len += len(chunk_tokens)

    if total_chunk_len == 0:
        return 0.0

    coverage_ratio = len(covered_tokens) / len(target_tokens)
    return round(min(1.0, max(0.0, coverage_ratio)), 4)


def calculate_citation_grounding_score(answer: str, chunk_texts: list[str]) -> float:
    """Evaluate how well each sentence in the synthesized answer is grounded in evidence chunks.

    Args:
        answer: Synthesized response from Gemma or GraphRAG reasoner.
        chunk_texts: List of evidence chunk text strings used as context.

    Returns:
        Float ratio (0.0 to 1.0) of answer sentences with sufficient evidence support.
    """
    if not answer or not chunk_texts:
        return 0.0

    all_evidence_words = set()
    for chunk in chunk_texts:
        all_evidence_words.update(_tokenize_text(chunk))

    sentences = [s.strip() for s in re.split(r"[.!?]\s+", answer) if len(s.strip()) > 15]
    if not sentences:
        return 0.0

    grounded_count = 0
    for sentence in sentences:
        words = _tokenize_text(sentence)
        if not words:
            continue
        overlap = sum(1 for w in words if w in all_evidence_words)
        ratio = overlap / len(words)
        if ratio >= 0.40:  # Threshold for factual evidence grounding
            grounded_count += 1

    return round(grounded_count / len(sentences), 4)


def evaluate_chunk_diversity(chunks: list[dict[str, Any]]) -> float:
    """Measure the distribution diversity across sections and source papers.

    Higher scores indicate chunks represent diverse evidence across multiple
    sections (e.g. methods, results, discussion) rather than repetitive passages.

    Args:
        chunks: List of retrieved chunk dictionaries containing 'paper_id' and 'section'.

    Returns:
        Diversity score normalized between 0.0 and 1.0.
    """
    if not chunks:
        return 0.0

    if len(chunks) == 1:
        return 1.0

    sections = [c.get("section", "unknown") for c in chunks]
    paper_ids = [c.get("paper_id", 0) for c in chunks]

    unique_sections = len(set(sections))
    unique_papers = len(set(paper_ids))

    max_possible_sections = min(len(chunks), 5)
    max_possible_papers = len(chunks)

    sec_score = unique_sections / max_possible_sections
    paper_score = unique_papers / max_possible_papers

    return round(0.5 * sec_score + 0.5 * paper_score, 4)


# ==============================================================================
# UNUSED FUNCTIONS / DEAD CODE CANDIDATES FOR DEAD CODE ANALYSIS TESTING
# ==============================================================================

def _compute_ngram_jaccard_similarity(text_a: str, text_b: str, n: int = 3) -> float:
    """[UNUSED] Internal character n-gram Jaccard index similarity.

    Dead code note: Private utility defined during early prototyping for fuzzy
    chunk deduplication, but never invoked by any public or private method.
    """
    if not text_a or not text_b or n <= 0:
        return 0.0

    def get_ngrams(s: str) -> set[str]:
        cleaned = re.sub(r"\s+", " ", s.lower()).strip()
        return {cleaned[i : i + n] for i in range(len(cleaned) - n + 1)}

    grams_a = get_ngrams(text_a)
    grams_b = get_ngrams(text_b)

    if not grams_a or not grams_b:
        return 0.0

    intersection = len(grams_a.intersection(grams_b))
    union = len(grams_a.union(grams_b))
    return intersection / union if union > 0 else 0.0


def legacy_calculate_bleu_score(
    reference: str,
    hypothesis: str,
    max_n: int = 4,
) -> float:
    """[UNUSED] Calculate exact n-gram BLEU score between reference and generated text.

    Dead code note: Standalone legacy evaluation metric. Insight Weaver uses
    semantic GraphRAG grounding and LLM verification rather than surface BLEU,
    so this function is never imported or called anywhere.
    """
    ref_tokens = _tokenize_text(reference)
    hyp_tokens = _tokenize_text(hypothesis)

    if not hyp_tokens or not ref_tokens:
        return 0.0

    weights = [1.0 / max_n] * max_n
    precisions = []

    for i in range(1, max_n + 1):
        ref_ngrams = Counter(tuple(ref_tokens[k : k + i]) for k in range(len(ref_tokens) - i + 1))
        hyp_ngrams = Counter(tuple(hyp_tokens[k : k + i]) for k in range(len(hyp_tokens) - i + 1))

        if not hyp_ngrams:
            precisions.append(0.0)
            continue

        clipped = sum(min(count, ref_ngrams.get(ng, 0)) for ng, count in hyp_ngrams.items())
        total = sum(hyp_ngrams.values())
        precisions.append((clipped + 1e-9) / total)

    log_sum = sum(w * math.log(p) for w, p in zip(weights, precisions) if p > 0)
    brevity_penalty = min(1.0, math.exp(1 - len(ref_tokens) / len(hyp_tokens))) if hyp_tokens else 0.0

    return round(brevity_penalty * math.exp(log_sum), 4)


def estimate_retrieval_latency_budget(
    target_ms: float,
    chunk_count: int,
    per_chunk_ms: float = 12.5,
) -> dict[str, Any]:
    """[UNUSED] Estimate latency budget allocation for Chroma vector search and Graph query.

    Dead code note: Theoretical sizing helper that was never hooked up to production
    configuration or performance monitoring tasks.
    """
    expected_fetch_time = chunk_count * per_chunk_ms
    remaining_time = target_ms - expected_fetch_time
    is_feasible = remaining_time >= 0

    return {
        "target_ms": target_ms,
        "chunk_count": chunk_count,
        "expected_fetch_time": expected_fetch_time,
        "remaining_ms": max(0.0, remaining_time),
        "is_feasible": is_feasible,
    }


def dummy_compute_cosine_mock(vec_a: list[float], vec_b: list[float]) -> float:
    """[UNUSED DUMMY] Mock calculation for vector cosine similarity without numpy.

    Dead code target: Pure dummy function never imported or called.
    """
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    return round(dot / (norm_a * norm_b), 4) if norm_a and norm_b else 0.0


def dummy_log_metric_telemetry(metric_name: str, score: float) -> dict[str, Any]:
    """[UNUSED DUMMY] Stub for logging telemetry metrics to remote service.

    Dead code target: Dummy stub never called anywhere in the project.
    """
    return {"metric": metric_name, "score": score, "logged": True}

