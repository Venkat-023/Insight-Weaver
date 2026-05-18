import re
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from ingestion.pdf_parser import PaperRawData
from preprocessing.cleaner import ScientificTextCleaner
from preprocessing.splitter import ScientificSentenceSplitter


@dataclass
class Chunk:
    section: str
    sub_index: int
    content: str
    importance_score: float
    word_count: int


class SemanticChunker:
    MAX_CHUNK_TOKENS = 400
    MIN_CHUNK_WORDS = 40
    OVERLAP_SENTENCES = 2

    def __init__(self, use_semantic_splitting: bool = False) -> None:
        self.nlp = _get_sentencizer() if use_semantic_splitting else None
        self.model = _get_chunking_model() if use_semantic_splitting else None
        self.cleaner = ScientificTextCleaner()
        self.splitter = ScientificSentenceSplitter()

    def chunk_paper(self, paper: PaperRawData) -> list[Chunk]:
        chunks: list[Chunk] = []
        for section, text in paper.sections.items():
            text = self.cleaner.clean(text, mode="standard")
            if not text.strip():
                continue
            if section in {"references", "acknowledgments"}:
                continue
            if section in {"abstract", "future_work", "conclusion"} or len(text.split()) < 450:
                parts = [text]
            elif self.model is None:
                parts = self._sentence_window_split(text)
            else:
                parts = self._semantic_split(text, section)
            for idx, part in enumerate(self._with_overlap(parts)):
                chunks.append(
                    Chunk(
                        section=section,
                        sub_index=idx,
                        content=part,
                        importance_score=self._score_importance(section, part),
                        word_count=len(part.split()),
                    )
                )
        return chunks

    def _sentence_window_split(self, text: str) -> list[str]:
        sentences = self._split_sentences(text)
        if len(sentences) <= 6:
            return [text]
        chunks = self.splitter.pack_to_chunks(sentences, max_words=220, overlap=0)
        return self._normalize_chunk_sizes(chunks)

    def _semantic_split(self, text: str, section: str) -> list[str]:
        if self.nlp is None or self.model is None:
            return self._sentence_window_split(text)
        sentences = [sent.text.strip() for sent in self.nlp(text).sents if sent.text.strip()]
        if len(sentences) <= 6:
            return [text]
        embeddings = self.model.encode(sentences, normalize_embeddings=True)
        similarities = np.sum(embeddings[:-1] * embeddings[1:], axis=1)
        split_points = {i + 1 for i, sim in enumerate(similarities) if sim < 0.6}
        chunks: list[str] = []
        current: list[str] = []
        for idx, sentence in enumerate(sentences):
            if idx in split_points and current:
                chunks.append(" ".join(current))
                current = []
            current.append(sentence)
        if current:
            chunks.append(" ".join(current))
        return self._normalize_chunk_sizes(chunks)

    def _normalize_chunk_sizes(self, chunks: list[str]) -> list[str]:
        normalized: list[str] = []
        for chunk in chunks:
            words = chunk.split()
            if len(words) * 1.3 > self.MAX_CHUNK_TOKENS:
                midpoint = len(words) // 2
                normalized.extend([" ".join(words[:midpoint]), " ".join(words[midpoint:])])
            else:
                normalized.append(chunk)
        merged: list[str] = []
        for chunk in normalized:
            if merged and len(chunk.split()) < self.MIN_CHUNK_WORDS:
                merged[-1] = f"{merged[-1]} {chunk}"
            else:
                merged.append(chunk)
        return merged

    def _with_overlap(self, chunks: list[str]) -> list[str]:
        if len(chunks) <= 1:
            return chunks
        overlapped: list[str] = []
        previous_tail = ""
        for chunk in chunks:
            content = f"{previous_tail} {chunk}".strip() if previous_tail else chunk
            overlapped.append(content)
            sents = self._split_sentences(chunk)
            previous_tail = " ".join(sents[-self.OVERLAP_SENTENCES :])
        return overlapped

    def _score_importance(self, section: str, content: str) -> float:
        base = {
            "abstract": 1.0,
            "results": 0.95,
            "conclusion": 0.9,
            "future_work": 0.88,
            "discussion": 0.75,
            "methods": 0.7,
            "methodology": 0.7,
            "introduction": 0.6,
            "related_work": 0.5,
            "other": 0.4,
        }.get(section, 0.4)
        lowered = content.lower()
        bonus = 0.0
        if any(term in lowered for term in ["significant", "novel", "demonstrate", "first", "discovered", "found that", "we show", "our results", "p < ", "p=0.0"]):
            bonus += 0.07
        if re.search(r"\d+\.?\d*\s?%", content):
            bonus += 0.05
        if any(term in lowered for term in ["however", "in contrast", "surprisingly"]):
            bonus += 0.03
        return min(1.0, base + bonus)

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return []
        return ScientificSentenceSplitter().split(normalized)


@lru_cache(maxsize=1)
def _get_sentencizer():
    import spacy

    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    return nlp


@lru_cache(maxsize=1)
def _get_chunking_model():
    from retrieval.vector_store import _get_embedding_model
    return _get_embedding_model()
