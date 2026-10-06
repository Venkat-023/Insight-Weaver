"""Scientific citation parsing, normalization, and bibliographic export utilities.

Provides functions for extracting DOIs, parsing raw reference strings into
structured records, and generating standard BibTeX bibliography entries.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


# Standard regular expression for Digital Object Identifiers (DOIs)
DOI_REGEX = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", re.IGNORECASE)

# Pattern for capturing year in reference entries
YEAR_REGEX = re.compile(r"\b(19\d{2}|20\d{2})\b")


def extract_doi_from_text(text: str) -> str | None:
    """Extract and sanitize the first valid DOI found in scientific text.

    Args:
        text: Raw document text, title, or reference snippet.

    Returns:
        Sanitized DOI string, or None if no valid pattern match is found.
    """
    if not text:
        return None

    match = DOI_REGEX.search(text)
    if not match:
        return None

    doi = match.group(0).rstrip(".,;)>]")
    return doi if len(doi) > 7 else None


def normalize_citation_key(
    title: str,
    year: int | None = None,
    author: str | None = None,
) -> str:
    """Generate a sanitized BibTeX citation key (e.g. 'vaswani2017attention').

    Args:
        title: Title of the scientific paper.
        year: Publication year.
        author: First author's surname.

    Returns:
        Alphanumeric citation key suitable for LaTeX and BibTeX references.
    """
    clean_author = "anon"
    if author:
        surname = author.strip().split()[-1]
        clean_author = re.sub(r"[^a-zA-Z0-9]", "", surname).lower() or "anon"

    year_str = str(year) if year else "nd"

    clean_title = unicodedata.normalize("NFKD", title or "")
    first_title_word = ""
    for word in clean_title.split():
        candidate = re.sub(r"[^a-zA-Z0-9]", "", word).lower()
        if candidate and candidate not in {"a", "an", "the", "on", "in", "for", "with"}:
            first_title_word = candidate
            break

    if not first_title_word:
        first_title_word = "paper"

    return f"{clean_author}{year_str}{first_title_word}"


def parse_reference_entry(raw_ref: str) -> dict[str, Any]:
    """Parse a single unstructured bibliography reference into structured components.

    Args:
        raw_ref: Raw reference string from the bibliography section of a paper.

    Returns:
        Dictionary containing extracted authors, year, title, and venue.
    """
    if not raw_ref:
        return {"authors": [], "year": None, "title": "", "venue": ""}

    cleaned = re.sub(r"\s+", " ", raw_ref).strip()
    year_match = YEAR_REGEX.search(cleaned)
    year = int(year_match.group(1)) if year_match else None

    # Extract authors and title using conventional punctuation separators
    authors: list[str] = []
    title = ""
    venue = ""

    if year_match:
        before_year = cleaned[: year_match.start()].strip().rstrip("(.,")
        after_year = cleaned[year_match.end() :].strip().lstrip(").,")

        if before_year:
            raw_authors = re.split(r",\s*|\s+and\s+", before_year)
            authors = [a.strip() for a in raw_authors if len(a.strip()) > 1]

        # In standard academic styles, title usually follows year up to the next period/quotes
        quote_match = re.search(r"\"([^\"]+)\"|“([^”]+)”", after_year)
        if quote_match:
            title = quote_match.group(1) or quote_match.group(2) or ""
            venue = after_year[quote_match.end() :].strip(" .,")
        else:
            segments = [seg.strip() for seg in after_year.split(".") if seg.strip()]
            if segments:
                title = segments[0]
                venue = " ".join(segments[1:]) if len(segments) > 1 else ""
    else:
        title = cleaned

    return {
        "authors": authors,
        "year": year,
        "title": title,
        "venue": venue,
        "doi": extract_doi_from_text(raw_ref),
    }


def format_bibtex_entry(ref_data: dict[str, Any]) -> str:
    """Format structured reference dictionary into standard BibTeX entry format.

    Args:
        ref_data: Dictionary with 'title', 'authors', 'year', 'venue', etc.

    Returns:
        Formatted BibTeX string.
    """
    title = ref_data.get("title", "Untitled Document")
    authors = ref_data.get("authors") or ["Unknown Author"]
    year = ref_data.get("year") or 2024
    venue = ref_data.get("venue", "")
    cite_key = normalize_citation_key(title, year, authors[0] if authors else None)

    author_field = " and ".join(authors)
    lines = [
        f"@article{{{cite_key},",
        f"  title = {{{title}}},",
        f"  author = {{{author_field}}},",
        f"  year = {{{year}}},",
    ]
    if venue:
        lines.append(f"  journal = {{{venue}}},")
    if ref_data.get("doi"):
        lines.append(f"  doi = {{{ref_data['doi']}}},")
    lines.append("}")
    return "\n".join(lines)


# ==============================================================================
# UNUSED FUNCTIONS / DEAD CODE CANDIDATES FOR DEAD CODE ANALYSIS TESTING
# ==============================================================================

def _legacy_strip_arxiv_version(raw_arxiv_str: str) -> str:
    """[UNUSED] Internal helper to strip version suffix (e.g. 'v1', 'v2') from old arXiv IDs.

    Dead code note: This function is never referenced or called internally
    nor exported for use elsewhere in the project.
    """
    if not raw_arxiv_str:
        return ""
    cleaned = raw_arxiv_str.strip()
    return re.sub(r"v\d+$", "", cleaned)


def convert_citation_to_harvard_format(
    authors: list[str],
    year: int | None,
    title: str,
    journal: str = "",
) -> str:
    """[UNUSED] Format citation into Harvard referencing style.

    Dead code note: Never imported or called in any module, router, or workflow.
    """
    author_str = "Anon."
    if authors:
        if len(authors) == 1:
            author_str = authors[0]
        elif len(authors) == 2:
            author_str = f"{authors[0]} and {authors[1]}"
        else:
            author_str = f"{authors[0]} et al."

    year_str = f"({year})" if year else "(n.d.)"
    formatted = f"{author_str} {year_str} '{title}'"
    if journal:
        formatted += f", {journal}"
    return formatted + "."


def calculate_journal_impact_proxy(issn: str) -> float | None:
    """[UNUSED] Estimate a dummy/proxy journal impact factor based on ISSN prefixes.

    Dead code note: Experimental heuristic for paper prioritization that was
    abandoned and never hooked up to any active pipeline.
    """
    if not issn or len(issn) < 8:
        return None
    # Simulated heuristic mapping
    checksum = sum(ord(c) for c in issn if c.isdigit()) % 10
    base_score = 1.5 + (checksum * 0.4)
    return round(base_score, 2)
