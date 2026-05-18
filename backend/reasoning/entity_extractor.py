import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache

from core.config import get_settings
from ingestion.chunker import Chunk
from preprocessing.cleaner import ScientificTextCleaner


@dataclass
class EntityExtractionResult:
    entities: dict[str, list[str]]
    relationships: list[dict]
    key_findings: list[str]


_GENE_PROTEIN_PATS = [
    re.compile(r"\b([A-Z]{2,7}\d*(?:-[A-Z\d]+)?)\b"),
    re.compile(r"\b([A-Z][a-z]{1,3}[A-Z]\d+[A-Za-z]?)\b"),
    re.compile(
        r"\b(\w+(?:\s+\w+)?\s+(?:kinase|receptor|protease|inhibitor|antibody|ligand|enzyme|channel|transporter|factor|complex))\b",
        re.I,
    ),
]
_DISEASE_PATS = [
    re.compile(r"\b([A-Z][a-z]+(?:'s)?\s+(?:disease|syndrome|disorder|carcinoma|lymphoma|leukemia|cancer|tumor|tumour))\b"),
    re.compile(r"\b((?:type\s+[12I]+|stage\s+[IVX]+)\s+\w+(?:\s+\w+)?)\b", re.I),
    re.compile(r"\b(COVID-19|SARS-CoV-2|HIV|AIDS|COPD|ADHD|ALS|MS(?=\s+patients))\b"),
]
_CHEMICAL_PATS = [
    re.compile(
        r"\b([a-z]{3,}(?:mab|nib|zumab|umab|ximab|tinib|ciclib|rafenib|lutamide|vudine|navir|cycline|mycin|floxacin|sartan|pril|olol|stat|tide|vir))\b",
        re.I,
    ),
    re.compile(r"\b([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*\s+(?:acid|oxide|chloride|sulfate|phosphate|agonist|antagonist))\b"),
]
_METHOD_PATS = [
    re.compile(
        r"\b((?:deep|machine|transfer|reinforcement|federated|self-supervised|semi-supervised|unsupervised|supervised)\s+learning)\b",
        re.I,
    ),
    re.compile(
        r"\b((?:convolutional|recurrent|transformer|attention|graph\s+neural|generative\s+adversarial)\s+(?:neural\s+)?network[s]?)\b",
        re.I,
    ),
    re.compile(r"\b((?:random\s+forest|gradient\s+boost|support\s+vector|logistic\s+regression|linear\s+discriminant))\b", re.I),
    re.compile(r"\b(BERT|GPT[-\d]*|ViT|ResNet-?\d*|VGG-?\d*|EfficientNet[-\w]*|CLIP|DINO|MAE|UNet|SegNet|Mask\s+R-CNN)\b"),
    re.compile(r"\b([A-Z][A-Za-z0-9]*(?:-v?\d+(?:\.\d+)?)?\s+(?:algorithm|framework|architecture|pipeline|classifier|detector))\b"),
]
_DATASET_PATS = [
    re.compile(r"\b((?:ImageNet|COCO|PubMed|MIMIC[-\s]?(?:III|IV)?|UK\s+Biobank|TCGA|GEO|dbSNP|ChEMBL|BindingDB|OpenTargets))\b", re.I),
    re.compile(r"\b([A-Z][A-Za-z0-9\-]+(?:\s+[A-Za-z0-9\-]+)?\s+(?:dataset|corpus|benchmark|cohort|database|collection))\b", re.I),
]
_ENTITY_BLACKLIST = {
    "a",
    "an",
    "the",
    "this",
    "that",
    "these",
    "those",
    "we",
    "our",
    "they",
    "it",
    "its",
    "table",
    "figure",
    "fig",
    "section",
    "supplementary",
    "appendix",
    "above",
    "below",
    "shown",
    "presented",
    "proposed",
    "described",
    "method",
    "result",
    "study",
    "paper",
    "work",
    "approach",
    "model",
    "data",
    "experiment",
    "performance",
    "evaluation",
    "analysis",
    "finding",
    "doi",
    "ieee",
    "arxiv",
    "preprint",
    "et",
    "al",
    "journal",
}
ALL_PATTERNS = {
    "PROTEIN": _GENE_PROTEIN_PATS,
    "DISEASE": _DISEASE_PATS,
    "CHEMICAL": _CHEMICAL_PATS,
    "METHOD": _METHOD_PATS,
    "DATASET": _DATASET_PATS,
}


def _is_valid_entity(name: str) -> bool:
    cleaned = " ".join(str(name or "").split())
    if not cleaned or len(cleaned) < 2 or len(cleaned) > 80:
        return False
    if cleaned.lower() in _ENTITY_BLACKLIST:
        return False
    if not any(char.isalpha() for char in cleaned):
        return False
    words = cleaned.lower().split()
    return not all(word in _ENTITY_BLACKLIST for word in words)


def _canonical_key(name: str) -> str:
    return re.sub(r"[\s\-_]", "", name.lower())


def run_pattern_ner(text: str) -> dict[str, Counter]:
    results: dict[str, Counter] = defaultdict(Counter)
    for entity_type, patterns in ALL_PATTERNS.items():
        for pattern in patterns:
            for match in pattern.finditer(text):
                name = " ".join(match.group(1).strip().split())
                if _is_valid_entity(name):
                    results[entity_type][name] += 1
    return results


def normalize_entity_results(raw: dict[str, Counter], max_per_type: int = 20) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    for entity_type, counter in raw.items():
        canonical: dict[str, tuple[str, int]] = {}
        for name, frequency in counter.items():
            key = _canonical_key(name)
            existing = canonical.get(key)
            if existing is None or frequency > existing[1] or (frequency == existing[1] and len(name) < len(existing[0])):
                canonical[key] = (name, frequency)
        top = sorted(canonical.values(), key=lambda item: (-item[1], item[0].lower()))[:max_per_type]
        if top:
            normalized[entity_type] = [name for name, _ in top]
    return normalized


class ScientificEntityExtractor:
    ENTITY_TYPES = ["DISEASE", "PROTEIN", "GENE", "CHEMICAL", "METHOD", "DATASET", "PATHWAY", "ORGANISM", "CONCEPT"]

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
        cleaner = ScientificTextCleaner()
        text = cleaner.clean("\n\n".join(chunk.content for chunk in selected), mode="aggressive")
        counter: Counter[str] = Counter()
        typed: dict[str, set[str]] = defaultdict(set)
        pattern_raw = run_pattern_ner(text)
        for entity_type, names in normalize_entity_results(pattern_raw).items():
            for name in names:
                typed[entity_type].add(name)
                counter[name] += pattern_raw[entity_type].get(name, 1)
        if self.nlp is not None:
            for chunk in selected:
                doc = self.nlp(cleaner.clean(chunk.content, mode="aggressive"))
                for ent in getattr(doc, "ents", []):
                    name = self._normalize(ent.text)
                    if not _is_valid_entity(name):
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
        prompt = self._build_prompt(text[:6000], json.dumps(top_entities))
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
        stop = {"TEXT", "TASKS", "JSON", "IEEE", "DOI", "RQ", "FIGURE", "TABLE", "ABSTRACT", "METHODS", "RESULTS"}
        for candidate in candidates:
            if candidate in stop or not _is_valid_entity(candidate):
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
    "DISEASE": [], "PROTEIN": [], "GENE": [], "CHEMICAL": [], "METHOD": [], "DATASET": [], "PATHWAY": [], "ORGANISM": [], "CONCEPT": []
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
