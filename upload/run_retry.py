"""Phase 1 STEP 2-R: 실패한 페이지만 선별하여 Notion DB에 재업로드.

upload_errors.json이 있는 폴더를 스캔하고,
실패 목록을 확인한 뒤 재업로드를 실행한다.

사용법:
    python -m upload.run_retry                              대화형 폴더 선택
    python -m upload.run_retry officeitcc_608682203_20260225 폴더 직접 지정
"""

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path[0] = str(PROJECT_ROOT)

from dotenv import load_dotenv

from upload.upload import NotionUploader


class RetryRunner:
    """실패 페이지 재업로드를 대화형으로 실행한다."""

    OUTPUT_BASE = PROJECT_ROOT / "output"

    def __init__(self):
        load_dotenv(PROJECT_ROOT / ".env")

        self.token = os.getenv("NOTION_TOKEN", "")
        self.database_id = os.getenv("NOTION_DATABASE_ID", "")
        self.api_url = os.getenv("NOTION_API_URL", "")
        self.api_path = os.getenv("NOTION_API_PATH", "")
        self.api_version = os.getenv("NOTION_API_VERSION", "")

        missing = []
        if not self.token:
            missing.append("NOTION_TOKEN")
        if not self.database_id:
            missing.append("NOTION_DATABASE_ID")
        if not self.api_url:
            missing.append("NOTION_API_URL")
        if not self.api_path:
            missing.append("NOTION_API_PATH")
        if not self.api_version:
            missing.append("NOTION_API_VERSION")
        if missing:
            print(f"ERROR: .env에 다음 항목이 필요합니다: {', '.join(missing)}")
            sys.exit(1)

        self.target_dir: Path | None = None

    def _scan_retry_folders(self) -> list[tuple[Path, dict]]:
        """upload_errors.json이 있고 failed > 0인 폴더 목록을 반환한다."""
        if not self.OUTPUT_BASE.exists():
            return []

        results: list[tuple[Path, dict]] = []
        for d in sorted(self.OUTPUT_BASE.iterdir(), key=lambda p: p.name):
            if not d.is_dir():
                continue
            err_path = d / "upload_errors.json"
            if not err_path.exists():
                continue
            report = json.loads(err_path.read_text(encoding="utf-8"))
            if report.get("failed", 0) > 0:
                results.append((d, report))
        return results

    def select_folder(self) -> tuple[Path, dict] | None:
        """재업로드할 폴더를 선택한다."""
        if not self.OUTPUT_BASE.exists():
            print(f"ERROR: output 폴더가 없습니다: {self.OUTPUT_BASE}")
            return None

        retry_folders = self._scan_retry_folders()
        if not retry_folders:
            print("재업로드할 실패 페이지가 있는 폴더가 없습니다.")
            return None

        if len(sys.argv) >= 2:
            target = self.OUTPUT_BASE / sys.argv[1]
            err_path = target / "upload_errors.json"
            if not err_path.exists():
                print(f"ERROR: {err_path} 파일이 없습니다.")
                return None
            report = json.loads(err_path.read_text(encoding="utf-8"))
            if report.get("failed", 0) == 0:
                print("실패한 페이지가 없습니다. 재업로드 불필요.")
                return None
            return target, report

        print("재업로드 가능한 폴더 목록:\n")
        for i, (folder, report) in enumerate(retry_folders, 1):
            failed = report.get("failed", 0)
            total = report.get("total_pages", 0)
            success = report.get("success", 0)
            print(f"  {i}. {folder.name}  ({total}개 중 {success}개 성공, {failed}개 실패)")

        print(f"\n선택 (1-{len(retry_folders)}): ", end="")
        try:
            choice = int(input().strip())
            if choice < 1 or choice > len(retry_folders):
                print("잘못된 선택입니다.")
                return None
            return retry_folders[choice - 1]
        except (ValueError, EOFError):
            print("취소되었습니다.")
            return None

    @staticmethod
    def show_failed_pages(report: dict) -> list[dict]:
        """실패 페이지 목록을 출력하고 errors 리스트를 반환한다."""
        errors = report.get("errors", [])
        print(f"\n실패 페이지 목록 ({len(errors)}건):\n")
        for i, err in enumerate(errors, 1):
            print(f"  {i}. [{err['page_id']}] {err.get('title', '')}  ({err.get('error_type', '')})")
        return errors

    def ask_domain(self) -> str:
        """Domain 값을 입력받는다."""
        print("\nDomain을 입력하세요 (문서의 주제 영역):")
        print("  예: Jira, Confluence, CI/CD, Security, Infra, Onboarding")
        print("  (Enter 누르면 기본값 'Jira')\n")
        print("Domain: ", end="")
        try:
            value = input().strip()
            return value if value else "Jira"
        except EOFError:
            return "Jira"

    def run(self):
        """대화형 입력을 받고 실패 페이지를 재업로드한다."""
        result = self.select_folder()
        if not result:
            sys.exit(1)

        self.target_dir, report = result
        errors = self.show_failed_pages(report)

        if not errors:
            print("재업로드할 페이지가 없습니다.")
            return

        domain = self.ask_domain()

        uploader = NotionUploader(
            token=self.token,
            database_id=self.database_id,
            api_url=self.api_url,
            api_path=self.api_path,
            api_version=self.api_version,
        )
        uploader.target_dir = self.target_dir
        uploader.CUSTOM_PROPERTIES = {"Domain": domain}

        print(f"\n{'=' * 50}")
        print(f"  대상 폴더 : {self.target_dir.name}")
        print(f"  재업로드  : {len(errors)}개 페이지")
        print(f"  Domain    : {domain}")
        print(f"  API       : {uploader.BASE}")
        print(f"{'=' * 50}\n")

        uploader.load_db_schema()
        uploader.ensure_properties()

        page_ids = [e["page_id"] for e in errors]
        uploader.retry(page_ids)

        self.print_result_summary()

    def print_result_summary(self) -> None:
        """재업로드 결과 요약을 출력한다."""
        error_file = self.target_dir / "upload_errors.json"
        if not error_file.exists():
            return
        report = json.loads(error_file.read_text(encoding="utf-8"))
        failed = report.get("failed", 0)
        total = report.get("total_pages", 0)
        success = report.get("success", 0)
        print(f"\n{'=' * 50}")
        print(f"  전체 결과: {total}개 중 {success}개 성공, {failed}개 실패")
        if failed > 0:
            print(f"  에러 리포트: {error_file}")
        else:
            print("  모든 페이지 업로드 완료!")
        print(f"{'=' * 50}")


if __name__ == "__main__":
    RetryRunner().run()
