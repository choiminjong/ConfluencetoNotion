"""3종 Retriever + ToolsRetriever + GraphRAG 파이프라인.

VectorRetriever, VectorCypherRetriever, Text2CypherRetriever를 구성하고
ToolsRetriever로 LLM이 자동 선택하도록 한다.
"""

from __future__ import annotations

import neo4j
from neo4j_graphrag.generation import GraphRAG, RagTemplate
from neo4j_graphrag.retrievers import (
    Text2CypherRetriever,
    ToolsRetriever,
    VectorCypherRetriever,
    VectorRetriever,
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
]

PROMPT_LIST = RagTemplate(
    template="""당신은 Neo4j 그래프 데이터베이스에 저장된 Confluence 기술 문서를 검색하여 답변하는 어시스턴트입니다.

질문: {query_text}

검색된 문서 정보:
{context}

반드시 지켜야 할 규칙:
1. 오직 위의 검색 결과(Context)에 포함된 내용만 사용하여 답변하세요.
2. 검색 결과가 비어있거나 질문과 관련 없는 경우, "해당 내용의 문서가 데이터베이스에 없습니다."라고만 답하세요.
3. 절대로 검색 결과에 없는 내용을 추측하거나 자체 지식으로 답변하지 마세요.
4. 같은 URL의 문서는 중복 제거하여 한 번만 표시하세요.
5. 반드시 아래 형식으로만 답변하세요:

1. 문서 제목
   - URL: https://...
   - 도메인: ...

답변:""",
    expected_inputs=["context", "query_text"],
)

PROMPT_SUMMARY = RagTemplate(
    template="""당신은 Neo4j 그래프 데이터베이스에 저장된 Confluence 기술 문서를 분석하여 주제별 요약을 제공하는 AI 어시스턴트입니다.

질문: {query_text}

검색된 문서 정보:
{context}

반드시 지켜야 할 규칙:
1. 오직 위의 검색 결과에 포함된 내용만을 기반으로 요약하세요.
2. 검색 결과가 비어있거나 질문과 관련 없는 경우, "관련 문서가 데이터베이스에 없습니다."라고만 답하세요.
3. 절대로 검색 결과에 없는 내용을 추측하거나 자체 지식으로 답변하지 마세요.
4. 반드시 아래 형식으로 답변하세요:

## [주제] 요약

[여러 문서의 핵심 내용을 종합하여 3~5문장으로 요약]

### 주요 포인트
- [핵심 사항 1]
- [핵심 사항 2]
- [핵심 사항 3]

### 참고 문서
1. 문서 제목
   URL: https://...

답변:""",
    expected_inputs=["context", "query_text"],
)


def get_neo4j_schema(driver: neo4j.Driver, database: str) -> str:
    """Neo4j 스키마를 텍스트로 반환한다."""
    with driver.session(database=database) as session:
        node_info = session.run(
            "CALL db.schema.nodeTypeProperties() "
            "YIELD nodeType, propertyName, propertyTypes "
            "RETURN nodeType, collect(propertyName) as properties"
        ).data()
        patterns = session.run(
            "MATCH (n)-[r]->(m) "
            "RETURN DISTINCT labels(n)[0] as source, type(r) as rel, labels(m)[0] as target "
            "LIMIT 20"
        ).data()

    schema = "=== Neo4j Schema ===\n\n노드 타입:\n"
    for n in node_info:
        schema += f"- {n['nodeType']}: {n['properties']}\n"
    schema += "\n관계 패턴:\n"
    for p in patterns:
        schema += f"- ({p['source']})-[:{p['rel']}]->({p['target']})\n"
    return schema


def build_pipeline(
    driver: neo4j.Driver,
    llm,
    embedder,
    database: str = "neo4j",
    index_name: str = "content_vector_index",
) -> tuple:
    """3종 Retriever + GraphRAG 인스턴스를 생성하여 반환한다.

    Returns:
        (tools_retriever, graphrag_list, graphrag_summary)
    """
    vector_retriever = VectorRetriever(
        driver=driver,
        index_name=index_name,
        embedder=embedder,
        neo4j_database=database,
    )

    vector_cypher_retriever = VectorCypherRetriever(
        driver=driver,
        index_name=index_name,
        retrieval_query=RETRIEVAL_QUERY,
        embedder=embedder,
        neo4j_database=database,
    )

    neo4j_schema = get_neo4j_schema(driver, database)
    text2cypher_retriever = Text2CypherRetriever(
        driver=driver,
        llm=llm,
        neo4j_schema=neo4j_schema,
        examples=TEXT2CYPHER_EXAMPLES,
        neo4j_database=database,
    )

    vector_tool = vector_retriever.convert_to_tool(
        name="vector_retriever",
        description=(
            "기술 문서 본문의 의미를 기반으로 유사한 내용을 검색한다. "
            "특정 기능, 설정 방법, 절차에 대한 문서를 찾을 때 사용한다."
        ),
    )
    vector_cypher_tool = vector_cypher_retriever.convert_to_tool(
        name="vectorcypher_retriever",
        description=(
            "의미 기반 검색 결과에 문서의 상세정보(제목, URL, 도메인)와 "
            "같은 도메인의 관련 문서를 함께 반환한다."
        ),
    )
    text2cypher_tool = text2cypher_retriever.convert_to_tool(
        name="text2cypher_retriever",
        description=(
            "도메인별 문서 목록, Space별 문서 수, 토픽별 분류 등 "
            "구조적 조건으로 검색한다. "
            "'도메인', '목록', '개수', 'Space별' 같은 조건이 포함된 질문에 사용한다."
        ),
    )

    tools_retriever = ToolsRetriever(
        driver=driver,
        llm=llm,
        tools=[vector_tool, vector_cypher_tool, text2cypher_tool],
    )

    graphrag_list = GraphRAG(
        llm=llm,
        retriever=tools_retriever,
        prompt_template=PROMPT_LIST,
    )
    graphrag_summary = GraphRAG(
        llm=llm,
        retriever=tools_retriever,
        prompt_template=PROMPT_SUMMARY,
    )

    return tools_retriever, graphrag_list, graphrag_summary
