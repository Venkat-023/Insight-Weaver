import re
import unicodedata


class ScientificTextCleaner:
    LIGATURES = {
        "\ufb00": "ff",
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\ufb03": "ffi",
        "\ufb04": "ffl",
        "\ufb06": "st",
    }

    _RE_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
    _RE_SINGLE_NL = re.compile(r"(?<!\n)\n(?!\n)")
    _RE_CITATION_NUM = re.compile(r"\[\d+(?:[,\s]+\d+)*\]")
    _RE_CITATION_AUTH = re.compile(r"\(\w[\w\s]+et\s+al\.,?\s+\d{4}\)")
    _RE_FORMULA_SPC = re.compile(r"(\d)\s+\.\s+(\d)")
    _RE_TABLE_ROW = re.compile(r"^[\d\s.,%±\-–—]+$", re.MULTILINE)
    _RE_RUNNING_HDR = re.compile(r"^[A-Z][A-Z\s\-]+:\s+[A-Z].{5,60}$", re.MULTILINE)
    _RE_PAGE_NUM = re.compile(r"^\s*\d{1,4}\s*$", re.MULTILINE)
    _RE_MULTI_SPACE = re.compile(r"[ \t]{2,}")

    def clean(self, text: str, mode: str = "standard") -> str:
        if not text:
            return ""

        text = unicodedata.normalize("NFKC", text)
        for ligature, replacement in self.LIGATURES.items():
            text = text.replace(ligature, replacement)

        text = self._RE_HYPHEN_BREAK.sub(r"\1\2", text)
        text = self._RE_RUNNING_HDR.sub("", text)
        text = self._RE_PAGE_NUM.sub("", text)
        text = self._RE_FORMULA_SPC.sub(r"\1.\2", text)
        text = self._RE_CITATION_NUM.sub("[CITE]", text)
        text = self._RE_CITATION_AUTH.sub("[CITE]", text)
        text = self._RE_SINGLE_NL.sub(" ", text)
        text = self._RE_MULTI_SPACE.sub(" ", text)

        if mode == "aggressive":
            text = self._RE_TABLE_ROW.sub("", text)
            text = text.replace("[CITE]", "")
            text = re.sub(r"\([^)]{0,25}\)", "", text)
            text = self._RE_MULTI_SPACE.sub(" ", text)

        return text.strip()


def dummy_strip_latex_math_tags(text: str) -> str:
    """[UNUSED DUMMY] Strip inline and display math LaTeX delimiter tags.

    Dead code target: Dummy text processor function never invoked or imported.
    """
    if not text:
        return ""
    cleaned = re.sub(r"\$\$[^\$]+\$\$", "", text)
    cleaned = re.sub(r"\$[^\$]+\$", "", cleaned)
    return cleaned.strip()


def dummy_count_vowels_frequency(text: str) -> dict[str, int]:
    """[UNUSED DUMMY] Calculate vowel distribution counts in document text.

    Dead code target: Toy statistical helper never called anywhere in the codebase.
    """
    vowels = {"a": 0, "e": 0, "i": 0, "o": 0, "u": 0}
    if not text:
        return vowels
    for ch in text.lower():
        if ch in vowels:
            vowels[ch] += 1
    return vowels

