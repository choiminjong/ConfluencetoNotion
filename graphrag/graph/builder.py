"""Neo4j 그래프 빌더.

Excel 데이터를 읽어 Page, Content, Space, Domain, Topic 노드와
HAS_CHUNK, BELONGS_TO, IN_SPACE, HAS_TOPIC, CHILD_OF 관계를 생성한다.
"""

from __future__ import annotations

from neo4j import GraphDatabase

from graphrag.graph.chunker import recursive_chunk_text


class GraphBuilder:
    """Neo4j 그래프를 구축한다."""

    def __init__(self, uri: str, auth: tuple[str, str], database: str = "neo4j"):
        self.driver = GraphDatabase.driver(uri, auth=auth)
        self.database = database

    def close(self):
        self.driver.close()

    def _run(self, query: str, **params):
        with self.driver.session(database=self.database) as session:
            return session.run(query, **params)

    def clear_database(self):
        """기존 데이터를 모두 삭제한다."""
        self._run("MATCH (n) DETACH DELETE n")
        print("  기존 데이터 삭제 완료")

    def create_constraints(self):
        """Unique 제약조건을 생성한다."""
        constraints = [
            ("Page", "page_id"),
            ("Content", "content_id"),
            ("Space", "name"),
            ("Domain", "name"),
            ("Topic", "name"),
        ]
        for label, prop in constraints:
            self._run(
                f"CREATE CONSTRAINT IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
            )
        print("  제약조건 생성 완료")

    def create_page_node(self, row: dict) -> None:
        """Page 노드를 생성한다."""
        self._run(
            """
            MERGE (p:Page {page_id: $page_id})
            SET p.title = $title,
                p.source_url = $source_url,
                p.updated = $updated,
                p.status = $status
            """,
            page_id=row["page_id"],
            title=row.get("title", ""),
            source_url=row.get("source_url", ""),
            updated=row.get("updated", ""),
            status=row.get("status", ""),
        )

    def create_content_nodes(
        self, page_id: str, title: str, content: str, chunk_size: int = 500, overlap: int = 100
    ) -> int:
        """Page의 본문을 청킹하여 Content 노드를 생성하고 HAS_CHUNK 관계를 연결한다."""
        if not content or not content.strip():
            return 0

        chunks = recursive_chunk_text(content, chunk_size=chunk_size, overlap=overlap)

        for i, chunk in enumerate(chunks):
            content_id = f"{page_id}_chunk_{i}"
            self._run(
                """
                MERGE (c:Content {content_id: $content_id})
                SET c.chunk = $chunk,
                    c.chunk_index = $chunk_index,
                    c.page_id = $page_id,
                    c.title = $title
                WITH c
                MATCH (p:Page {page_id: $page_id})
                MERGE (p)-[:HAS_CHUNK]->(c)
                """,
                content_id=content_id,
                chunk=chunk,
                chunk_index=i,
                page_id=page_id,
                title=title,
            )

        return len(chunks)

    def create_space_relationship(self, page_id: str, space_name: str) -> None:
        """Space 노드를 생성하고 IN_SPACE 관계를 연결한다."""
        if not space_name:
            return
        self._run(
            """
            MERGE (s:Space {name: $space_name})
            WITH s
            MATCH (p:Page {page_id: $page_id})
            MERGE (p)-[:IN_SPACE]->(s)
            """,
            page_id=page_id,
            space_name=space_name,
        )

    def create_domain_relationship(self, page_id: str, domain_name: str) -> None:
        """Domain 노드를 생성하고 BELONGS_TO 관계를 연결한다."""
        if not domain_name:
            return
        self._run(
            """
            MERGE (d:Domain {name: $domain_name})
            WITH d
            MATCH (p:Page {page_id: $page_id})
            MERGE (p)-[:BELONGS_TO]->(d)
            """,
            page_id=page_id,
            domain_name=domain_name,
        )

    def create_topic_relationships(self, page_id: str, topics_str: str) -> None:
        """Topics 문자열을 파싱하여 Topic 노드와 HAS_TOPIC 관계를 생성한다."""
        if not topics_str:
            return
        for topic in topics_str.split(","):
            topic = topic.strip()
            if not topic:
                continue
            self._run(
                """
                MERGE (t:Topic {name: $topic_name})
                WITH t
                MATCH (p:Page {page_id: $page_id})
                MERGE (p)-[:HAS_TOPIC]->(t)
                """,
                page_id=page_id,
                topic_name=topic,
            )

    def create_child_of_relationships(self, records: list[dict]) -> None:
        """Parent Title 기반으로 CHILD_OF 관계를 생성한다."""
        title_to_id: dict[str, str] = {}
        for r in records:
            title = r.get("title", "")
            if title:
                title_to_id[title] = r["page_id"]

        for r in records:
            parent_title = r.get("parent_title", "")
            if parent_title and parent_title in title_to_id:
                self._run(
                    """
                    MATCH (child:Page {page_id: $child_id})
                    MATCH (parent:Page {page_id: $parent_id})
                    MERGE (child)-[:CHILD_OF]->(parent)
                    """,
                    child_id=r["page_id"],
                    parent_id=title_to_id[parent_title],
                )

    def build_graph(self, records: list[dict]) -> dict:
        """전체 그래프를 구축하고 통계를 반환한다."""
        total_chunks = 0

        for i, row in enumerate(records, 1):
            page_id = row["page_id"]
            title = row.get("title", "Untitled")
            print(f"  ({i}/{len(records)}) {title}")

            self.create_page_node(row)

            chunks = self.create_content_nodes(
                page_id=page_id,
                title=title,
                content=row.get("content", ""),
            )
            total_chunks += chunks

            self.create_space_relationship(page_id, row.get("space", ""))
            self.create_domain_relationship(page_id, row.get("domain", ""))
            self.create_topic_relationships(page_id, row.get("topics", ""))

        print("\n  부모-자식 관계 생성 중...")
        self.create_child_of_relationships(records)

        return {"pages": len(records), "chunks": total_chunks}

    def get_stats(self) -> dict:
        """그래프 노드/관계 수를 조회한다."""
        with self.driver.session(database=self.database) as session:
            node_result = session.run("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt")
            nodes = {r["label"]: r["cnt"] for r in node_result}

            rel_result = session.run("MATCH ()-[r]->() RETURN type(r) AS rtype, count(r) AS cnt")
            rels = {r["rtype"]: r["cnt"] for r in rel_result}

        return {"nodes": nodes, "relationships": rels}
