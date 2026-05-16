from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, settings_dep
from core.config import Settings
from models.entity import PaperEntity
from models.paper import Chunk, Paper, ProcessingStatus
from schemas.paper_schemas import ArxivIngestRequest, PaperDetail, PaperStatusResponse, PaperSummary, PaperUploadResponse
from tasks.paper_processing import process_paper, process_paper_local

router = APIRouter(prefix="/papers", tags=["papers"])


@router.post("/upload", response_model=PaperUploadResponse)
async def upload_paper(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(settings_dep),
) -> PaperUploadResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, {"error": "Only PDF uploads are supported", "code": "INVALID_FILE", "detail": file.filename})
    upload_dir = Path(settings.uploads_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{uuid4()}_{file.filename}"
    path.write_bytes(await file.read())
    paper = Paper(title=file.filename, authors=[], pdf_path=str(path), processing_status=ProcessingStatus.pending)
    db.add(paper)
    await db.commit()
    await db.refresh(paper)
    if settings.paper_processing_mode.lower() == "celery":
        task = process_paper.delay(paper.id)
        task_id = task.id
    else:
        background_tasks.add_task(process_paper_local, paper.id)
        task_id = f"local-paper-{paper.id}"
    paper.processing_status = ProcessingStatus.processing
    await db.commit()
    return PaperUploadResponse(paper_id=paper.id, title=paper.title, status="processing", task_id=task_id)


@router.post("/arxiv", response_model=PaperUploadResponse)
async def ingest_arxiv(
    payload: ArxivIngestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(settings_dep),
) -> PaperUploadResponse:
    paper = Paper(title=f"arXiv:{payload.arxiv_id}", authors=[], arxiv_id=payload.arxiv_id, processing_status=ProcessingStatus.pending)
    db.add(paper)
    await db.commit()
    await db.refresh(paper)
    if settings.paper_processing_mode.lower() == "celery":
        task = process_paper.delay(paper.id)
        task_id = task.id
    else:
        background_tasks.add_task(process_paper_local, paper.id)
        task_id = f"local-paper-{paper.id}"
    paper.processing_status = ProcessingStatus.processing
    await db.commit()
    return PaperUploadResponse(paper_id=paper.id, title=paper.title, status="processing", task_id=task_id)


@router.get("/", response_model=list[PaperSummary])
async def list_papers(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[PaperSummary]:
    stmt = select(Paper).offset(offset).limit(limit).order_by(Paper.uploaded_at.desc())
    if status:
        stmt = stmt.where(Paper.processing_status == status)
    return list((await db.execute(stmt)).scalars().all())


@router.get("/{paper_id}", response_model=PaperDetail)
async def get_paper(paper_id: int, db: AsyncSession = Depends(get_db)) -> PaperDetail:
    paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, {"error": "Paper not found", "code": "PAPER_NOT_FOUND", "detail": str(paper_id)})
    chunks_count = await db.scalar(select(func.count()).select_from(Chunk).where(Chunk.paper_id == paper_id))
    entities_count = await db.scalar(select(func.count()).select_from(PaperEntity).where(PaperEntity.paper_id == paper_id))
    return PaperDetail(
        id=paper.id,
        title=paper.title,
        authors=paper.authors or [],
        publication_year=paper.publication_year,
        processing_status=paper.processing_status.value,
        uploaded_at=paper.uploaded_at,
        abstract=paper.abstract,
        doi=paper.doi,
        arxiv_id=paper.arxiv_id,
        pubmed_id=paper.pubmed_id,
        journal=paper.journal,
        chunks_count=chunks_count or 0,
        entities_count=entities_count or 0,
    )


@router.get("/{paper_id}/status", response_model=PaperStatusResponse)
async def get_status(paper_id: int, db: AsyncSession = Depends(get_db)) -> PaperStatusResponse:
    paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, {"error": "Paper not found", "code": "PAPER_NOT_FOUND", "detail": str(paper_id)})
    chunks_count = await db.scalar(select(func.count()).select_from(Chunk).where(Chunk.paper_id == paper_id))
    entities_count = await db.scalar(select(func.count()).select_from(PaperEntity).where(PaperEntity.paper_id == paper_id))
    return PaperStatusResponse(
        paper_id=paper_id,
        status=paper.processing_status.value,
        chunks_created=chunks_count or 0,
        entities_extracted=entities_count or 0,
        graph_built=paper.processing_status == ProcessingStatus.completed and (entities_count or 0) > 0,
    )
