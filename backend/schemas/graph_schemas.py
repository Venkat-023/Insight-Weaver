from pydantic import BaseModel


class GraphNode(BaseModel):
    id: str | int
    label: str
    type: str | None = None
    mention_count: int | None = None
    paper_count: int | None = None


class GraphEdge(BaseModel):
    source: str | int
    target: str | int
    type: str
    confidence: float | None = None
    paper_id: int | None = None
    papers: list[int] | None = None


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
