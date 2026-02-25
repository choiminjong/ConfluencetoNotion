"""그래프 시각화 데이터 API.

GET /graph          -- semantic(기본) 또는 full 모드로 전체 그래프 반환
GET /graph/expand   -- 특정 Page의 Content 청크를 동적으로 반환
GET /similar        -- 임베딩 기반 유사 페이지 추천
GET /analytics      -- 그래프 통계 (degree, 분포 등)
"""

from fastapi import APIRouter, HTTPException, Query

from graphrag.web.config import NEO4J_DB
from graphrag.web.services.rag_service import driver

router = APIRouter()

_SEMANTIC_LABELS = ["Page", "Domain", "Topics", "Space", "Status"]
_NOISE_RELS = {"HAS_CHUNK", "NEXT_CHUNK"}


def _node_title(record) -> str:
    label = record["label"]
    if label == "Page":
        return record["raw_title"] or "No title"
    if label == "Content":
        chunk = record.get("raw_chunk") or ""
        return chunk[:50] + "..." if len(chunk) > 50 else chunk or "..."
    return record.get("raw_name") or "Unknown"


def _clean_props(props: dict) -> dict:
    return {k: v for k, v in props.items() if k != "embedding"}


@router.get("/graph")
async def get_graph(mode: str = Query("semantic", pattern="^(semantic|full)$")):
    """그래프 노드/엣지를 반환한다.

    mode=semantic  Page·Domain·Topics·Space·Status만 (Content 제외)
    mode=full      모든 노드 포함
    """
    try:
        with driver.session(database=NEO4J_DB) as session:
            if mode == "semantic":
                label_filter = " OR ".join(f"n:{l}" for l in _SEMANTIC_LABELS)
                nodes_result = session.run(f"""
                    MATCH (n) WHERE {label_filter}
                    RETURN elementId(n) AS id, labels(n)[0] AS label,
                           n.title AS raw_title, n.name AS raw_name,
                           properties(n) AS properties
                """)
            else:
                nodes_result = session.run("""
                    MATCH (n)
                    WHERE n:Page OR n:Content OR n:Space OR n:Domain
                          OR n:Topics OR n:Status
                    RETURN elementId(n) AS id, labels(n)[0] AS label,
                           n.title AS raw_title, n.name AS raw_name,
                           n.chunk AS raw_chunk,
                           properties(n) AS properties
                """)

            nodes = []
            for r in nodes_result:
                nodes.append({
                    "id": r["id"],
                    "label": r["label"],
                    "title": _node_title(r),
                    "properties": _clean_props(dict(r["properties"])),
                })

            if mode == "semantic":
                edges_result = session.run(f"""
                    MATCH (n)-[r]->(m)
                    WHERE ({" OR ".join(f"n:{l}" for l in _SEMANTIC_LABELS)})
                      AND ({" OR ".join(f"m:{l}" for l in _SEMANTIC_LABELS)})
                      AND NOT type(r) IN $noise
                    RETURN elementId(r) AS id,
                           elementId(n) AS source,
                           elementId(m) AS target,
                           type(r) AS relationship
                """, noise=list(_NOISE_RELS))
            else:
                edges_result = session.run("""
                    MATCH (n)-[r]->(m)
                    RETURN elementId(r) AS id,
                           elementId(n) AS source,
                           elementId(m) AS target,
                           type(r) AS relationship
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

        page_count = sum(1 for n in nodes if n["label"] == "Page")
        return {"nodes": nodes, "edges": edges, "page_count": page_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph/expand/{page_id}")
async def expand_page(page_id: str):
    """특정 Page의 Content 청크 노드와 관계를 반환한다."""
    try:
        with driver.session(database=NEO4J_DB) as session:
            chunks_result = session.run("""
                MATCH (p:Page {page_id: $pid})-[:HAS_CHUNK]->(c:Content)
                RETURN elementId(c) AS id, labels(c)[0] AS label,
                       c.chunk AS chunk, c.heading_path AS heading_path,
                       c.content_type AS content_type,
                       c.chunk_index AS chunk_index,
                       properties(c) AS properties
                ORDER BY c.chunk_index
            """, pid=page_id)

            nodes = []
            for r in chunks_result:
                chunk_text = r["chunk"] or ""
                nodes.append({
                    "id": r["id"],
                    "label": "Content",
                    "title": chunk_text[:50] + "..." if len(chunk_text) > 50 else chunk_text,
                    "properties": _clean_props(dict(r["properties"])),
                })

            edges_result = session.run("""
                MATCH (p:Page {page_id: $pid})-[r:HAS_CHUNK]->(c:Content)
                RETURN elementId(r) AS id,
                       elementId(p) AS source,
                       elementId(c) AS target,
                       'HAS_CHUNK' AS relationship
            """, pid=page_id)

            edges = [
                {"id": r["id"], "source": r["source"],
                 "target": r["target"], "relationship": r["relationship"]}
                for r in edges_result
            ]

            next_result = session.run("""
                MATCH (p:Page {page_id: $pid})-[:HAS_CHUNK]->(c1:Content)
                      -[r:NEXT_CHUNK]->(c2:Content)
                RETURN elementId(r) AS id,
                       elementId(c1) AS source,
                       elementId(c2) AS target,
                       'NEXT_CHUNK' AS relationship
            """, pid=page_id)

            for r in next_result:
                edges.append({
                    "id": r["id"], "source": r["source"],
                    "target": r["target"], "relationship": r["relationship"],
                })

        return {"nodes": nodes, "edges": edges}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/similar/{page_id}")
async def get_similar(page_id: str, top_k: int = Query(5, ge=1, le=20)):
    """임베딩 기반으로 유사한 Page를 추천한다."""
    try:
        with driver.session(database=NEO4J_DB) as session:
            result = session.run("""
                MATCH (p:Page {page_id: $pid})-[:HAS_CHUNK]->(c:Content)
                WHERE c.embedding IS NOT NULL
                WITH p, collect(c.embedding) AS embeddings
                WHERE size(embeddings) > 0
                WITH p,
                     [i IN range(0, size(embeddings[0])-1) |
                      reduce(s=0.0, e IN embeddings | s + e[i]) / size(embeddings)
                     ] AS avg_embedding
                CALL db.index.vector.queryNodes('content_vector_index', $k * 3, avg_embedding)
                YIELD node AS similar_content, score
                MATCH (similar_content)<-[:HAS_CHUNK]-(similar_page:Page)
                WHERE similar_page.page_id <> $pid
                RETURN DISTINCT similar_page.page_id AS page_id,
                       similar_page.title AS title,
                       similar_page.source_url AS source_url,
                       max(score) AS score
                ORDER BY score DESC
                LIMIT $k
            """, pid=page_id, k=top_k)

            similar = [
                {
                    "page_id": r["page_id"],
                    "title": r["title"],
                    "source_url": r["source_url"],
                    "score": round(r["score"], 4),
                }
                for r in result
            ]

        return {"page_id": page_id, "similar": similar}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics")
async def get_analytics():
    """그래프 통계 정보를 반환한다."""
    try:
        with driver.session(database=NEO4J_DB) as session:
            node_counts = session.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt"
            )
            node_stats = {r["label"]: r["cnt"] for r in node_counts}

            rel_counts = session.run(
                "MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS cnt"
            )
            rel_stats = {r["rel"]: r["cnt"] for r in rel_counts}

            degree_result = session.run("""
                MATCH (p:Page)
                OPTIONAL MATCH (p)-[r]-()
                WITH p, count(r) AS degree
                RETURN p.page_id AS page_id, p.title AS title, degree
                ORDER BY degree DESC
            """)
            page_degrees = [
                {"page_id": r["page_id"], "title": r["title"], "degree": r["degree"]}
                for r in degree_result
            ]

            orphan_result = session.run("""
                MATCH (p:Page)
                WHERE NOT (p)-[:CHILD_OF]->() AND NOT (p)<-[:CHILD_OF]-()
                      AND NOT (p)-[:HAS_TOPICS]->()
                RETURN p.page_id AS page_id, p.title AS title
            """)
            orphans = [
                {"page_id": r["page_id"], "title": r["title"]}
                for r in orphan_result
            ]

            topic_dist = session.run("""
                MATCH (t:Topics)<-[:HAS_TOPICS]-(p:Page)
                RETURN t.name AS topic, count(p) AS count
                ORDER BY count DESC
            """)
            topics = [
                {"name": r["topic"], "count": r["count"]}
                for r in topic_dist
            ]

            domain_dist = session.run("""
                MATCH (d:Domain)<-[:HAS_DOMAIN]-(p:Page)
                RETURN d.name AS domain, count(p) AS count
                ORDER BY count DESC
            """)
            domains = [
                {"name": r["domain"], "count": r["count"]}
                for r in domain_dist
            ]

        return {
            "node_counts": node_stats,
            "relationship_counts": rel_stats,
            "page_degrees": page_degrees,
            "orphan_pages": orphans,
            "topic_distribution": topics,
            "domain_distribution": domains,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
