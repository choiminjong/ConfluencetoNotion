"""Phase 2 STEP 4: JSON 데이터를 Neo4j 그래프로 구축.

STEP 3에서 생성된 JSON 파일(스키마 포함)을 읽어 Neo4j에 스키마 기반으로
Page, Content, 그리고 select/multi_select 필드에 대한 동적 노드·관계를 생성한다.

사용법:
    python -m graphrag.graph.run

설정 (.env):
    NEO4J_URI       - Neo4j 접속 URI (기본: bolt://127.0.0.1:7687)
    NEO4J_USERNAME  - Neo4j 사용자명
    NEO4J_PASSWORD  - Neo4j 비밀번호
    NEO4J_DB        - Neo4j 데이터베이스명 (기본: neo4j)
"""

import glob
import json
import os
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[0] = str(PROJECT_ROOT)

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")


def find_latest_json() -> Path | None:
    """output/graphrag/ 에서 가장 최근 JSON 파일을 찾는다."""
    pattern = str(PROJECT_ROOT / "output" / "graphrag" / "pages_*.json")
    files = sorted(glob.glob(pattern), reverse=True)
    return Path(files[0]) if files else None


def main():
    from graphrag.graph.builder import GraphBuilder

    uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4jpass")
    db_name = os.getenv("NEO4J_DB", "neo4j")

    if not password:
        print("ERROR: .env에 NEO4J_PASSWORD 설정 필요")
        sys.exit(1)

    json_path = find_latest_json()
    if not json_path:
        print("ERROR: output/graphrag/ 에 JSON 파일이 없습니다.")
        print("  먼저 python -m graphrag.scraper.run 을 실행하세요.")
        sys.exit(1)

    print("=" * 60)
    print("Phase 2 STEP 4: JSON → Neo4j 그래프")
    print("=" * 60)
    print(f"\n  입력 파일: {json_path.name}")
    print(f"  Neo4j:     {uri} / {db_name}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    schema = data.get("schema", {})
    records = data.get("pages", [])

    def _nulls_to_empty(obj):
        """None 값을 빈 문자열로 재귀 변환한다."""
        if isinstance(obj, dict):
            return {k: _nulls_to_empty(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_nulls_to_empty(item) for item in obj]
        return "" if obj is None else obj

    records = _nulls_to_empty(records)

    print(f"  스키마:     필드 {len(schema)}개")
    print(f"  페이지 수:  {len(records)}개\n")

    builder = GraphBuilder(
        uri=uri, auth=(username, password), database=db_name, schema=schema,
    )

    try:
        print("[1/3] DB 초기화...")
        builder.clear_database()
        builder.create_constraints()

        print("\n[2/3] 그래프 구축 중...")
        stats = builder.build_graph(records)

        print("\n[3/3] 그래프 통계 조회...")
        graph_stats = builder.get_stats()

        print(f"\n{'=' * 60}")
        print(f"  구축 완료")
        print(f"  Page: {stats['pages']}개, Content 청크: {stats['chunks']}개")
        print(f"\n  노드별 수:")
        for label, cnt in graph_stats["nodes"].items():
            print(f"    {label}: {cnt}")
        print(f"\n  관계별 수:")
        for rtype, cnt in graph_stats["relationships"].items():
            print(f"    {rtype}: {cnt}")
        print(f"\n  다음 단계: python -m graphrag.retriever.run")
        print(f"{'=' * 60}")
    finally:
        builder.close()


if __name__ == "__main__":
    main()
