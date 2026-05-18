import re
import string
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import requests

from preprocessing.cleaner import ScientificTextCleaner


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
    skip_headers = {
        "references",
        "bibliography",
        "acknowledgments",
        "acknowledgements",
        "appendix",
        "supplementary",
        "supplementary material",
        "funding",
        "conflicts of interest",
        "author contributions",
        "data availability",
    }

    expanded_headers = {
        **known_headers,
        "proposed method": "methods",
        "proposed approach": "methods",
        "system design": "methods",
        "implementation details": "methods",
        "technical approach": "methods",
        "model architecture": "methods",
        "ablation study": "results",
        "ablation": "results",
        "quantitative results": "results",
        "qualitative analysis": "results",
        "benchmarks": "results",
        "baseline comparison": "results",
        "concluding remarks": "conclusion",
        "summary and conclusion": "conclusion",
        "conclusion and future work": "conclusion",
        "future directions": "future_work",
        "open problems": "future_work",
        "limitations and future work": "future_work",
        "broader impact": "future_work",
        "ethical considerations": "future_work",
    }

    _section_prefix = re.compile(r"^(?:\d+(?:\.\d+)*\.?\s+|[IVXivx]+\.\s+|[A-Z]\.\s+)")

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
        first_page_blocks: list[dict] = []
        for block in first_page.get("blocks", []):
            for line in block.get("lines", []):
                line_spans = line.get("spans", [])
                spans.extend(line_spans)
                text = " ".join(span.get("text", "") for span in line_spans).strip()
                if text:
                    first_page_blocks.append(
                        {
                            "text": text,
                            "size": max((span.get("size", 0) for span in line_spans), default=0),
                            "bold": any("bold" in span.get("font", "").lower() for span in line_spans),
                            "y": line.get("bbox", [0, 0, 0, 0])[1],
                        }
                    )

        title = self._detect_title(first_page_blocks)
        authors = self._detect_authors(first_page_blocks, title)

        sections: dict[str, list[str]] = {"other": []}
        current = "other"
        skip_mode = False
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
                        if header == "SKIP":
                            skip_mode = True
                            current = "SKIP"
                            continue
                        skip_mode = False
                        current = header
                        sections.setdefault(current, [])
                        continue
                    if skip_mode:
                        continue
                    sections.setdefault(current, []).append(text)
                    full_text_parts.append(text)

        cleaner = ScientificTextCleaner()
        materialized = {
            k: cleaner.clean("\n".join(v).strip(), mode="standard")
            for k, v in sections.items()
            if k != "SKIP" and "\n".join(v).strip()
        }
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
        normalized = self._normalize_header(line)
        if len(line) < 80 and normalized in self.skip_headers and (is_bold or font_size >= 10.5):
            return "SKIP"
        if len(line) < 80 and normalized in self.expanded_headers and (is_bold or font_size >= 11):
            return self.expanded_headers[normalized]
        return None

    def _normalize_header(self, line: str) -> str:
        normalized = line.lower().strip().strip(string.punctuation).rstrip(".")
        normalized = self._section_prefix.sub("", normalized).strip()
        return normalized

    def _detect_title(self, first_page_blocks: list[dict]) -> str:
        if not first_page_blocks:
            return "Unknown Title"

        max_y = max((block.get("y", 0) for block in first_page_blocks), default=800)
        top_zone = max_y * 0.45
        exclude_patterns = [
            re.compile(r"^\d+$"),
            re.compile(r"^[A-Z][A-Z\s\-]{10,}$"),
            re.compile(r"@"),
            re.compile(r"doi|arxiv|preprint", re.I),
            re.compile(r"^\d{4}$"),
        ]
        candidates: list[tuple[float, float, str]] = []
        for block in first_page_blocks:
            text = block.get("text", "").strip()
            y = block.get("y", 0)
            size = block.get("size", 10.0)
            if y > top_zone or len(text) < 15 or len(text) > 280:
                continue
            if any(pattern.search(text) for pattern in exclude_patterns):
                continue
            if self._normalize_header(text) in self.expanded_headers or self._normalize_header(text) in self.skip_headers:
                continue
            if text == text.upper() and len(text) > 10:
                continue
            candidates.append((size, -y, text))
        if not candidates:
            return "Unknown Title"
        candidates.sort(key=lambda item: (-item[0], item[1]))
        return candidates[0][2]

    def _detect_authors(self, first_page_blocks: list[dict], title: str) -> list[str]:
        if not first_page_blocks:
            return []

        max_y = max((block.get("y", 0) for block in first_page_blocks), default=800)
        author_zone = (max_y * 0.08, max_y * 0.52)
        affiliation_signals = {
            "university",
            "institute",
            "department",
            "college",
            "laboratory",
            "center",
            "school",
            "faculty",
            "hospital",
            ".edu",
            ".ac.",
            "@",
            "email:",
            "correspondence",
            "equal contribution",
            "these authors",
        }
        name_pattern = re.compile(r"^[A-Z][A-Za-zÀ-ÿ]+(?:[-\s][A-Z][A-Za-zÀ-ÿ]+)*$")
        authors: list[str] = []
        for block in first_page_blocks:
            text = block.get("text", "").strip()
            y = block.get("y", 0)
            size = block.get("size", 10.0)
            if not (author_zone[0] < y < author_zone[1]):
                continue
            if not (8.5 < size < 13.5) or len(text) > 180:
                continue
            if title and title[:30].lower() in text.lower():
                continue
            if re.search(r"\d{3,}", text):
                continue
            if any(signal in text.lower() for signal in affiliation_signals):
                continue
            for part in re.split(r"[,;]\s*|\s+and\s+", text, flags=re.IGNORECASE):
                part = re.sub(r"[\d*†‡§¶]+$", "", part.strip()).strip()
                if 4 < len(part) < 60 and name_pattern.match(part):
                    authors.append(part)

        seen: set[str] = set()
        result: list[str] = []
        for author in authors:
            key = author.lower()
            if key not in seen:
                seen.add(key)
                result.append(author)
        return result[:12]

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
