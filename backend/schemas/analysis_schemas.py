from pydantic import BaseModel, Field


class ContradictionRequest(BaseModel):
    topic: str = Field(min_length=1)
    paper_ids: list[int] = Field(min_length=2)


class ConnectionsRequest(BaseModel):
    paper_id: int


class LandscapeRequest(BaseModel):
    topic: str = Field(min_length=1)


class ContradictionSchema(BaseModel):
    paper_a_id: int
    paper_b_id: int
    severity: str
    contradiction_type: str
    paper_a_claim: str | None = None
    paper_b_claim: str | None = None
    explanation: str | None = None
    resolution_suggestion: str | None = None
    topic: str | None = None


class UnexploredConnectionSchema(BaseModel):
    source_paper_id: int
    target_paper_id: int
    target_paper_title: str
    similarity_score: float
    connection_score: float
    source_excerpt: str
    target_excerpt: str
    shared_concepts: list[str]
