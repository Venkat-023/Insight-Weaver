from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from graph.graph_builder import KnowledgeGraphBuilder
from models.entity import Entity, EntityRelationship, PaperEntity
from models.paper import Paper

router = APIRouter(prefix="/graph", tags=["graph"])


def _builder() -> KnowledgeGraphBuilder:
    try:
        return KnowledgeGraphBuilder()
    except RuntimeError as exc:
        raise HTTPException(503, {"error": "Neo4j unavailable", "code": "GRAPH_UNAVAILABLE", "detail": str(exc)}) from exc


@router.get("/entity/{entity_name}")
async def graph_for_entity(
    entity_name: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        graph = _builder().get_entity_neighborhood(entity_name, 2)
        if graph.get("nodes"):
            return graph
    except Exception:
        pass
    return await _entity_graph_from_postgres(entity_name, db)


@router.get("/{paper_id}")
async def graph_for_paper(
    paper_id: int,
    include_neighbors: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        graph = _builder().export_graph_json([paper_id])
        if graph.get("nodes"):
            return graph
    except Exception:
        pass
    return await _paper_graph_from_postgres(paper_id, db)


async def _paper_graph_from_postgres(paper_id: int, db: AsyncSession) -> dict:
    paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, {"error": "Paper not found", "code": "PAPER_NOT_FOUND", "detail": str(paper_id)})

    rows = await db.execute(
        select(Entity, PaperEntity.frequency)
        .join(PaperEntity, PaperEntity.entity_id == Entity.id)
        .where(PaperEntity.paper_id == paper_id)
        .order_by(PaperEntity.frequency.desc(), Entity.name)
        .limit(80)
    )
    entity_rows = rows.all()
    paper_node_id = f"paper-{paper.id}"
    nodes = [
        {
            "id": paper_node_id,
            "label": paper.title,
            "type": "Paper",
            "paper_count": 1,
        }
    ]
    edges = []
    for entity, frequency in entity_rows:
        entity_node_id = f"entity-{entity.id}"
        nodes.append(
            {
                "id": entity_node_id,
                "label": entity.name,
                "type": entity.entity_type,
                "mention_count": frequency,
                "paper_count": entity.paper_count,
            }
        )
        edges.append(
            {
                "source": paper_node_id,
                "target": entity_node_id,
                "type": "MENTIONS",
                "paper_id": paper.id,
            }
        )
    return {"nodes": nodes, "edges": edges}


async def _entity_graph_from_postgres(entity_name: str, db: AsyncSession) -> dict:
    normalized = " ".join(entity_name.lower().split())
    rows = await db.execute(
        select(Entity)
        .where(
            or_(
                func.lower(Entity.name) == normalized,
                Entity.normalized_name == normalized,
                Entity.name.ilike(f"%{entity_name}%"),
            )
        )
        .order_by(Entity.paper_count.desc(), Entity.name)
        .limit(8)
    )
    seed_entities = list(rows.scalars().all())
    if not seed_entities:
        return {"nodes": [], "edges": []}

    seed_ids = [entity.id for entity in seed_entities]
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def add_entity_node(entity: Entity, mention_count: int | None = None) -> str:
        node_id = f"entity-{entity.id}"
        existing = nodes.get(node_id, {})
        nodes[node_id] = {
            "id": node_id,
            "label": entity.name,
            "type": entity.entity_type,
            "mention_count": mention_count if mention_count is not None else existing.get("mention_count", 0),
            "paper_count": entity.paper_count,
        }
        return node_id

    for entity in seed_entities:
        add_entity_node(entity)

    paper_rows = await db.execute(
        select(Paper, PaperEntity.entity_id, PaperEntity.frequency)
        .join(PaperEntity, PaperEntity.paper_id == Paper.id)
        .where(PaperEntity.entity_id.in_(seed_ids))
        .order_by(PaperEntity.frequency.desc(), Paper.title)
        .limit(24)
    )
    paper_ids: list[int] = []
    for paper, entity_id, frequency in paper_rows.all():
        paper_ids.append(paper.id)
        paper_node_id = f"paper-{paper.id}"
        nodes[paper_node_id] = {
            "id": paper_node_id,
            "label": paper.title,
            "type": "Paper",
            "year": paper.publication_year,
            "paper_count": 1,
        }
        edges.append(
            {
                "source": paper_node_id,
                "target": f"entity-{entity_id}",
                "type": "MENTIONS",
                "frequency": frequency,
                "paper_id": paper.id,
            }
        )

    rel_rows = await db.execute(
        select(EntityRelationship, Entity)
        .join(
            Entity,
            or_(
                Entity.id == EntityRelationship.source_entity_id,
                Entity.id == EntityRelationship.target_entity_id,
            ),
        )
        .where(
            or_(
                EntityRelationship.source_entity_id.in_(seed_ids),
                EntityRelationship.target_entity_id.in_(seed_ids),
            ),
            ~Entity.id.in_(seed_ids),
        )
        .order_by(EntityRelationship.confidence.desc())
        .limit(40)
    )
    for rel, neighbor in rel_rows.all():
        add_entity_node(neighbor)
        source_id = f"entity-{rel.source_entity_id}"
        target_id = f"entity-{rel.target_entity_id}"
        if source_id not in nodes or target_id not in nodes:
            continue
        edges.append(
            {
                "source": source_id,
                "target": target_id,
                "type": rel.relationship_type,
                "confidence": rel.confidence,
                "paper_id": rel.paper_id,
                "evidence": rel.evidence_text,
            }
        )

    if paper_ids:
        co_rows = await db.execute(
            select(Entity, PaperEntity.paper_id, PaperEntity.frequency)
            .join(PaperEntity, PaperEntity.entity_id == Entity.id)
            .where(PaperEntity.paper_id.in_(paper_ids), ~Entity.id.in_(seed_ids))
            .order_by(PaperEntity.frequency.desc(), Entity.paper_count.desc())
            .limit(48)
        )
        for entity, paper_id, frequency in co_rows.all():
            entity_node_id = add_entity_node(entity, frequency)
            paper_node_id = f"paper-{paper_id}"
            if paper_node_id in nodes:
                edges.append(
                    {
                        "source": paper_node_id,
                        "target": entity_node_id,
                        "type": "MENTIONS",
                        "frequency": frequency,
                        "paper_id": paper_id,
                    }
                )

    return {"nodes": list(nodes.values()), "edges": edges}
