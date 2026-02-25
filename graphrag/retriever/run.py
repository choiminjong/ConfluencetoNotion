"""Phase 2 STEP 5: Content 노드에 임베딩을 생성하고 GraphRAG 파이프라인을 검증.

임베딩을 생성한 후 테스트 질의를 실행하여 파이프라인 동작을 확인한다.

사용법:
    python -m graphrag.retriever.run

설정 (.env):
    NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD / NEO4J_DB
    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_DEFAULT_REGION
    AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY / AZURE_OPENAI_EMBEDDING_DEPLOYMENT
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[0] = str(PROJECT_ROOT)

import neo4j
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")


def main():
    from graphrag.retriever.embedder import clear_existing_embeddings, generate_embeddings
    from graphrag.retriever.rag_pipeline import build_pipeline

    uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")
    db_name = os.getenv("NEO4J_DB", "neo4j")
    bedrock_model = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
    region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    embedding_model = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")

    if not password:
        print("ERROR: .env에 NEO4J_PASSWORD 설정 필요")
        sys.exit(1)

    print("=" * 60)
    print("Phase 2 STEP 5: 임베딩 생성 + GraphRAG 검증")
    print("=" * 60)

    from graphrag.web.services.llm import AzureOpenAIEmbeddings, BedrockLLM

    driver = neo4j.GraphDatabase.driver(uri, auth=(username, password))
    llm = BedrockLLM(
        model_name=bedrock_model,
        model_params={"max_tokens": 4096, "temperature": 0},
        region=region,
    )
    embedder = AzureOpenAIEmbeddings(model=embedding_model)

    try:
        print("\n[1/3] 임베딩 생성...")
        clear_existing_embeddings(driver, db_name)
        count = generate_embeddings(driver, db_name, embedder)
        print(f"  {count}개 Content 노드 임베딩 완료")

        print("\n[2/3] GraphRAG 파이프라인 구성...")
        _, graphrag_list, _ = build_pipeline(
            driver=driver, llm=llm, embedder=embedder, database=db_name
        )
        print("  파이프라인 구성 완료")

        print("\n[3/3] 테스트 질의...")
        test_query = "Jira 관련 문서를 알려줘"
        print(f"  질의: {test_query}")
        response = graphrag_list.search(query_text=test_query, retriever_config={"top_k": 3})
        print(f"  응답:\n{response.answer[:500]}...")

        print(f"\n{'=' * 60}")
        print(f"  GraphRAG 파이프라인 준비 완료")
        print(f"  다음 단계: python -m graphrag.web.run")
        print(f"{'=' * 60}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
