from ingestion.chunker import SemanticChunker
from ingestion.pdf_parser import ScientificPDFParser


def test_section_header_detection():
    parser = ScientificPDFParser()
    assert parser._is_section_header("Abstract", 12, True) == "abstract"
    assert parser._is_section_header("1 Introduction", 12, True) == "introduction"


def test_importance_scoring_without_model_load():
    score = SemanticChunker.__new__(SemanticChunker)._score_importance("results", "We show a significant 12% improvement.")
    assert score == 1.0
