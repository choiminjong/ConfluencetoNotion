"""Notion DB 페이지의 multi_select 필드를 일괄 업데이트한다.

topics_mapping.json 파일을 읽어 각 페이지의 지정된 multi_select 필드를
Notion API를 통해 업데이트한다. 기본 대상 필드는 Topics.

사용법:
    python -m graphrag.scraper.update_topics
    python -m graphrag.scraper.update_topics --file output/graphrag/topics_mapping.json

설정 (.env):
    NOTION_TOKEN        - Notion Integration 토큰
    NOTION_API_URL      - Notion API URL (프록시 경유 시 변경)
    NOTION_API_PATH     - API 경로
    NOTION_API_VERSION  - API 버전
"""

import argparse
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


def find_latest_mapping() -> Path | None:
    """output/graphrag/ 에서 topics_mapping.json을 찾는다."""
    path = PROJECT_ROOT / "output" / "graphrag" / "topics_mapping.json"
    return path if path.exists() else None


def main():
    from graphrag.scraper.notion_client import NotionClient

    parser = argparse.ArgumentParser(description="Notion DB multi_select 필드 일괄 업데이트")
    parser.add_argument(
        "--file", type=str, default=None,
        help="topics_mapping.json 파일 경로 (기본: output/graphrag/topics_mapping.json)",
    )
    parser.add_argument(
        "--field", type=str, default="Topics",
        help="업데이트할 multi_select 필드명 (기본: Topics)",
    )
    args = parser.parse_args()

    token = os.getenv("NOTION_TOKEN", "")
    api_url = os.getenv("NOTION_API_URL", "")
    api_path = os.getenv("NOTION_API_PATH", "")
    api_version = os.getenv("NOTION_API_VERSION", "")

    missing = []
    if not token:
        missing.append("NOTION_TOKEN")
    if not api_url:
        missing.append("NOTION_API_URL")
    if not api_path:
        missing.append("NOTION_API_PATH")
    if not api_version:
        missing.append("NOTION_API_VERSION")
    if missing:
        print(f"ERROR: .env에 다음 항목이 필요합니다: {', '.join(missing)}")
        sys.exit(1)

    if args.file:
        mapping_path = Path(args.file)
    else:
        mapping_path = find_latest_mapping()

    if not mapping_path or not mapping_path.exists():
        print("ERROR: topics_mapping.json 파일을 찾을 수 없습니다.")
        print("  먼저 Topic 매핑 파일을 생성하세요.")
        print("  경로: output/graphrag/topics_mapping.json")
        sys.exit(1)

    with open(mapping_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    mappings = data.get("mappings", [])
    if not mappings:
        print("ERROR: 매핑 데이터가 비어 있습니다.")
        sys.exit(1)

    client = NotionClient(
        token=token, api_url=api_url, api_path=api_path, api_version=api_version,
    )

    field_name = args.field

    print("=" * 60)
    print(f"Notion DB {field_name} 일괄 업데이트")
    print("=" * 60)
    print(f"\n  매핑 파일: {mapping_path}")
    print(f"  대상 필드: {field_name}")
    print(f"  대상 페이지: {len(mappings)}개")
    print(f"  API: {api_url}")
    print()

    success = 0
    failed = 0

    for i, item in enumerate(mappings, 1):
        page_id = item.get("page_id", "")
        title = item.get("title", "Untitled")
        topics = item.get("topics", [])

        if not page_id:
            print(f"  ({i}/{len(mappings)}) SKIP: page_id 없음 - {title}")
            failed += 1
            continue

        if not topics:
            print(f"  ({i}/{len(mappings)}) SKIP: topics 없음 - {title}")
            continue

        try:
            client.update_page_multi_select(page_id, field_name, topics)
            topics_str = ", ".join(topics)
            print(f"  ({i}/{len(mappings)}) OK: {title} → [{topics_str}]")
            success += 1
        except Exception as e:
            print(f"  ({i}/{len(mappings)}) FAIL: {title} - {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"  완료: 성공 {success}개, 실패 {failed}개")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
