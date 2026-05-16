TOPIC_PAPERS = """
MATCH (p:Paper)-[:MENTIONS]->(e:Entity)
WHERE toLower(e.name) CONTAINS toLower($topic)
RETURN p.id AS paper_id, p.title AS title, p.year AS year
ORDER BY p.year
"""
