"""Phase 2 STEP 3: Notion DB에서 전체 페이지를 추출하여 JSON으로 저장.

Notion DB 스키마를 자동 조회하고, 모든 페이지의 속성과 블록 콘텐츠를
구조화된 섹션(heading 기반)과 플레인 텍스트로 추출하여 JSON 파일로 저장한다.
DB 필드명을 하드코딩하지 않으므로 어떤 Notion DB에서도 동작한다.

사용법:
    python -m graphrag.scraper.run

설정 (.env):
    NOTION_TOKEN        - Notion Integration 토큰
    NOTION_DATABASE_ID  - 대상 Notion DB ID
    NOTION_API_URL      - Notion API URL (프록시 경유 시 변경)
    NOTION_API_PATH     - API 경로 (기본 v1)
    NOTION_API_VERSION  - API 버전 (기본 2022-06-28)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[0] = str(PROJECT_ROOT)

from graphrag.scraper.content_parser import ContentParser
from graphrag.scraper.notion_client import NotionClient


class NotionScraper:
    """Notion DB → JSON 추출 오케스트레이터."""

    def __init__(self, client: NotionClient, output_dir: Path):
        self.client = client
        self.output_dir = output_dir
        self.parser = ContentParser()

    def run(self, database_id: str) -> Path:
        """스키마 조회 → 페이지 추출 → JSON 저장. 저장된 JSON 경로를 반환한다."""
        print("=" * 60)
        print("Phase 2 STEP 3: Notion DB → JSON")
        print("=" * 60)

        print("\n[1/4] DB 스키마 조회 중...")
        schema = self.client.get_database_schema(database_id)
        print(f"  필드 {len(schema)}개 감지:")
        for name, ftype in schema.items():
            print(f"    {name}: {ftype}")

        print("\n[2/4] Notion DB 페이지 목록 조회 중...")
        pages = self.client.query_database(database_id)
        print(f"  총 {len(pages)}개 페이지 발견")

        print("\n[3/4] 각 페이지 속성 + 본문 추출 중...")
        records = self._extract_pages(pages)

        print("\n[4/4] JSON 저장 중...")
        output_path = self._save_json(database_id, schema, records)

        content_count = sum(1 for r in records if r["content"])
        section_count = sum(len(r["sections"]) for r in records)

        print(f"  저장 완료: {output_path}")
        print(f"  총 {len(records)}개 페이지, 본문 있는 페이지: {content_count}개")
        print(f"  총 섹션 수: {section_count}개")
        print(f"\n{'=' * 60}")
        print(f"  다음 단계: python -m graphrag.graph.run")
        print(f"{'=' * 60}")

        return output_path

    def _extract_pages(self, pages: list[dict]) -> list[dict]:
        """각 페이지의 속성과 본문을 추출한다."""
        records: list[dict] = []

        for i, page in enumerate(pages, 1):
            props = self.client.extract_page_properties(page)
            page_id = props.pop("page_id", "")
            title = props.pop("title", "Untitled")
            notion_url = props.pop("notion_url", "")
            last_edited = props.pop("last_edited_time", "")
            print(f"  ({i}/{len(pages)}) {title}")

            try:
                blocks = self.client.get_block_children(page["id"])
                content = self.parser.parse_text(blocks)
                sections = self.parser.parse_sections(blocks)
            except Exception as e:
                print(f"    WARN: 블록 읽기 실패 - {e}")
                content = ""
                sections = []

            props["Source URL"] = notion_url

            records.append({
                "page_id": page_id,
                "title": title,
                "properties": props,
                "last_edited_time": last_edited,
                "content": content,
                "sections": sections,
            })

        return records

    def _save_json(self, database_id: str, schema: dict, records: list[dict]) -> Path:
        """추출된 데이터를 JSON 파일로 저장한다."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = self.output_dir / f"pages_{timestamp}.json"

        output_data = {
            "extracted_at": datetime.now().isoformat(),
            "database_id": database_id,
            "schema": schema,
            "pages": records,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        return output_path


# ======================================================================
# 엔트리포인트 — 환경변수 로딩은 이 블록에서만 수행
# ======================================================================

if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")

    token = os.getenv("NOTION_TOKEN", "")
    database_id = os.getenv("NOTION_DATABASE_ID", "")
    api_url = os.getenv("NOTION_API_URL", "")
    api_path = os.getenv("NOTION_API_PATH", "")
    api_version = os.getenv("NOTION_API_VERSION", "")

    missing = []
    if not token:
        missing.append("NOTION_TOKEN")
    if not database_id:
        missing.append("NOTION_DATABASE_ID")
    if not api_url:
        missing.append("NOTION_API_URL")
    if not api_path:
        missing.append("NOTION_API_PATH")
    if not api_version:
        missing.append("NOTION_API_VERSION")
    if missing:
        print(f"ERROR: .env에 다음 항목이 필요합니다: {', '.join(missing)}")
        sys.exit(1)

    client = NotionClient(
        token=token, api_url=api_url, api_path=api_path, api_version=api_version,
    )
    output_dir = PROJECT_ROOT / "output" / "graphrag"

    scraper = NotionScraper(client=client, output_dir=output_dir)
    scraper.run(database_id)
