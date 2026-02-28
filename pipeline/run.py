"""Phase 1 STEP 1: Confluence -> Markdown -> Notion JSON 변환.

Confluence 페이지를 가져와서 output/ 폴더에 저장한다.
.env에 CONFLUENCE_URL, CONFLUENCE_PAT 설정 필요.

사용법:
    python -m pipeline.run

설정 (.env):
    CONFLUENCE_PAGE_IDS      - 가져올 Confluence 루트 페이지 ID (쉼표 구분)

설정 (코드):
    include_descendants      - True면 하위 페이지도 전부 가져옴
    download_all_attachments - True면 본문에 없는 첨부파일도 다운로드
    include_document_title   - False면 MD에 페이지 제목 H1 미포함 (Notion 제목과 중복 방지)
    page_breadcrumbs         - False면 MD 상단 경로 미포함
    run_step1                - Confluence -> Markdown 변환
    run_step2                - Markdown -> Notion JSON 변환
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path[0] = str(PROJECT_ROOT)

from atlassian import Confluence
from dotenv import load_dotenv


class Pipeline:
    """Confluence -> Markdown -> Notion 변환 파이프라인."""

    def __init__(
        self,
        output_base: str = str(PROJECT_ROOT / "output"),
        include_descendants: bool = True,
        download_all_attachments: bool = False,
        include_document_title: bool = True,
        page_breadcrumbs: bool = False,
        run_step1: bool = True,
        run_step2: bool = True,
    ):
        load_dotenv(PROJECT_ROOT / ".env")

        self.confluence_url = os.getenv("CONFLUENCE_URL", "")
        self.confluence_pat = os.getenv("CONFLUENCE_PAT", "")
        page_ids_raw = os.getenv("CONFLUENCE_PAGE_IDS", "")

        if not self.confluence_url or not self.confluence_pat or not page_ids_raw:
            print("ERROR: .env에 CONFLUENCE_URL, CONFLUENCE_PAT, CONFLUENCE_PAGE_IDS 설정 필요")
            sys.exit(1)

        self.page_ids = [int(pid.strip()) for pid in page_ids_raw.split(",") if pid.strip()]
        self.output_base = output_base
        self.include_descendants = include_descendants
        self.download_all_attachments = download_all_attachments
        self.include_document_title = include_document_title
        self.page_breadcrumbs = page_breadcrumbs
        self.run_step1 = run_step1
        self.run_step2 = run_step2

        self.run_dir = ""

    def resolve_run_dir(self) -> str:
        """루트 페이지의 space_key를 조회하여 실행 폴더 경로를 결정한다."""
        Path(self.output_base).mkdir(parents=True, exist_ok=True)

        client = Confluence(url=self.confluence_url, token=self.confluence_pat)
        root_id = self.page_ids[0]
        page = client.get_page_by_id(root_id, expand="space")
        space_key = page["space"]["key"]
        today = datetime.now().strftime("%Y%m%d")
        self.run_dir = os.path.join(self.output_base, f"{space_key}_{root_id}_{today}")
        return self.run_dir

    def print_step(self, step: int, title: str) -> None:
        print("=" * 60)
        print(f"Step {step}: {title}")
        print("=" * 60 + "\n")

    def step1_confluence_to_markdown(self) -> None:
        """Step 1: Confluence 페이지를 Markdown + 첨부파일로 변환한다."""
        self.print_step(1, "Confluence -> Markdown")

        from pipeline.confluence_to_markdown import ConfluenceExporter

        exporter = ConfluenceExporter(
            url=self.confluence_url,
            pat=self.confluence_pat,
            output_dir=self.run_dir,
            page_ids=self.page_ids,
            include_descendants=self.include_descendants,
            download_all_attachments=self.download_all_attachments,
            include_document_title=self.include_document_title,
            page_breadcrumbs=self.page_breadcrumbs,
        )
        exporter.export_pages()
        print()

    def step2_markdown_to_notion(self) -> None:
        """Step 2: Markdown을 Notion API 블록 JSON으로 변환한다."""
        self.print_step(2, "Markdown -> Notion 블록 JSON")

        from pipeline.markdown_to_notion import NotionConverter

        converter = NotionConverter(output_dir=self.run_dir)
        converter.convert_all()

    def print_error_summary(self) -> None:
        """에러 리포트 파일이 있으면 요약을 출력한다."""
        error_file = Path(self.run_dir) / "convert_errors.json"
        if not error_file.exists():
            return
        report = json.loads(error_file.read_text(encoding="utf-8"))
        failed = report.get("failed", 0)
        total = report.get("total_pages", 0)
        success = report.get("success", 0)
        if failed == 0:
            return
        print(f"\n{'=' * 60}")
        print(f"  변환 결과: {total}개 중 {success}개 성공, {failed}개 실패")
        print(f"  에러 리포트: {error_file}")
        print(f"{'=' * 60}")

    def run(self) -> None:
        """설정된 단계를 순서대로 실행한다."""
        self.resolve_run_dir()
        print(f"Output: {self.run_dir}\n")

        if self.run_step1:
            self.step1_confluence_to_markdown()
        if self.run_step2:
            self.step2_markdown_to_notion()

        self.print_error_summary()


def main():
    Pipeline(
        include_descendants=True,
        download_all_attachments=False,
        include_document_title=False,
        page_breadcrumbs=False,
        run_step1=True,
        run_step2=True,
    ).run()


if __name__ == "__main__":
    main()
