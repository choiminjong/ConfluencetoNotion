"""STEP 4: GraphRAG 파이프라인을 구성하고 테스트 질의로 검증한다.

사용법:
    python -m graphrag.step4_rag.run

설정 (.env):
    NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD / NEO4J_DB
    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_DEFAULT_REGION
    AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY / AZURE_OPENAI_EMBEDDING_DEPLOYMENT
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[0] = str(PROJECT_ROOT)

import neo4j


class RAGTestRunner:
    """GraphRAG 파이프라인 구성 + 테스트 질의 오케스트레이터."""

    def __init__(
        self,
        uri: str,
        auth: tuple[str, str],
        database: str = "neo4j",
        bedrock_model: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        region: str = "us-east-1",
        embedding_model: str = "text-embedding-ada-002",
    ):
        self.uri = uri
        self.auth = auth
        self.database = database
        self.bedrock_model = bedrock_model
        self.region = region
        self.embedding_model = embedding_model

    def run(self) -> None:
        """파이프라인 구성 → 테스트 질의."""
        from graphrag.step4_rag.rag_pipeline import RAGPipeline
        from graphrag.step5_web.services.llm import AzureOpenAIEmbeddings, BedrockLLM

        print("=" * 60)
        print("STEP 4: GraphRAG 파이프라인 검증")
        print("=" * 60)

        driver = neo4j.GraphDatabase.driver(self.uri, auth=self.auth)
        llm = BedrockLLM(
            model_name=self.bedrock_model,
            model_params={"max_tokens": 4096, "temperature": 0},
            region=self.region,
        )
        embedder = AzureOpenAIEmbeddings(model=self.embedding_model)

        try:
            print("\n[1/2] GraphRAG 파이프라인 구성...")
            pipeline = RAGPipeline(
                driver=driver, llm=llm, embedder=embedder,
                database=self.database,
            )
            _, graphrag_list, _ = pipeline.build()
            print("  파이프라인 구성 완료")

            print("\n[2/2] 테스트 질의...")
            test_query = "Jira 관련 문서를 알려줘"
            print(f"  질의: {test_query}")
            response = graphrag_list.search(
                query_text=test_query, retriever_config={"top_k": 3},
            )
            print(f"  응답:\n{response.answer[:500]}...")

            print(f"\n{'=' * 60}")
            print("  GraphRAG 파이프라인 준비 완료")
            print("  다음 단계: python -m graphrag.step5_web.run")
            print(f"{'=' * 60}")
        finally:
            driver.close()


# ======================================================================
# 엔트리포인트 — 환경변수 로딩은 이 블록에서만 수행
# ======================================================================

if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")

    uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")
    db_name = os.getenv("NEO4J_DB", "neo4j")
    bedrock_model = os.getenv(
        "BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    )
    region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    embedding_model = os.getenv(
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002"
    )

    if not password:
        print("ERROR: .env에 NEO4J_PASSWORD 설정 필요")
        sys.exit(1)

    runner = RAGTestRunner(
        uri=uri,
        auth=(username, password),
        database=db_name,
        bedrock_model=bedrock_model,
        region=region,
        embedding_model=embedding_model,
    )

    runner.run()
