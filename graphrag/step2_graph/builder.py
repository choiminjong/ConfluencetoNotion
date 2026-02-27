"""Neo4j 그래프 빌더.

DB 스키마를 기반으로 Page, Content 노드와 select/multi_select 필드에 대한
동적 노드·관계를 생성한다. 섹션 기반 청킹과 NEXT_CHUNK 순서 관계를 지원한다.
"""

from __future__ import annotations

import re

from neo4j import GraphDatabase

from graphrag.graph.chunker import TextChunker

SKIP_FIELDS = {"Status", "Space"}
CHILD_OF_FIELDS = {"Parent Title"}


class GraphBuilder:
    """스키마 기반으로 Neo4j 그래프를 구축한다."""

    def __init__(
        self,
        uri: str,
        auth: tuple[str, str],
        database: str = "neo4j",
        schema: dict[str, str] | None = None,
    ):
        self.driver = GraphDatabase.driver(uri, auth=auth)
        self.database = database
        self.schema = schema or {}
        self.chunker = TextChunker()

    def close(self):
        self.driver.close()

    def _run(self, query: str, **params):
        with self.driver.session(database=self.database) as session:
            return session.run(query, **params)

    def _sanitize_label(self, name: str) -> str:
        """필드명을 Neo4j label로 변환한다."""
        label = name.replace(" ", "_").replace("-", "_")
        return re.sub(r"[^A-Za-z0-9_\uAC00-\uD7A3]", "", label)

    def _to_property_key(self, name: str) -> str:
        """필드명을 Neo4j 속성 키로 변환한다."""
        key = name.lower().replace(" ", "_").replace("-", "_")
        return re.sub(r"[^a-z0-9_]", "", key)

    def clear_database(self):
        """기존 데이터를 모두 삭제한다."""
        self._run("MATCH (n) DETACH DELETE n")
        print("  기존 데이터 삭제 완료")

    def create_constraints(self):
        """스키마 기반으로 Unique 제약조건을 생성한다."""
        base_constraints = [
            ("Page", "page_id"),
            ("Content", "content_id"),
        ]
        for label, prop in base_constraints:
            self._run(
                f"CREATE CONSTRAINT IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
            )

        for field_name, field_type in self.schema.items():
            if field_name in SKIP_FIELDS:
                continue
            if field_type in ("select", "multi_select"):
                label = self._sanitize_label(field_name)
                self._run(
                    f"CREATE CONSTRAINT IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.name IS UNIQUE"
                )

        print("  제약조건 생성 완료")

    def create_page_node(self, row: dict) -> None:
        """Page 노드를 생성한다. SKIP_FIELDS·CHILD_OF_FIELDS·select/multi_select를 제외한 속성을 저장."""
        properties = row.get("properties", {})
        excluded = SKIP_FIELDS | CHILD_OF_FIELDS
        extra_props: dict[str, str] = {}

        for field_name, field_type in self.schema.items():
            if field_name in excluded:
                continue
            if field_type not in ("select", "multi_select"):
                key = self._to_property_key(field_name)
                value = properties.get(field_name, "")
                extra_props[key] = value if value is not None else ""

        extra_props["last_edited"] = row.get("last_edited_time", "")

        self._run(
            """
            MERGE (p:Page {page_id: $page_id})
            SET p.title = $title, p += $extra_props
            """,
            page_id=row["page_id"],
            title=row.get("title", ""),
            extra_props=extra_props,
        )

    def create_select_relationship(
        self, page_id: str, field_name: str, value: str,
    ) -> None:
        """select 필드에 대해 노드와 관계를 생성한다."""
        if not value:
            return
        label = self._sanitize_label(field_name)
        rel_type = f"HAS_{label.upper()}"
        self._run(
            f"""
            MERGE (n:{label} {{name: $value}})
            WITH n
            MATCH (p:Page {{page_id: $page_id}})
            MERGE (p)-[:{rel_type}]->(n)
            """,
            page_id=page_id,
            value=value,
        )

    def create_multi_select_relationships(
        self, page_id: str, field_name: str, values_str: str,
    ) -> None:
        """multi_select 필드에 대해 각 값마다 노드와 관계를 생성한다."""
        if not values_str:
            return
        label = self._sanitize_label(field_name)
        rel_type = f"HAS_{label.upper()}"
        for value in values_str.split(","):
            value = value.strip()
            if not value:
                continue
            self._run(
                f"""
                MERGE (n:{label} {{name: $value}})
                WITH n
                MATCH (p:Page {{page_id: $page_id}})
                MERGE (p)-[:{rel_type}]->(n)
                """,
                page_id=page_id,
                value=value,
            )

    def create_content_nodes(
        self,
        page_id: str,
        title: str,
        content: str,
        sections: list[dict] | None = None,
    ) -> int:
        """H2 그룹핑 기반 청킹으로 Content 노드를 생성하고 HAS_CHUNK·NEXT_CHUNK 관계를 연결한다."""
        has_section_content = sections and any(
            s.get("text", "").strip() for s in sections
        )
        if has_section_content:
            chunks = self.chunker.chunk_sections(sections, title)
        elif content and content.strip():
            raw = self.chunker.recursive_chunk(
                self.chunker.clean_text(content),
            )
            chunks = [
                {"text": c, "heading_path": [], "content_type": "text", "page_title": title}
                for c in raw
            ]
        else:
            return 0

        chunks = [c for c in chunks if len(c.get("text", "")) >= 100]
        if not chunks:
            return 0

        for i, chunk_data in enumerate(chunks):
            content_id = f"{page_id}_chunk_{i}"
            heading_path_str = " > ".join(chunk_data.get("heading_path", []))
            self._run(
                """
                MERGE (c:Content {content_id: $content_id})
                SET c.chunk = $chunk,
                    c.chunk_index = $chunk_index,
                    c.page_id = $page_id,
                    c.title = $title,
                    c.heading_path = $heading_path,
                    c.content_type = $content_type
                WITH c
                MATCH (p:Page {page_id: $page_id})
                MERGE (p)-[:HAS_CHUNK]->(c)
                """,
                content_id=content_id,
                chunk=chunk_data["text"],
                chunk_index=i,
                page_id=page_id,
                title=title,
                heading_path=heading_path_str,
                content_type=chunk_data.get("content_type", "text"),
            )

        if len(chunks) > 1:
            for i in range(len(chunks) - 1):
                self._run(
                    """
                    MATCH (a:Content {content_id: $from_id})
                    MATCH (b:Content {content_id: $to_id})
                    MERGE (a)-[:NEXT_CHUNK]->(b)
                    """,
                    from_id=f"{page_id}_chunk_{i}",
                    to_id=f"{page_id}_chunk_{i + 1}",
                )

        return len(chunks)

    def create_child_of_relationships(self, records: list[dict]) -> None:
        """CHILD_OF_FIELDS의 값이 다른 페이지 title과 일치하면 CHILD_OF 관계를 생성한다."""
        title_to_id: dict[str, str] = {}
        for r in records:
            title = r.get("title", "")
            if title:
                title_to_id[title] = r["page_id"]

        for r in records:
            properties = r.get("properties", {})
            for field_name in CHILD_OF_FIELDS:
                value = properties.get(field_name, "")
                if value and value in title_to_id and title_to_id[value] != r["page_id"]:
                    self._run(
                        """
                        MATCH (child:Page {page_id: $child_id})
                        MATCH (parent:Page {page_id: $parent_id})
                        MERGE (child)-[:CHILD_OF]->(parent)
                        """,
                        child_id=r["page_id"],
                        parent_id=title_to_id[value],
                    )

    def build_graph(self, records: list[dict]) -> dict:
        """전체 그래프를 구축하고 통계를 반환한다."""
        total_chunks = 0

        for i, row in enumerate(records, 1):
            page_id = row["page_id"]
            title = row.get("title", "Untitled")
            properties = row.get("properties", {})
            print(f"  ({i}/{len(records)}) {title}")

            self.create_page_node(row)

            chunks = self.create_content_nodes(
                page_id=page_id,
                title=title,
                content=row.get("content", ""),
                sections=row.get("sections"),
            )
            total_chunks += chunks

            for field_name, field_type in self.schema.items():
                if field_name in SKIP_FIELDS:
                    continue
                value = properties.get(field_name, "")
                if not value:
                    continue
                if field_type == "select":
                    self.create_select_relationship(page_id, field_name, value)
                elif field_type == "multi_select":
                    self.create_multi_select_relationships(page_id, field_name, value)

        print("\n  부모-자식 관계 생성 중...")
        self.create_child_of_relationships(records)

        return {"pages": len(records), "chunks": total_chunks}

    def get_stats(self) -> dict:
        """그래프 노드/관계 수를 조회한다."""
        with self.driver.session(database=self.database) as session:
            node_result = session.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt"
            )
            nodes = {r["label"]: r["cnt"] for r in node_result}

            rel_result = session.run(
                "MATCH ()-[r]->() RETURN type(r) AS rtype, count(r) AS cnt"
            )
            rels = {r["rtype"]: r["cnt"] for r in rel_result}

        return {"nodes": nodes, "relationships": rels}
