from pydantic import BaseModel, ConfigDict, Field


class HypothesisGenerateRequest(BaseModel):
    query: str = Field(min_length=1)
    paper_ids: list[int] | None = None
    num_hypotheses: int = Field(default=5, ge=1, le=10)
    use_fast_fallback: bool = True


class HypothesisItem(BaseModel):
    id: int | None = None
    hypothesis: str
    reasoning: str
    supporting_evidence: list[dict]
    confidence: float
    novelty_score: float
    testability: str
    suggested_experiments: list[str] = []
    falsifiable_conditions: str | None = None
    research_gaps_addressed: list[str] = []
    cross_domain_insight: str | None = None


class HypothesisResult(BaseModel):
    hypotheses: list[HypothesisItem]
    meta_insights: dict = {}
    warnings: list[str] = []


class HypothesisListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hypothesis_text: str
    confidence_score: float
    novelty_score: float
    testability: str
    upvotes: int
