"""임베딩 생성 + 벡터 인덱스 관리.

Content 노드에 배치 임베딩을 생성하고 Neo4j 벡터 인덱스를 구축한다.
"""

from __future__ import annotations

import neo4j
from neo4j_graphrag.indexes import create_vector_index

BATCH_SIZE = 50
INDEX_NAME = "content_vector_index"
DIMENSION = 1536


class EmbeddingManager:
    """Content 노드 임베딩 생성과 벡터 인덱스를 관리한다."""

    def __init__(
        self,
        driver: neo4j.Driver,
        database: str,
        embedder,
        index_name: str = INDEX_NAME,
        dimension: int = DIMENSION,
        batch_size: int = BATCH_SIZE,
    ):
        self.driver = driver
        self.database = database
        self.embedder = embedder
        self.index_name = index_name
        self.dimension = dimension
        self.batch_size = batch_size

    def clear(self) -> None:
        """기존 임베딩과 벡터 인덱스를 제거한다."""
        with self.driver.session(database=self.database) as session:
            session.run(
                "MATCH (c:Content) WHERE c.embedding IS NOT NULL "
                "REMOVE c.embedding"
            )
            indexes = session.run(
                "SHOW INDEXES YIELD name, type "
                "WHERE type = 'VECTOR' RETURN name"
            ).data()
            for idx in indexes:
                session.run(f"DROP INDEX `{idx['name']}`")

        print("  기존 임베딩/인덱스 제거 완료")

    def generate(self, force: bool = False) -> int:
        """Content 노드에 임베딩을 생성하고 벡터 인덱스를 구축한다.

        Args:
            force: True이면 전체 삭제 후 재생성. False이면 미임베딩 노드만 처리.

        Returns:
            처리된 Content 노드 수.
        """
        if force:
            self.clear()

        contents = self._fetch_targets(skip_existing=not force)

        if not contents:
            print("  임베딩할 Content 노드가 없습니다.")
            self._ensure_index()
            return 0

        print(f"  총 {len(contents)}개 Content 노드에 임베딩 생성 중...")

        processed = 0
        for start in range(0, len(contents), self.batch_size):
            batch = contents[start : start + self.batch_size]
            texts = [chunk for _, chunk in batch]
            ids = [cid for cid, _ in batch]

            vectors = self._batch_embed(texts)

            write_data = [
                {"id": cid, "embedding": vec}
                for cid, vec in zip(ids, vectors)
            ]
            self._batch_write(write_data)

            processed += len(batch)
            print(f"    {processed}/{len(contents)} 완료")

        self._ensure_index()
        return len(contents)

    def _fetch_targets(self, skip_existing: bool = True) -> list[tuple[str, str]]:
        """임베딩 대상 Content 노드를 조회한다."""
        if skip_existing:
            query = (
                "MATCH (c:Content) WHERE c.embedding IS NULL "
                "RETURN c.content_id AS id, c.chunk AS chunk"
            )
        else:
            query = "MATCH (c:Content) RETURN c.content_id AS id, c.chunk AS chunk"

        with self.driver.session(database=self.database) as session:
            result = session.run(query)
            return [(r["id"], r["chunk"]) for r in result if r["chunk"]]

    def _batch_embed(self, texts: list[str]) -> list[list[float]]:
        """여러 텍스트를 한 번의 API 호출로 임베딩한다."""
        response = self.embedder.client.embeddings.create(
            input=texts, model=self.embedder.model
        )
        return [item.embedding for item in response.data]

    def _batch_write(self, batch: list[dict]) -> None:
        """UNWIND로 배치 데이터를 한 번에 Neo4j에 저장한다."""
        with self.driver.session(database=self.database) as session:
            session.run(
                "UNWIND $batch AS item "
                "MATCH (c:Content {content_id: item.id}) "
                "SET c.embedding = item.embedding",
                batch=batch,
            )

    def _ensure_index(self) -> None:
        """벡터 인덱스가 없으면 생성한다."""
        with self.driver.session(database=self.database) as session:
            indexes = session.run(
                "SHOW INDEXES YIELD name, type "
                "WHERE type = 'VECTOR' AND name = $name "
                "RETURN name",
                name=self.index_name,
            ).data()

        if not indexes:
            create_vector_index(
                driver=self.driver,
                name=self.index_name,
                label="Content",
                embedding_property="embedding",
                dimensions=self.dimension,
                similarity_fn="cosine",
            )
            print(f"  벡터 인덱스 '{self.index_name}' 생성 완료 (dimension={self.dimension})")
        else:
            print(f"  벡터 인덱스 '{self.index_name}' 이미 존재")
