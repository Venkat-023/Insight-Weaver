from neo4j import GraphDatabase

from core.config import get_settings


class KnowledgeGraphBuilder:
    def __init__(self) -> None:
        settings = get_settings()
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            connection_timeout=3,
            max_transaction_retry_time=3,
        )
        try:
            self.driver.verify_connectivity()
        except Exception as exc:
            raise RuntimeError("Neo4j unreachable") from exc
        self.setup()

    def setup(self) -> None:
        queries = [
            "CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE",
            "CREATE CONSTRAINT paper_id IF NOT EXISTS FOR (p:Paper) REQUIRE p.id IS UNIQUE",
            "CREATE INDEX entity_type_idx IF NOT EXISTS FOR (e:Entity) ON (e.type)",
        ]
        with self.driver.session() as session:
            for query in queries:
                session.run(query)

    def upsert_paper(self, paper_id: int, title: str, year: int | None, arxiv_id: str | None = None) -> None:
        with self.driver.session() as session:
            session.run(
                "MERGE (p:Paper {id: $paper_id}) SET p.title=$title, p.year=$year, p.arxiv_id=$arxiv_id",
                paper_id=paper_id,
                title=title,
                year=year,
                arxiv_id=arxiv_id,
            )

    def upsert_entity(self, name: str, entity_type: str) -> str:
        with self.driver.session() as session:
            record = session.run(
                """
                MERGE (e:Entity {name: $name})
                ON CREATE SET e.type=$entity_type, e.mention_count=1
                ON MATCH SET e.mention_count = coalesce(e.mention_count, 0) + 1
                RETURN elementId(e) AS id
                """,
                name=name,
                entity_type=entity_type,
            ).single()
            return record["id"]

    def link_paper_entity(self, paper_id: int, entity_name: str, frequency: int) -> None:
        with self.driver.session() as session:
            session.run(
                """
                MATCH (p:Paper {id: $paper_id})
                MATCH (e:Entity {name: $entity_name})
                MERGE (p)-[r:MENTIONS]->(e)
                SET r.frequency=$frequency
                """,
                paper_id=paper_id,
                entity_name=entity_name,
                frequency=frequency,
            )

    def create_relationship(self, source: str, target: str, rel_type: str, confidence: float, paper_id: int, evidence: str) -> None:
        with self.driver.session() as session:
            session.run(
                """
                MATCH (a:Entity {name: $source})
                MATCH (b:Entity {name: $target})
                MERGE (a)-[r:RELATES_TO {type: $rel_type, paper_id: $paper_id}]->(b)
                SET r.confidence=$confidence, r.evidence=$evidence
                """,
                source=source,
                target=target,
                rel_type=rel_type,
                confidence=confidence,
                paper_id=paper_id,
                evidence=evidence,
            )

    def sync_paper(
        self,
        paper_id: int,
        title: str,
        year: int | None,
        arxiv_id: str | None,
        entities: list[dict],
        relationships: list[dict],
    ) -> None:
        with self.driver.session() as session:
            session.run(
                "MERGE (p:Paper {id: $paper_id}) SET p.title=$title, p.year=$year, p.arxiv_id=$arxiv_id",
                paper_id=paper_id,
                title=title,
                year=year,
                arxiv_id=arxiv_id,
            )
            if entities:
                session.run(
                    """
                    UNWIND $entities AS entity
                    MERGE (e:Entity {name: entity.name})
                    ON CREATE SET e.type=entity.entity_type, e.mention_count=1
                    ON MATCH SET e.mention_count = coalesce(e.mention_count, 0) + 1
                    """,
                    entities=entities,
                )
                session.run(
                    """
                    MATCH (p:Paper {id: $paper_id})
                    UNWIND $entities AS entity
                    MATCH (e:Entity {name: entity.name})
                    MERGE (p)-[r:MENTIONS]->(e)
                    SET r.frequency=entity.frequency
                    """,
                    paper_id=paper_id,
                    entities=entities,
                )
            if relationships:
                session.run(
                    """
                    UNWIND $relationships AS rel
                    MATCH (a:Entity {name: rel.source})
                    MATCH (b:Entity {name: rel.target})
                    MERGE (a)-[r:RELATES_TO {type: rel.rel_type, paper_id: rel.paper_id}]->(b)
                    SET r.confidence=rel.confidence, r.evidence=rel.evidence
                    """,
                    relationships=relationships,
                )

    def get_entity_neighborhood(self, entity_name: str, max_hops: int = 2) -> dict:
        query = f"""
        MATCH path = (start:Entity {{name: $entity_name}})-[*1..{max_hops}]-(neighbor)
        RETURN path LIMIT 100
        """
        return self._paths_to_graph(query, {"entity_name": entity_name})

    def find_cross_paper_paths(self, entity_a: str, entity_b: str) -> list:
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH path = (a:Entity {name: $entity_a})-[*1..4]-(b:Entity {name: $entity_b})
                WHERE ALL(r IN relationships(path) WHERE r.paper_id IS NOT NULL)
                RETURN [r IN relationships(path) | r.paper_id] as papers_involved,
                       [n IN nodes(path) | n.name] as entity_chain,
                       length(path) as hops
                ORDER BY hops LIMIT 20
                """,
                entity_a=entity_a,
                entity_b=entity_b,
            )
            return [dict(record) for record in result]

    def export_graph_json(self, paper_ids: list[int] | None = None) -> dict:
        if paper_ids:
            query = """
            MATCH (p:Paper)-[:MENTIONS]->(e:Entity)
            WHERE p.id IN $paper_ids
            OPTIONAL MATCH (e)-[r:RELATES_TO]-(other:Entity)
            RETURN p, e, r, other LIMIT 500
            """
            params = {"paper_ids": paper_ids}
        else:
            query = "MATCH (e:Entity) OPTIONAL MATCH (e)-[r:RELATES_TO]-(other:Entity) RETURN e, r, other LIMIT 500"
            params = {}
        return self._records_to_graph(query, params)

    def _paths_to_graph(self, query: str, params: dict) -> dict:
        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        with self.driver.session() as session:
            for record in session.run(query, **params):
                for node in record["path"].nodes:
                    nodes[node.element_id] = {
                        "id": node.element_id,
                        "label": node.get("name", node.get("title", "")),
                        "type": node.get("type", "Paper"),
                        "mention_count": node.get("mention_count", 0),
                    }
                for rel in record["path"].relationships:
                    edges.append(
                        {
                            "source": rel.start_node.element_id,
                            "target": rel.end_node.element_id,
                            "type": rel.get("type", rel.type),
                            "confidence": rel.get("confidence"),
                            "paper_id": rel.get("paper_id"),
                        }
                    )
        return {"nodes": list(nodes.values()), "edges": edges}

    def _records_to_graph(self, query: str, params: dict) -> dict:
        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        with self.driver.session() as session:
            for record in session.run(query, **params):
                for key in ["p", "e", "other"]:
                    node = record.get(key)
                    if node:
                        nodes[node.element_id] = {
                            "id": node.element_id,
                            "label": node.get("name", node.get("title", "")),
                            "type": node.get("type", "Paper"),
                            "mention_count": node.get("mention_count", 0),
                            "paper_count": node.get("paper_count", 0),
                        }
                rel = record.get("r")
                if rel:
                    edges.append(
                        {
                            "source": rel.start_node.element_id,
                            "target": rel.end_node.element_id,
                            "type": rel.get("type", rel.type),
                            "confidence": rel.get("confidence"),
                            "papers": [rel.get("paper_id")] if rel.get("paper_id") else [],
                        }
                    )
        return {"nodes": list(nodes.values()), "edges": edges}
