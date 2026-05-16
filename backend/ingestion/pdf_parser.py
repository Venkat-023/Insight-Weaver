import re
import string
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import requests


@dataclass
class PaperRawData:
    title: str
    authors: list[str]
    abstract: str
    sections: dict[str, str]
    references: list[str]
    page_count: int
    metadata: dict = field(default_factory=dict)


class ScientificPDFParser:
    known_headers = {
        "abstract": "abstract",
        "introduction": "introduction",
        "related work": "related_work",
        "background": "background",
        "methodology": "methods",
        "methods": "methods",
        "experimental setup": "methods",
        "results": "results",
        "experiments": "results",
        "discussion": "discussion",
        "conclusion": "conclusion",
        "future work": "future_work",
        "acknowledgments": "acknowledgments",
        "references": "references",
    }

    def parse_pdf(self, pdf_path: str) -> PaperRawData:
        try:
            return self._parse_with_pymupdf(pdf_path)
        except Exception:
            return self._parse_with_pdfplumber(pdf_path)

    def _parse_with_pymupdf(self, pdf_path: str) -> PaperRawData:
        import fitz

        doc = fitz.open(pdf_path)
        page_count = doc.page_count
        first_page = doc[0].get_text("dict")
        spans: list[dict] = []
        for block in first_page.get("blocks", []):
            for line in block.get("lines", []):
                spans.extend(line.get("spans", []))

        title_span = max((s for s in spans if len(s.get("text", "").strip()) > 10), key=lambda s: s["size"], default={})
        title = title_span.get("text", "").strip()
        title_y = title_span.get("bbox", [0, 0, 0, 0])[1] if title_span else 0
        authors = [
            s["text"].strip()
            for s in spans
            if 10 <= s.get("size", 0) <= 13 and s.get("bbox", [0, 999, 0, 0])[1] > title_y and 2 < len(s.get("text", "")) < 160
        ][:8]

        sections: dict[str, list[str]] = {"other": []}
        current = "other"
        full_text_parts: list[str] = []
        for page in doc:
            text_dict = page.get_text("dict")
            for block in text_dict.get("blocks", []):
                for line in block.get("lines", []):
                    text = " ".join(span.get("text", "") for span in line.get("spans", [])).strip()
                    if not text:
                        continue
                    max_size = max((span.get("size", 0) for span in line.get("spans", [])), default=0)
                    is_bold = any("bold" in span.get("font", "").lower() for span in line.get("spans", []))
                    header = self._is_section_header(text, max_size, is_bold)
                    if header:
                        current = header
                        sections.setdefault(current, [])
                        continue
                    sections.setdefault(current, []).append(text)
                    full_text_parts.append(text)

        materialized = {k: "\n".join(v).strip() for k, v in sections.items() if "\n".join(v).strip()}
        abstract = materialized.get("abstract", self._extract_abstract("\n".join(full_text_parts)))
        references = self._split_references(materialized.get("references", ""))
        if not title:
            raise ValueError("PyMuPDF failed to identify a title")
        return PaperRawData(title, authors, abstract, materialized, references, page_count, {"parser": "pymupdf"})

    def _parse_with_pdfplumber(self, pdf_path: str) -> PaperRawData:
        import pdfplumber

        with pdfplumber.open(pdf_path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        text = "\n".join(pages)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        title = lines[0] if lines else Path(pdf_path).stem
        sections = self._simple_section_split(lines)
        return PaperRawData(
            title=title,
            authors=[],
            abstract=sections.get("abstract", self._extract_abstract(text)),
            sections=sections or {"other": text},
            references=self._split_references(sections.get("references", "")),
            page_count=len(pages),
            metadata={"parser": "pdfplumber"},
        )

    def parse_from_arxiv(self, arxiv_id: str) -> PaperRawData:
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        pdf_path = Path("/tmp") / f"{arxiv_id}.pdf"
        with requests.get(pdf_url, timeout=30, stream=True) as response:
            response.raise_for_status()
            with pdf_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    handle.write(chunk)
        meta_response = requests.get(f"https://export.arxiv.org/api/query?id_list={arxiv_id}", timeout=30)
        meta_response.raise_for_status()
        metadata = self._parse_arxiv_metadata(meta_response.text)
        parsed = self.parse_pdf(str(pdf_path))
        parsed.title = metadata.get("title") or parsed.title
        parsed.authors = metadata.get("authors") or parsed.authors
        parsed.abstract = metadata.get("abstract") or parsed.abstract
        parsed.metadata.update(metadata)
        return parsed

    def _is_section_header(self, line: str, font_size: float, is_bold: bool) -> str | None:
        normalized = line.lower().strip().strip(string.punctuation)
        normalized = re.sub(r"^\d+(\.\d+)*\s+", "", normalized)
        if len(line) < 80 and normalized in self.known_headers and (is_bold or font_size >= 11):
            return self.known_headers[normalized]
        return None

    def _simple_section_split(self, lines: list[str]) -> dict[str, str]:
        sections: dict[str, list[str]] = {"other": []}
        current = "other"
        for line in lines:
            header = self._is_section_header(line, 12, True)
            if header:
                current = header
                sections.setdefault(current, [])
            else:
                sections.setdefault(current, []).append(line)
        return {k: "\n".join(v) for k, v in sections.items() if v}

    @staticmethod
    def _extract_abstract(text: str) -> str:
        match = re.search(r"abstract\s*(.*?)(?:\n\s*(?:introduction|1\s+introduction)\b)", text, re.I | re.S)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _split_references(text: str) -> list[str]:
        return [item.strip() for item in re.split(r"\n\s*(?:\[\d+\]|\d+\.)\s*", text) if len(item.strip()) > 10]

    @staticmethod
    def _parse_arxiv_metadata(xml_text: str) -> dict:
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)
        if entry is None:
            return {}
        return {
            "title": " ".join((entry.findtext("atom:title", "", ns) or "").split()),
            "abstract": " ".join((entry.findtext("atom:summary", "", ns) or "").split()),
            "authors": [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)],
            "published": entry.findtext("atom:published", "", ns),
        }
