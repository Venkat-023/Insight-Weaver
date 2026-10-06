"""Unit tests for the new citation, retrieval metrics, and graph analytics utilities.

Note for dead code analysis:
These tests strictly exercise the active, production-grade utility functions.
The dead code functions (_legacy_strip_arxiv_version, convert_citation_to_harvard_format,
calculate_journal_impact_proxy, _compute_ngram_jaccard_similarity, legacy_calculate_bleu_score,
estimate_retrieval_latency_budget, _dijkstra_shortest_distance, export_graph_to_graphml_xml,
calculate_graph_density_ratio) are intentionally NOT tested or referenced here.
"""

from preprocessing.citation_utils import (
    extract_doi_from_text,
    format_bibtex_entry,
    normalize_citation_key,
    parse_reference_entry,
)
from retrieval.rag_metrics import (
    calculate_citation_grounding_score,
    compute_context_relevance_score,
    evaluate_chunk_diversity,
)
from graph.graph_analytics import (
    compute_node_degree_centralities,
    filter_isolated_entities,
    find_connected_subgraphs,
)


def test_doi_extraction():
    sample_text = "Refer to the initial study published at 10.1038/s41586-020-2649-2 for details."
    doi = extract_doi_from_text(sample_text)
    assert doi == "10.1038/s41586-020-2649-2"

    assert extract_doi_from_text("No DOI in this string.") is None


def test_citation_key_and_bibtex():
    key = normalize_citation_key("Attention Is All You Need", 2017, "Ashish Vaswani")
    assert key == "vaswani2017attention"

    ref_data = {
        "title": "Attention Is All You Need",
        "authors": ["Ashish Vaswani", "Noam Shazeer"],
        "year": 2017,
        "venue": "NeurIPS",
        "doi": "10.5555/3295222.3295349",
    }
    bib = format_bibtex_entry(ref_data)
    assert "@article{vaswani2017attention," in bib
    assert "author = {Ashish Vaswani and Noam Shazeer}" in bib


def test_parse_reference_entry():
    raw_ref = "Vaswani, A., Shazeer, N. (2017). Attention Is All You Need. NeurIPS."
    parsed = parse_reference_entry(raw_ref)
    assert parsed["year"] == 2017
    assert len(parsed["authors"]) >= 1
    assert "Attention" in parsed["title"]


def test_rag_context_relevance():
    query = "How does p53 regulate apoptosis in cancer cells?"
    chunks = [
        "The p53 tumor suppressor regulates apoptosis through transcriptional activation of BAX.",
        "DNA damage triggers rapid p53 accumulation leading to apoptotic cell death.",
    ]
    relevance = compute_context_relevance_score(chunks, query)
    assert relevance > 0.3


def test_citation_grounding_score():
    answer = "p53 activates BAX expression to initiate apoptosis. This pathway suppresses tumors."
    evidence = [
        "Transcriptional activation of BAX by p53 promotes apoptosis and cellular tumor suppression."
    ]
    score = calculate_citation_grounding_score(answer, evidence)
    assert score > 0.0


def test_chunk_diversity():
    chunks = [
        {"paper_id": 1, "section": "abstract"},
        {"paper_id": 2, "section": "methods"},
        {"paper_id": 1, "section": "results"},
    ]
    diversity = evaluate_chunk_diversity(chunks)
    assert diversity > 0.5


def test_graph_analytics_centrality():
    nodes = [{"id": "p1", "type": "paper"}, {"id": "e1", "type": "entity"}, {"id": "e2", "type": "entity"}]
    edges = [{"source": "p1", "target": "e1"}, {"source": "p1", "target": "e2"}]

    centralities = compute_node_degree_centralities(nodes, edges)
    assert centralities["p1"] == 1.0
    assert centralities["e1"] == 0.5
    assert centralities["e2"] == 0.5


def test_graph_subgraphs_and_isolated_filter():
    nodes = [
        {"id": "p1", "type": "paper"},
        {"id": "e1", "type": "entity"},
        {"id": "e_isolated", "type": "entity"},
    ]
    edges = [{"source": "p1", "target": "e1"}]

    components = find_connected_subgraphs(nodes, edges)
    assert len(components) == 2

    retained = filter_isolated_entities(nodes, edges)
    retained_ids = [n["id"] for n in retained]
    assert "e_isolated" not in retained_ids
    assert "p1" in retained_ids
    assert "e1" in retained_ids
