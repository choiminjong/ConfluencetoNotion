"""Retriever 초기화, Neo4j 연결 관리.

Neo4j 드라이버를 두 종류로 관리한다.
  - async_driver: FastAPI 엔드포인트에서 non-blocking 쿼리용
  - sync_driver:  neo4j_graphrag 파이프라인용 (동기 API만 지원)

LLM/Embedder/GraphRAG 파이프라인은 initialize() 호출 시 지연 생성한다.
자격증명이 없어도 그래프 시각화는 동작한다.
"""

from __future__ import annotations

import logging

import neo4j

from graphrag.web.config import (
    NEO4J_AUTH,
    NEO4J_URI,
)

logger = logging.getLogger(__name__)

async_driver = neo4j.AsyncGraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
sync_driver = neo4j.GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)

tools_retriever = None
graphrag_list = None
graphrag_summary = None


def initialize():
    """Retriever와 GraphRAG 인스턴스를 생성한다. 앱 lifespan에서 호출."""
    global tools_retriever, graphrag_list, graphrag_summary

    from graphrag.web.config import (
        AWS_DEFAULT_REGION,
        BEDROCK_MODEL_ID,
        EMBEDDING_MODEL,
        NEO4J_DB,
    )
    from graphrag.web.services.llm import AzureOpenAIEmbeddings, BedrockLLM
    from graphrag.retriever.rag_pipeline import RAGPipeline

    llm = BedrockLLM(
        model_name=BEDROCK_MODEL_ID,
        model_params={"max_tokens": 4096, "temperature": 0},
        region=AWS_DEFAULT_REGION,
    )
    embedder = AzureOpenAIEmbeddings(model=EMBEDDING_MODEL)

    pipeline = RAGPipeline(
        driver=sync_driver,
        llm=llm,
        embedder=embedder,
        database=NEO4J_DB,
    )
    tools_retriever, graphrag_list, graphrag_summary = pipeline.build()
