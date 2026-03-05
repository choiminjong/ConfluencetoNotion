"""GraphRAG 파이프라인.

VectorCypherRetriever를 기본 retriever로 사용하고,
GraphRAG로 답변을 생성한다.
도메인이 여러 개일 때는 간략 요약을 먼저 제공한 뒤,
사용자가 도메인을 선택하면 상세 답변을 생성한다.
"""

from __future__ import annotations

import neo4j
from neo4j_graphrag.generation import GraphRAG, RagTemplate
from neo4j_graphrag.retrievers import VectorCypherRetriever


RETRIEVAL_QUERY = """
WITH node AS content, score
MATCH (content)<-[:HAS_CHUNK]-(page:Page)
OPTIONAL MATCH (page)-[:HAS_DOMAIN]->(domain:Domain)
OPTIONAL MATCH (page)-[:HAS_TOPICS]->(topic:Topics)
RETURN
    content.content_id AS content_id,
    content.chunk AS chunk,
    page.page_id AS page_id,
    page.title AS page_title,
    page.source_url AS page_url,
    page.updated AS page_updated,
    domain.name AS domain_name,
    collect(DISTINCT topic.name) AS topics,
    score AS similarity_score
"""

NEO4J_DATA_CONSTRAINT = """
## 절대 규칙 (반드시 준수)
- 위 검색 결과에 포함된 내용만 사용하여 답변하세요.
- 검색 결과에 없는 내용은 절대 답변에 포함하지 마세요.
- "~일 수 있습니다", "일반적으로~" 같은 추측 표현을 사용하지 마세요.
- 사전 학습된 지식이나 외부 정보를 절대 사용하지 마세요.
- 관련 문서가 없으면 반드시 "해당 내용의 문서가 데이터베이스에 없습니다."로만 답변하세요.
"""

PROMPT_LIST = RagTemplate(
    template="""당신은 사내 기술 문서 검색 어시스턴트입니다.
Neo4j 지식 그래프에서 검색된 문서 정보만을 사용하여 답변합니다.

## 검색 결과
{context}

## 질문
{query_text}
"""
    + NEO4J_DATA_CONSTRAINT
    + """
## 답변 형식
각 문서에 대해 아래 형식으로 작성하세요:

1. **문서 제목** (`도메인명`)
   - 핵심 내용: [질문과 관련된 내용 1~2문장 요약]
   - [문서 보기](문서 URL)

답변:""",
    expected_inputs=["context", "query_text"],
)

PROMPT_SUMMARY = RagTemplate(
    template="""당신은 사내 기술 문서를 분석하여 실용적인 안내를 제공하는 어시스턴트입니다.
Neo4j 지식 그래프에서 검색된 문서 정보만을 사용하여 답변합니다.

## 검색 결과
{context}

## 질문
{query_text}
"""
    + NEO4J_DATA_CONSTRAINT
    + """
## 답변 형식

### [주제] 안내

검색 결과에 단계별 절차가 있으면 아래처럼 구체적으로 안내하세요:
1. [절차 1]
2. [절차 2]
3. [절차 3]

절차가 없으면 핵심 내용을 종합하여 3~5문장으로 요약하세요.

### 참고 문서
- [문서 제목](문서 URL)

답변:""",
    expected_inputs=["context", "query_text"],
)

PROMPT_DOMAIN_OVERVIEW = RagTemplate(
    template="""당신은 사내 기술 문서 검색 어시스턴트입니다.
사용자의 질문과 관련된 문서가 여러 도메인에 걸쳐 있습니다.
각 도메인별로 간략히 어떤 내용이 있는지 1줄 요약만 작성하세요.

## 검색 결과
{context}

## 질문
{query_text}
"""
    + NEO4J_DATA_CONSTRAINT
    + """
## 답변 형식
요약 답변: [질문]과 관련된 가이드가 여러 도메인에 걸쳐 존재합니다.

- **[도메인명1]** — [해당 도메인에서 다루는 내용 1줄 요약]
- **[도메인명2]** — [해당 도메인에서 다루는 내용 1줄 요약]

어떤 도메인의 상세 안내를 원하시나요?

답변:""",
    expected_inputs=["context", "query_text"],
)


class RAGPipeline:
    """VectorCypherRetriever + GraphRAG 파이프라인을 구성한다."""

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
        """VectorCypherRetriever + GraphRAG 인스턴스를 생성하여 반환한다.

        Returns:
            (retriever, graphrag_list, graphrag_summary, graphrag_overview, llm)
        """
        retriever = VectorCypherRetriever(
            driver=self.driver,
            index_name=self.index_name,
            retrieval_query=RETRIEVAL_QUERY,
            embedder=self.embedder,
            neo4j_database=self.database,
        )

        graphrag_list = GraphRAG(
            llm=self.llm,
            retriever=retriever,
            prompt_template=PROMPT_LIST,
        )
        graphrag_summary = GraphRAG(
            llm=self.llm,
            retriever=retriever,
            prompt_template=PROMPT_SUMMARY,
        )
        graphrag_overview = GraphRAG(
            llm=self.llm,
            retriever=retriever,
            prompt_template=PROMPT_DOMAIN_OVERVIEW,
        )

        return retriever, graphrag_list, graphrag_summary, graphrag_overview, self.llm
