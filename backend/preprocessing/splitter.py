import re


class ScientificSentenceSplitter:
    _NO_BREAK = {
        "al",
        "fig",
        "figs",
        "dr",
        "prof",
        "mr",
        "mrs",
        "ms",
        "vs",
        "cf",
        "ie",
        "eg",
        "eq",
        "eqs",
        "no",
        "vol",
        "approx",
        "est",
        "max",
        "min",
        "avg",
        "et",
        "ibid",
        "jan",
        "feb",
        "mar",
        "apr",
        "jun",
        "jul",
        "aug",
        "sep",
        "oct",
        "nov",
        "dec",
        "st",
        "nd",
        "rd",
        "th",
    }

    _RE_BOUNDARY = re.compile(r"[.!?](?=\s+[A-Z\d])")

    def split(self, text: str) -> list[str]:
        if not text:
            return []
        cuts: list[int] = []
        for match in self._RE_BOUNDARY.finditer(text):
            idx = match.start()
            before = text[:idx].rstrip()
            token = before.split()[-1].strip(".!?;:,()[]{}").lower() if before.split() else ""
            if token in self._NO_BREAK:
                continue
            if idx > 0 and text[idx - 1].isdigit():
                continue
            if len(token) == 1 and token.isalpha():
                continue
            cuts.append(idx + 1)

        if not cuts:
            return [text.strip()] if len(text.strip()) > 25 else []

        sentences: list[str] = []
        start = 0
        for cut in cuts:
            sentences.append(text[start:cut].strip())
            start = cut
        sentences.append(text[start:].strip())
        return [sentence for sentence in sentences if len(sentence) > 25]

    def pack_to_chunks(self, sentences: list[str], max_words: int = 220, overlap: int = 2) -> list[str]:
        chunks: list[str] = []
        current: list[str] = []
        current_wc = 0

        for sentence in sentences:
            sentence_wc = len(sentence.split())
            if current and current_wc + sentence_wc > max_words:
                chunks.append(" ".join(current))
                current = current[-overlap:]
                current_wc = sum(len(item.split()) for item in current)
            current.append(sentence)
            current_wc += sentence_wc

        if current:
            chunks.append(" ".join(current))
        return chunks
