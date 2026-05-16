from ingestion.pdf_parser import PaperRawData, ScientificPDFParser


class ArxivFetcher:
    def __init__(self) -> None:
        self.parser = ScientificPDFParser()

    def fetch(self, arxiv_id: str) -> PaperRawData:
        return self.parser.parse_from_arxiv(arxiv_id)
