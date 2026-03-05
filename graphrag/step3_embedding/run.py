"""STEP 3: Content 노드에 임베딩을 생성한다.

사용법:
    python -m graphrag.step3_embedding.run

설정 (.env):
    NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD / NEO4J_DB
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


class EmbeddingRunner:
    """Content 노드 임베딩 생성 오케스트레이터."""

    def __init__(
        self,
        uri: str,
        auth: tuple[str, str],
        database: str = "neo4j",
        embedding_model: str = "text-embedding-ada-002",
    ):
        self.uri = uri
        self.auth = auth
        self.database = database
        self.embedding_model = embedding_model

    def run(self, force: bool = False) -> int:
        """Content 노드에 임베딩을 생성하고 벡터 인덱스를 구축한다.

        Args:
            force: True이면 전체 삭제 후 재생성. False이면 증분 임베딩.

        Returns:
            처리된 Content 노드 수.
        """
        from graphrag.step3_embedding.embedder import EmbeddingManager
        from graphrag.step5_web.services.llm import AzureOpenAIEmbeddings

        print("=" * 60)
        print("STEP 3: 임베딩 생성")
        print("=" * 60)

        driver = neo4j.GraphDatabase.driver(self.uri, auth=self.auth)
        embedder = AzureOpenAIEmbeddings(model=self.embedding_model)

        try:
            mode = "전체 재생성" if force else "증분 (미임베딩만)"
            print(f"\n[1/1] 임베딩 생성... ({mode})")
            emb_manager = EmbeddingManager(
                driver=driver, database=self.database, embedder=embedder,
            )
            count = emb_manager.generate(force=force)
            print(f"  {count}개 Content 노드 임베딩 완료")

            print(f"\n{'=' * 60}")
            print("  임베딩 완료")
            print("  다음 단계: python -m graphrag.step4_rag.run")
            print(f"{'=' * 60}")

            return count
        finally:
            driver.close()

    def _ask_force(self) -> bool:
        """전체 재임베딩 여부를 사용자에게 묻는다."""
        choice = input("\n  전체 재임베딩? (y/N): ").strip().lower()
        return choice in ("y", "yes")


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
    embedding_model = os.getenv(
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002"
    )

    if not password:
        print("ERROR: .env에 NEO4J_PASSWORD 설정 필요")
        sys.exit(1)

    runner = EmbeddingRunner(
        uri=uri,
        auth=(username, password),
        database=db_name,
        embedding_model=embedding_model,
    )

    force = runner._ask_force()
    runner.run(force=force)
