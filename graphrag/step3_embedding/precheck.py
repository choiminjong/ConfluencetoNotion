"""STEP 3 실행 전 사전 점검 스크립트.

Neo4j 연결, Azure OpenAI 임베딩, AWS Bedrock LLM을 각각 테스트하여
step3_embedding.run 실행 가능 여부를 판단한다.

사용법:
    python -m graphrag.step3_embedding.precheck

설정 (.env):
    NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD / NEO4J_DB
    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_DEFAULT_REGION
    AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY / AZURE_OPENAI_EMBEDDING_DEPLOYMENT
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[0] = str(PROJECT_ROOT)

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")


class RetrieverPrecheck:
    """Retriever 실행 전 Neo4j, 임베딩, LLM 연결을 점검한다."""

    def __init__(self):
        self.uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
        self.username = os.getenv("NEO4J_USERNAME", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "")
        self.db_name = os.getenv("NEO4J_DB", "neo4j")
        self.embedding_model = os.getenv(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002"
        )
        self.bedrock_model = os.getenv(
            "BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        )
        self.region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    def run(self) -> None:
        """전체 점검을 실행하고 결과를 출력한다."""
        print("=" * 55)
        print("  Retriever Pre-check")
        print("=" * 55)

        print("\n[0/3] 환경변수 확인...")
        env_results = self._check_env_vars()

        print("\n[1/3] Neo4j 연결...")
        neo4j_ok = self._check_neo4j()

        print("\n[2/3] Azure OpenAI 임베딩...")
        embed_ok = self._check_embedding()

        print("\n[3/3] AWS Bedrock LLM...")
        llm_ok = self._check_llm()

        results = {
            "env_vars": all(env_results.values()),
            "neo4j": neo4j_ok,
            "embedding": embed_ok,
            "llm": llm_ok,
        }

        print(f"\n{'=' * 55}")
        for name, ok in results.items():
            status = "PASS" if ok else "FAIL"
            print(f"  {name:12s} : {status}")
        print(f"{'=' * 55}")

        if all(results.values()):
            print("\n  모든 점검 통과!")
            print("  다음 단계: python -m graphrag.step3_embedding.run")
        else:
            failed = [k for k, v in results.items() if not v]
            print(f"\n  실패 항목: {', '.join(failed)}")
            print("  .env 설정을 확인한 뒤 다시 시도하세요.")
            sys.exit(1)

    def _check_env_vars(self) -> dict[str, bool]:
        """필수 환경변수 존재 여부를 반환한다."""
        groups = {
            "Neo4j": ["NEO4J_PASSWORD"],
            "Azure OpenAI": [
                "AZURE_OPENAI_ENDPOINT",
                "AZURE_OPENAI_API_KEY",
            ],
            "AWS Bedrock": [
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
            ],
        }
        results: dict[str, bool] = {}
        for group, keys in groups.items():
            missing = [k for k in keys if not os.getenv(k)]
            ok = len(missing) == 0
            results[group] = ok
            if ok:
                print(f"  {group} 환경변수 OK")
            else:
                print(f"  {group} 환경변수 MISSING: {', '.join(missing)}")
        return results

    def _check_neo4j(self) -> bool:
        """Neo4j 연결과 Content 노드 존재 여부를 확인한다."""
        import neo4j

        if not self.password:
            print("  NEO4J_PASSWORD가 비어 있습니다.")
            return False

        driver = neo4j.GraphDatabase.driver(
            self.uri, auth=(self.username, self.password),
        )
        try:
            with driver.session(database=self.db_name) as session:
                page_cnt = session.run(
                    "MATCH (p:Page) RETURN count(p) AS cnt"
                ).single()["cnt"]
                content_cnt = session.run(
                    "MATCH (c:Content) RETURN count(c) AS cnt"
                ).single()["cnt"]
            print(f"  Neo4j 연결 OK - Page: {page_cnt}개, Content: {content_cnt}개")
            if content_cnt == 0:
                print("  (주의) Content 노드가 0개입니다. graph.run을 먼저 실행하세요.")
            return True
        except Exception as e:
            print(f"  Neo4j 연결 실패: {e}")
            return False
        finally:
            driver.close()

    def _check_embedding(self) -> bool:
        """Azure OpenAI 임베딩 모델에 테스트 문장을 보내 벡터를 반환받는다."""
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        if not endpoint or not api_key:
            print("  AZURE_OPENAI_ENDPOINT / API_KEY 가 설정되지 않았습니다.")
            return False

        from graphrag.step5_web.services.llm import AzureOpenAIEmbeddings

        embedder = AzureOpenAIEmbeddings(model=self.embedding_model)
        try:
            vector = embedder.embed_query("사전 점검 테스트 문장입니다.")
            dim = len(vector)
            print(
                f"  임베딩 OK - 차원: {dim}, "
                f"샘플: [{vector[0]:.6f}, {vector[1]:.6f}, {vector[2]:.6f}]"
            )
            return True
        except Exception as e:
            print(f"  임베딩 실패: {e}")
            return False

    def _check_llm(self) -> bool:
        """AWS Bedrock LLM에 테스트 프롬프트를 보내 응답을 받는다."""
        if not os.getenv("AWS_ACCESS_KEY_ID") or not os.getenv("AWS_SECRET_ACCESS_KEY"):
            print("  AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY 가 설정되지 않았습니다.")
            return False

        from graphrag.step5_web.services.llm import BedrockLLM

        llm = BedrockLLM(
            model_name=self.bedrock_model,
            model_params={"max_tokens": 50, "temperature": 0},
            region=self.region,
        )
        try:
            response = llm.invoke("테스트입니다. '확인' 한 글자만 답하세요.")
            print(f"  LLM 호출 OK - 응답: {response.content[:80]}")
            return True
        except Exception as e:
            print(f"  LLM 호출 실패: {e}")
            return False


if __name__ == "__main__":
    checker = RetrieverPrecheck()
    checker.run()
