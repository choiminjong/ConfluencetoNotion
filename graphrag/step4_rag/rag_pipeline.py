"""2종 Retriever + ToolsRetriever + GraphRAG 파이프라인.

VectorCypherRetriever, Text2CypherRetriever를 구성하고
ToolsRetriever로 LLM이 자동 선택하도록 한다.
"""

from __future__ import annotations

import neo4j
from neo4j_graphrag.generation import GraphRAG, RagTemplate
from neo4j_graphrag.retrievers import (
    Text2CypherRetriever,
    ToolsRetriever,
    VectorCypherRetriever,
)


RETRIEVAL_QUERY = """
WITH node AS content, score
MATCH (content)<-[:HAS_CHUNK]-(page:Page)
OPTIONAL MATCH (page)-[:BELONGS_TO]->(domain:Domain)
OPTIONAL MATCH (page)-[:HAS_TOPIC]->(topic:Topic)
OPTIONAL MATCH (page)-[:IN_SPACE]->(space:Space)
OPTIONAL MATCH (domain)<-[:BELONGS_TO]-(related_page:Page)
WHERE related_page <> page
RETURN
    content.content_id AS content_id,
    content.chunk AS chunk,
    page.page_id AS page_id,
    page.title AS page_title,
    page.source_url AS page_url,
    page.updated AS page_updated,
    domain.name AS domain_name,
    space.name AS space_name,
    collect(DISTINCT topic.name) AS topics,
    score AS similarity_score,
    collect(DISTINCT {
        page_id: related_page.page_id,
        title: related_page.title,
        source_url: related_page.source_url
    })[0..5] AS related_pages
"""

TEXT2CYPHER_EXAMPLES = [
    'USER INPUT: Jira 도메인의 모든 페이지\nCYPHER QUERY:\n'
    'MATCH (p:Page)-[:BELONGS_TO]->(d:Domain {name: "Jira"})\n'
    'RETURN p.page_id, p.title, p.source_url, p.updated\n'
    'ORDER BY p.updated DESC LIMIT 20',

    'USER INPUT: 도메인별 페이지 수\nCYPHER QUERY:\n'
    'MATCH (p:Page)-[:BELONGS_TO]->(d:Domain)\n'
    'RETURN d.name as domain, count(p) as page_count\n'
    'ORDER BY page_count DESC',

    'USER INPUT: 특정 Space의 페이지 목록\nCYPHER QUERY:\n'
    'MATCH (p:Page)-[:IN_SPACE]->(s:Space)\n'
    'RETURN s.name as space, p.title, p.source_url\n'
    'ORDER BY s.name, p.title',

    'USER INPUT: 토픽별 페이지 수\nCYPHER QUERY:\n'
    'MATCH (p:Page)-[:HAS_TOPIC]->(t:Topic)\n'
    'RETURN t.name as topic, count(p) as page_count\n'
    'ORDER BY page_count DESC',

    'USER INPUT: 최근 업데이트된 문서\nCYPHER QUERY:\n'
    'MATCH (p:Page)\n'
    'RETURN p.title, p.source_url, p.last_edited, p.updated\n'
    'ORDER BY p.last_edited DESC LIMIT 20',
]

TOOL_SELECTION_INSTRUCTION = (
    "당신은 사용자의 질문을 분석하여 가장 적합한 검색 도구를 선택하는 어시스턴트입니다. "
    "다음 기준으로 도구를 선택하세요:\n"
    "- 문서 내용(설정 방법, 절차, 개념, 문제 해결 등)에 대한 질문 → semantic_search\n"
    "- 문서 목록, 개수, 분류 등 구조적 질문 → structured_query\n"
    "- 확실하지 않으면 semantic_search를 선택하세요.\n"
    "- 한 번에 하나의 도구만 선택하세요."
)

PROMPT_LIST = RagTemplate(
    template="""당신은 사내 기술 문서 검색 어시스턴트입니다.
Neo4j 지식 그래프에서 검색된 문서 정보만을 사용하여 답변합니다.

## 검색 결과
{context}

## 질문
{query_text}

## 지시사항
1. 반드시 위 검색 결과에 포함된 내용만 사용하여 답변하세요.
2. 검색 결과에 질문과 관련된 내용이 없으면 다음과 같이만 답하세요:
   "해당 내용의 문서가 데이터베이스에 없습니다."
3. 자체 지식이나 추측으로 답변하지 마세요.
4. 동일 URL의 문서는 한 번만 표시하세요.
5. 유사도 점수가 높은 문서를 우선 배치하세요.

## 답변 형식
각 문서에 대해 아래 형식으로 작성하세요:

1. **문서 제목**
   - URL: [문서 URL]
   - 도메인: [도메인명]
   - 핵심 내용: [질문과 관련된 내용 1~2문장 요약]

답변:""",
    expected_inputs=["context", "query_text"],
)

