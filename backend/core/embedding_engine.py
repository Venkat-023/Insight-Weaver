from functools import lru_cache


class EmbeddingEngine:
    def __init__(self, model_name: str = "BAAI/bge-large-en-v1.5") -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)

    @lru_cache(maxsize=4096)
    def embed_text(self, text: str) -> tuple[float, ...]:
        vector = self.model.encode(text, normalize_embeddings=True)
        return tuple(float(v) for v in vector)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(texts, normalize_embeddings=True, batch_size=32)
        return [[float(v) for v in vector] for vector in vectors]
