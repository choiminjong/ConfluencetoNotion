"""임베딩 생성 + 벡터 인덱스 관리.

Content 노드에 임베딩을 생성하고 Neo4j 벡터 인덱스를 구축한다.
"""

from __future__ import annotations

import neo4j
from neo4j_graphrag.indexes import create_vector_index


def clear_existing_embeddings(driver: neo4j.Driver, database: str) -> None:
    """기존 임베딩과 벡터 인덱스를 제거한다."""
    with driver.session(database=database) as session:
        session.run("MATCH (c:Content) WHERE c.embedding IS NOT NULL REMOVE c.embedding")

        indexes = session.run("SHOW INDEXES YIELD name, type WHERE type = 'VECTOR' RETURN name").data()
        for idx in indexes:
            session.run(f"DROP INDEX `{idx['name']}`")

    print("  기존 임베딩/인덱스 제거 완료")


def generate_embeddings(
    driver: neo4j.Driver,
    database: str,
    embedder,
    index_name: str = "content_vector_index",
    dimension: int = 1536,
) -> int:
    """모든 Content 노드에 임베딩을 생성하고 벡터 인덱스를 구축한다."""

    with driver.session(database=database) as session:
        result = session.run("MATCH (c:Content) RETURN c.content_id AS id, c.chunk AS chunk")
        contents = [(r["id"], r["chunk"]) for r in result]

    print(f"  총 {len(contents)}개 Content 노드에 임베딩 생성 중...")

    for i, (content_id, chunk) in enumerate(contents, 1):
        if not chunk:
            continue

        embedding = embedder.embed_query(chunk)

        with driver.session(database=database) as session:
            session.run(
                "MATCH (c:Content {content_id: $id}) SET c.embedding = $embedding",
                id=content_id,
                embedding=embedding,
            )

        if i % 10 == 0 or i == len(contents):
            print(f"    {i}/{len(contents)} 완료")

    create_vector_index(
        driver=driver,
        name=index_name,
        label="Content",
        embedding_property="embedding",
        dimensions=dimension,
        similarity_fn="cosine",
    )
    print(f"  벡터 인덱스 '{index_name}' 생성 완료 (dimension={dimension})")

    return len(contents)
