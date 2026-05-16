from core.gemma_engine import GemmaEngine


class ContradictionDetector:
    def __init__(self, gemma: GemmaEngine | None = None) -> None:
        self.gemma = gemma or GemmaEngine()

    def detect(self, text_a: str, text_b: str, topic: str) -> dict:
        return self.gemma.detect_contradiction(text_a, text_b, topic)
