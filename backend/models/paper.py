import enum
from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.database import Base
from models.types import JsonType


class ProcessingStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True, default="legacy", nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[list[str]] = mapped_column(JsonType, default=list)
    abstract: Mapped[str | None] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(String(100), unique=True)
    arxiv_id: Mapped[str | None] = mapped_column(String(50), unique=True)
    pubmed_id: Mapped[str | None] = mapped_column(String(50), unique=True)
    journal: Mapped[str | None] = mapped_column(String(300))
    publication_year: Mapped[int | None] = mapped_column(Integer)
    pdf_path: Mapped[str | None] = mapped_column(String(500))
    raw_text: Mapped[str | None] = mapped_column(Text)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, name="processing_status"),
        default=ProcessingStatus.pending,
        nullable=False,
    )
    uploaded_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at = mapped_column(DateTime(timezone=True), nullable=True)

    chunks: Mapped[list["Chunk"]] = relationship(back_populates="paper", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    section: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sub_index: Mapped[int] = mapped_column(Integer, default=0)
    importance_score: Mapped[float] = mapped_column(Float, default=0.5)
    chroma_embedding_id: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    word_count: Mapped[int | None] = mapped_column(Integer)

    paper: Mapped[Paper] = relationship(back_populates="chunks")
