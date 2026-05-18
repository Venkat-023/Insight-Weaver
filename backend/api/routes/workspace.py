import shutil
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, get_workspace_id, settings_dep
from core.config import Settings
from models.entity import Entity, EntityRelationship, PaperEntity
from models.hypothesis import Contradiction, Hypothesis
from models.paper import Paper
from retrieval.vector_store import VectorStore

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.delete("/current")
async def reset_current_workspace(
    db: AsyncSession = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    settings: Settings = Depends(settings_dep),
) -> dict:
    paper_ids = list(
        (
            await db.execute(select(Paper.id).where(Paper.workspace_id == workspace_id))
        ).scalars().all()
    )
    entity_ids = list(
        (
            await db.execute(select(Entity.id).where(Entity.workspace_id == workspace_id))
        ).scalars().all()
    )

    if entity_ids:
        await db.execute(delete(PaperEntity).where(PaperEntity.entity_id.in_(entity_ids)))
        await db.execute(
            delete(EntityRelationship).where(
                (EntityRelationship.source_entity_id.in_(entity_ids))
                | (EntityRelationship.target_entity_id.in_(entity_ids))
            )
        )
    await db.execute(delete(Hypothesis).where(Hypothesis.workspace_id == workspace_id))
    await db.execute(delete(Contradiction).where(Contradiction.workspace_id == workspace_id))
    await db.execute(delete(Entity).where(Entity.workspace_id == workspace_id))
    await db.execute(delete(Paper).where(Paper.workspace_id == workspace_id))
    await db.commit()

    try:
        VectorStore(load_model=False).delete_workspace(workspace_id)
    except Exception:
        pass

    upload_dir = Path(settings.uploads_dir) / workspace_id
    if upload_dir.exists():
        shutil.rmtree(upload_dir, ignore_errors=True)

    return {"workspace_id": workspace_id, "papers_deleted": len(paper_ids), "entities_deleted": len(entity_ids)}
