from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    paper_ids: list[int] | None = None
    n_results: int = 15
    section_filter: str | None = None


class SearchResultSchema(BaseModel):
    id: str
    text: str
    metadata: dict
    similarity_score: float


class SearchResponse(BaseModel):
    results: list[SearchResultSchema]
    total: int
    query_time_ms: int


class GraphRAGRequest(BaseModel):
    query: str = Field(min_length=1)
    paper_ids: list[int] | None = None
    n_results: int = Field(default=8, ge=1, le=20)
    include_graph: bool = True
    use_vector: bool = False
    use_gemma: bool = False
    max_model_seconds: int = Field(default=6, ge=3, le=30)


class GraphRAGResponse(BaseModel):
    answer: str
    model: str
    warnings: list[str] = []
    results: list[SearchResultSchema]
    graph_context: dict
    query_time_ms: int
