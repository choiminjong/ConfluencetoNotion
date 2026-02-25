"""GET /graph - Neo4j 그래프 시각화 데이터 반환."""

from fastapi import APIRouter, HTTPException

from graphrag.web.config import NEO4J_DB
from graphrag.web.services.rag_service import driver

router = APIRouter()


@router.get("/graph")
async def get_graph():
    try:
        with driver.session(database=NEO4J_DB) as session:
            nodes_result = session.run("""
                MATCH (n)
                WHERE n:Page OR n:Content OR n:Space OR n:Domain OR n:Topic
                RETURN
                    elementId(n) as id,
                    labels(n)[0] as label,
                    CASE
                        WHEN n:Page THEN n.title
                        WHEN n:Content THEN substring(n.chunk, 0, 50) + '...'
                        WHEN n:Space THEN n.name
                        WHEN n:Domain THEN n.name
                        WHEN n:Topic THEN n.name
                        ELSE 'Unknown'
                    END as title,
                    properties(n) as properties
            """)
            nodes = [
                {
                    "id": r["id"],
                    "label": r["label"],
                    "title": r["title"] or "No title",
                    "properties": {
                        k: v for k, v in dict(r["properties"]).items()
                        if k != "embedding"
                    },
                }
                for r in nodes_result
            ]

            edges_result = session.run("""
                MATCH (n)-[r]->(m)
                WHERE (n:Page OR n:Content OR n:Space OR n:Domain OR n:Topic)
                  AND (m:Page OR m:Content OR m:Space OR m:Domain OR m:Topic)
                RETURN
                    elementId(r) as id,
                    elementId(n) as source,
                    elementId(m) as target,
                    type(r) as relationship
            """)
            edges = [
                {
                    "id": r["id"],
                    "source": r["source"],
                    "target": r["target"],
                    "relationship": r["relationship"],
                }
                for r in edges_result
            ]

        return {"nodes": nodes, "edges": edges}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
