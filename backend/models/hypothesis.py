from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base
from models.types import JsonType


class Hypothesis(Base):
    __tablename__ = "hypotheses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True, default="legacy", nullable=False)
    hypothesis_text: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    novelty_score: Mapped[float] = mapped_column(Float, nullable=False)
    testability: Mapped[str] = mapped_column(String(20), nullable=False)
    supporting_paper_ids: Mapped[list[int]] = mapped_column(JsonType, default=list)
    supporting_evidence: Mapped[list[dict]] = mapped_column(JsonType, default=list)
    suggested_experiments: Mapped[list[str]] = mapped_column(JsonType, default=list)
    research_gaps_addressed: Mapped[list[str]] = mapped_column(JsonType, default=list)
    cross_domain_insights: Mapped[list[str]] = mapped_column(JsonType, default=list)
    query_context: Mapped[str | None] = mapped_column(Text)
    upvotes: Mapped[int] = mapped_column(Integer, default=0)
    agent_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())


class Contradiction(Base):
    __tablename__ = "contradictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True, default="legacy", nullable=False)
    paper_a_id: Mapped[int] = mapped_column(ForeignKey("papers.id"))
    paper_b_id: Mapped[int] = mapped_column(ForeignKey("papers.id"))
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    contradiction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    paper_a_claim: Mapped[str | None] = mapped_column(Text)
    paper_b_claim: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    resolution_suggestion: Mapped[str | None] = mapped_column(Text)
    topic: Mapped[str | None] = mapped_column(String(500))
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
