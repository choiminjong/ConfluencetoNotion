"""Phase 2 STEP 3: Notion DB에서 전체 페이지를 추출하여 Excel로 저장.

Notion DB의 모든 페이지를 조회하고, 각 페이지의 속성(Title, Space, Domain, Topics 등)과
블록 콘텐츠(본문 텍스트)를 추출하여 Excel 파일로 저장한다.

사용법:
    python -m graphrag.scraper.run

설정 (.env):
    NOTION_TOKEN        - Notion Integration 토큰
    NOTION_DATABASE_ID  - 대상 Notion DB ID
"""

import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[0] = str(PROJECT_ROOT)

import pandas as pd
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")


def main():
    from graphrag.scraper.block_parser import blocks_to_text
    from graphrag.scraper.notion_client import NotionClient

    token = os.getenv("NOTION_TOKEN", "")
    database_id = os.getenv("NOTION_DATABASE_ID", "")

    if not token or not database_id:
        print("ERROR: .env에 NOTION_TOKEN, NOTION_DATABASE_ID 설정 필요")
        sys.exit(1)

    client = NotionClient(token=token)

    print("=" * 60)
    print("Phase 2 STEP 3: Notion DB → Excel")
    print("=" * 60)

    print("\n[1/3] Notion DB 페이지 목록 조회 중...")
    pages = client.query_database(database_id)
    print(f"  총 {len(pages)}개 페이지 발견")

    print("\n[2/3] 각 페이지 속성 + 본문 추출 중...")
    records: list[dict] = []

    for i, page in enumerate(pages, 1):
        props = client.extract_page_properties(page)
        title = props.get("title", "Untitled")
        print(f"  ({i}/{len(pages)}) {title}")

        try:
            blocks = client.get_block_children(page["id"])
            content = blocks_to_text(blocks)
        except Exception as e:
            print(f"    WARN: 블록 읽기 실패 - {e}")
            content = ""

        records.append({
            "page_id": props.get("page_id", ""),
            "title": title,
            "content": content,
            "space": props.get("Space", ""),
            "domain": props.get("Domain", ""),
            "topics": props.get("Topics", ""),
            "parent_title": props.get("Parent Title", ""),
            "status": props.get("Status", ""),
            "source_url": props.get("Source URL", ""),
            "updated": props.get("Updated", ""),
        })

    print("\n[3/3] Excel 저장 중...")
    output_dir = PROJECT_ROOT / "output" / "graphrag"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"Pages_{timestamp}.xlsx"

    df = pd.DataFrame(records)
    df.to_excel(output_path, index=False, engine="openpyxl")

    print(f"  저장 완료: {output_path}")
    print(f"  총 {len(records)}개 페이지, 본문 있는 페이지: {sum(1 for r in records if r['content'])}개")
    print(f"\n{'=' * 60}")
    print(f"  다음 단계: python -m graphrag.graph.run")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
