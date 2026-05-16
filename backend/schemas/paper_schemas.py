from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ArxivIngestRequest(BaseModel):
    arxiv_id: str = Field(min_length=1)


class PaperUploadResponse(BaseModel):
    paper_id: int
    title: str
    status: str
    task_id: str | None = None


class PaperSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    authors: list[str] = []
    publication_year: int | None = None
    processing_status: str
    uploaded_at: datetime | None = None


class PaperDetail(PaperSummary):
    abstract: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    pubmed_id: str | None = None
    journal: str | None = None
    chunks_count: int = 0
    entities_count: int = 0


class PaperStatusResponse(BaseModel):
    paper_id: int
    status: str
    chunks_created: int
    entities_extracted: int
    graph_built: bool