PROMPT_SUMMARY = RagTemplate(
    template="""당신은 사내 기술 문서를 분석하여 주제별 요약을 제공하는 어시스턴트입니다.
Neo4j 지식 그래프에서 검색된 문서 정보만을 사용하여 요약합니다.

## 검색 결과
{context}

## 질문
{query_text}

## 지시사항
1. 반드시 위 검색 결과에 포함된 내용만 사용하여 요약하세요.
2. 검색 결과에 질문과 관련된 내용이 없으면 다음과 같이만 답하세요:
   "관련 문서가 데이터베이스에 없습니다."
3. 자체 지식이나 추측으로 내용을 보충하지 마세요.
4. 여러 문서의 내용을 종합하되, 각 정보의 출처를 명시하세요.

## 답변 형식

### [주제] 요약
[여러 문서의 핵심 내용을 종합하여 3~5문장으로 요약]

### 주요 포인트
- [핵심 사항 1] (출처: 문서 제목)
- [핵심 사항 2] (출처: 문서 제목)
- [핵심 사항 3] (출처: 문서 제목)

### 참고 문서
1. **문서 제목** - [URL]

답변:""",
    expected_inputs=["context", "query_text"],
)


class RAGPipeline:
    """2종 Retriever + GraphRAG 파이프라인을 구성한다."""

    def __init__(
        self,
        driver: neo4j.Driver,
        llm,
        embedder,
        database: str = "neo4j",
        index_name: str = "content_vector_index",
    ):
        self.driver = driver
        self.llm = llm
        self.embedder = embedder
        self.database = database
        self.index_name = index_name

    def build(self) -> tuple:
        """2종 Retriever + GraphRAG 인스턴스를 생성하여 반환한다.

        Returns:
            (tools_retriever, graphrag_list, graphrag_summary)
        """
        vector_cypher_retriever = VectorCypherRetriever(
            driver=self.driver,
            index_name=self.index_name,
            retrieval_query=RETRIEVAL_QUERY,
            embedder=self.embedder,
            neo4j_database=self.database,
        )

        neo4j_schema = self._get_neo4j_schema()
        text2cypher_retriever = Text2CypherRetriever(
            driver=self.driver,
            llm=self.llm,
            neo4j_schema=neo4j_schema,
            examples=TEXT2CYPHER_EXAMPLES,
            neo4j_database=self.database,
        )

        semantic_tool = vector_cypher_retriever.convert_to_tool(
            name="semantic_search",
            description=(
                "기술 문서의 본문 내용을 의미 기반으로 검색하여, "
                "해당 문서의 제목, URL, 도메인, 토픽, 유사도 점수, "
                "같은 도메인의 관련 문서를 함께 반환한다. "
                "특정 기술의 설정 방법, 사용 절차, 개념 설명, 문제 해결 등 "
                "문서 내용에 대한 질문일 때 사용한다. "
                "예시: 'Jira 프로젝트 설정 방법', 'OAuth 인증 절차', "
                "'API 호출 방법', '오류 해결 가이드'"
            ),
        )
        structured_tool = text2cypher_retriever.convert_to_tool(
            name="structured_query",
            description=(
                "그래프 데이터베이스의 구조를 직접 조회하여 "
                "문서 목록, 개수, 분류 등 집계·필터링 결과를 반환한다. "
                "특정 도메인·토픽·Space에 속한 문서 목록이나 "
                "개수를 물을 때, 또는 전체 구조를 파악할 때 사용한다. "
                "예시: 'Jira 도메인의 모든 문서', '도메인별 페이지 수', "
                "'토픽별 문서 분류', '최근 업데이트된 문서 목록'"
            ),
        )

        tools_retriever = ToolsRetriever(
            driver=self.driver,
            llm=self.llm,
            tools=[semantic_tool, structured_tool],
            system_instruction=TOOL_SELECTION_INSTRUCTION,
        )

        graphrag_list = GraphRAG(
            llm=self.llm,
            retriever=tools_retriever,
            prompt_template=PROMPT_LIST,
        )
        graphrag_summary = GraphRAG(
            llm=self.llm,
            retriever=tools_retriever,
            prompt_template=PROMPT_SUMMARY,
        )

        return tools_retriever, graphrag_list, graphrag_summary

    def _get_neo4j_schema(self) -> str:
        """Neo4j 스키마를 텍스트로 반환한다."""
        with self.driver.session(database=self.database) as session:
            node_info = session.run(
                "CALL db.schema.nodeTypeProperties() "
                "YIELD nodeType, propertyName, propertyTypes "
                "RETURN nodeType, collect(propertyName) as properties"
            ).data()
            patterns = session.run(
                "MATCH (n)-[r]->(m) "
                "RETURN DISTINCT labels(n)[0] as source, type(r) as rel, "
                "labels(m)[0] as target LIMIT 20"
            ).data()

        schema = "=== Neo4j Schema ===\n\n노드 타입:\n"
        for n in node_info:
            schema += f"- {n['nodeType']}: {n['properties']}\n"
        schema += "\n관계 패턴:\n"
        for p in patterns:
            schema += f"- ({p['source']})-[:{p['rel']}]->({p['target']})\n"
        return schema
