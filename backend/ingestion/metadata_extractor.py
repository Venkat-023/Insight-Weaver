import re

from ingestion.pdf_parser import PaperRawData


class MetadataExtractor:
    def extract(self, paper: PaperRawData) -> dict:
        year = None
        haystack = " ".join([paper.title, paper.abstract, str(paper.metadata)])
        match = re.search(r"\b(19|20)\d{2}\b", haystack)
        if match:
            year = int(match.group(0))
        doi_match = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", haystack, re.I)
        return {
            "title": paper.title,
            "authors": paper.authors,
            "abstract": paper.abstract,
            "publication_year": year,
            "doi": doi_match.group(0) if doi_match else None,
            "raw_text": "\n\n".join(paper.sections.values()),
        }
