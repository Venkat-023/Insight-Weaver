import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache

from core.config import get_settings
from ingestion.chunker import Chunk


@dataclass
class EntityExtractionResult:
    entities: dict[str, list[str]]
    relationships: list[dict]
    key_findings: list[str]


class ScientificEntityExtractor:
    ENTITY_TYPES = ["DISEASE", "PROTEIN", "GENE", "CHEMICAL", "METHOD", "PATHWAY", "ORGANISM", "CONCEPT"]

    def __init__(self, use_gemma_refinement: bool = False, use_scispacy: bool = False) -> None:
        self.nlp = _get_scientific_nlp() if use_scispacy else None
        self.use_gemma_refinement = use_gemma_refinement
        self.gemma = None
        if use_gemma_refinement:
            from core.gemma_engine import GemmaEngine

            self.gemma = GemmaEngine(get_settings().gemma_light_model)

    def extract(self, chunks: list[Chunk]) -> EntityExtractionResult:
        selected = [chunk for chunk in chunks if chunk.importance_score >= 0.7]
        if not selected:
            selected = sorted(chunks, key=lambda chunk: chunk.importance_score, reverse=True)[:8]
        text = "\n\n".join(chunk.content for chunk in selected)
        counter: Counter[str] = Counter()
        typed: dict[str, set[str]] = defaultdict(set)
        if self.nlp is not None:
            for chunk in selected:
                doc = self.nlp(chunk.content)
                for ent in getattr(doc, "ents", []):
                    name = self._normalize(ent.text)
                    if not name or len(name) < 3:
                        continue
                    label = self._map_label(ent.label_)
                    typed[label].add(name)
                    counter[name] += 1
        self._add_keyword_entities(text, typed, counter)
        top_entities = {k: sorted(v, key=lambda name: (-counter[name], name.lower()))[:10] for k, v in typed.items()}
        if not self.use_gemma_refinement or self.gemma is None:
            return EntityExtractionResult(
                entities={entity_type: top_entities.get(entity_type, []) for entity_type in self.ENTITY_TYPES},
                relationships=[],
                key_findings=[],
            )
        prompt = self._build_prompt(text[:9000], json.dumps(top_entities))
        try:
            refined = self.gemma.generate_structured(prompt)
        except Exception:
            refined = {
                "validated_entities": {entity_type: top_entities.get(entity_type, []) for entity_type in self.ENTITY_TYPES},
                "relationships": [],
                "key_findings": [],
            }
        return EntityExtractionResult(
            entities=refined.get("validated_entities", top_entities),
            relationships=refined.get("relationships", []),
            key_findings=refined.get("key_findings", []),
        )

    @staticmethod
    def _normalize(name: str) -> str:
        normalized = " ".join(name.strip().split())
        return normalized[:-1] if normalized.endswith("s") and len(normalized) > 4 else normalized

    @staticmethod
    def _map_label(label: str) -> str:
        upper = label.upper()
        if upper in ScientificEntityExtractor.ENTITY_TYPES:
            return upper
        if upper in {"CHEMICAL_ENTITY", "DRUG"}:
            return "CHEMICAL"
        if upper in {"ORGANISM_TAXON"}:
            return "ORGANISM"
        return "CONCEPT"

    @classmethod
    def _add_keyword_entities(cls, text: str, typed: dict[str, set[str]], counter: Counter[str]) -> None:
        lower_text = text.lower()
        phrase_types = {
            "deep learning": "METHOD",
            "machine learning": "METHOD",
            "computer vision": "METHOD",
            "endoscopy": "METHOD",
            "laparoscopy": "METHOD",
            "federated learning": "METHOD",
            "convolutional neural network": "METHOD",
            "transformer": "METHOD",
            "lesion": "DISEASE",
            "lesions": "DISEASE",
            "cancer": "DISEASE",
            "colorectal lesions": "DISEASE",
            "gastric cancer": "DISEASE",
            "barrett": "DISEASE",
            "dataset bias": "CONCEPT",
            "generalizability": "CONCEPT",
            "real-time deployment": "CONCEPT",
            "clinical translation": "CONCEPT",
            "privacy": "CONCEPT",
            "electronic health records": "CONCEPT",
            "ehr": "CONCEPT",
            "mortality prediction": "CONCEPT",
            "hierarchical transformer": "METHOD",
        }
        for phrase, entity_type in phrase_types.items():
            if phrase in lower_text:
                canonical = cls._canonical_phrase(phrase)
                typed[entity_type].add(canonical)
                counter[canonical] += lower_text.count(phrase)

        candidates = re.findall(r"\b(?:[A-Z][A-Za-z0-9-]{2,}|[A-Z]{2,}(?:-[A-Z0-9]+)?)\b", text)
        stop = {"TEXT", "TASKS", "JSON", "IEEE", "DOI", "RQ"}
        for candidate in candidates:
            if candidate in stop or len(candidate) < 3:
                continue
            typed["CONCEPT"].add(candidate)
            counter[candidate] += 1

    @staticmethod
    def _canonical_phrase(phrase: str) -> str:
        acronyms = {"ehr": "EHR"}
        if phrase in acronyms:
            return acronyms[phrase]
        return " ".join(word.capitalize() for word in phrase.split())

    @staticmethod
    def _build_prompt(text: str, spacy_entities_json: str) -> str:
        return f"""
You are a scientific entity extraction specialist. Analyze this scientific text:

TEXT:
{text}

ENTITIES FOUND BY NER (validate these):
{spacy_entities_json}

TASKS:
1. Remove false positives (e.g. generic words incorrectly tagged as entities)
2. Add important entities the NER missed
3. Extract typed relationships between entities
4. Normalize entity names to their canonical form (e.g. "Covid-19" -> "SARS-CoV-2")

STRICT OUTPUT - valid JSON only, no markdown, no explanation:
{{
  "validated_entities": {{
    "DISEASE": [], "PROTEIN": [], "GENE": [], "CHEMICAL": [], "METHOD": [], "PATHWAY": [], "ORGANISM": [], "CONCEPT": []
  }},
  "relationships": [
    {{"source": "entity_name", "relation": "treats|inhibits|activates|correlates_with|causes|similar_to|part_of", "target": "entity_name", "confidence": 0.0, "evidence": "one sentence from text supporting this"}}
  ],
  "key_findings": ["brief statement"]
}}
"""


@lru_cache(maxsize=1)
def _get_scientific_nlp():
    import spacy
    try:
        return spacy.load("en_core_sci_lg")  # full sci NER, no UMLS linker
    except Exception:
        nlp = spacy.blank("en")
        nlp.add_pipe("sentencizer")
        return nlp
