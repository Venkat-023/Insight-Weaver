from sqlalchemy import DateTime, Float, ForeignKey, Integer, PrimaryKeyConstraint, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base
from models.types import JsonType


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("normalized_name", "entity_type", name="uq_entity_name_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True, default="legacy", nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(300), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JsonType, default=list)
    umls_cui: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text)
    paper_count: Mapped[int] = mapped_column(Integer, default=1)


class PaperEntity(Base):
    __tablename__ = "paper_entities"
    __table_args__ = (PrimaryKeyConstraint("paper_id", "entity_id"),)

    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"))
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))
    frequency: Mapped[int] = mapped_column(Integer, default=1)


class EntityRelationship(Base):
    __tablename__ = "entity_relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"))
    target_entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"))
    relationship_type: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_text: Mapped[str | None] = mapped_column(Text)
    paper_id: Mapped[int | None] = mapped_column(ForeignKey("papers.id"))
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
