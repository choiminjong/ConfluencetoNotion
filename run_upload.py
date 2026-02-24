"""Step 2: output 폴더를 선택하여 Notion DB에 업로드.

output/ 하위 폴더를 선택하고, Domain을 지정하여 Notion DB에 업로드한다.
.env에 NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_API_URL, NOTION_API_PATH, NOTION_API_VERSION 설정 필요.

사용법:
    uv run python run_upload.py                              대화형 폴더 선택
    uv run python run_upload.py AGUIDE_1427741158_20260222   폴더 직접 지정
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from upload.upload import NotionUploader


class UploadRunner:
    """Notion DB 업로드를 대화형으로 실행한다."""

    OUTPUT_BASE = Path("./output")

    def __init__(self):
        load_dotenv()

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
        self.domain = ""

    def select_folder(self) -> Path | None:
        """업로드할 output 하위 폴더를 선택한다."""
        if not self.OUTPUT_BASE.exists():
            print(f"ERROR: output 폴더가 없습니다: {self.OUTPUT_BASE}")
            return None

        folders = sorted(
            [d for d in self.OUTPUT_BASE.iterdir() if d.is_dir()],
            key=lambda d: d.name,
        )
        if not folders:
            print("업로드할 데이터가 없습니다. 먼저 run_convert.py를 실행하세요.")
            return None

        if len(sys.argv) >= 2:
            target = self.OUTPUT_BASE / sys.argv[1]
            if not target.exists():
                print(f"ERROR: 폴더를 찾을 수 없습니다: {target}")
                return None
            return target

        print("업로드 가능한 데이터 목록:\n")
        for i, folder in enumerate(folders, 1):
            index_path = folder / "index.json"
            page_count = ""
            if index_path.exists():
                index = json.loads(index_path.read_text(encoding="utf-8"))
                page_count = f" ({index.get('total_pages', '?')}페이지)"
            print(f"  {i}. {folder.name}{page_count}")

        print(f"\n선택 (1-{len(folders)}): ", end="")
        try:
            choice = int(input().strip())
            if choice < 1 or choice > len(folders):
                print("잘못된 선택입니다.")
                return None
            return folders[choice - 1]
        except (ValueError, EOFError):
            print("취소되었습니다.")
            return None

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
        """대화형 입력을 받고 업로드를 실행한다."""
        self.target_dir = self.select_folder()
        if not self.target_dir:
            sys.exit(1)

        self.domain = self.ask_domain()

        uploader = NotionUploader(
            token=self.token,
            database_id=self.database_id,
            api_url=self.api_url,
            api_path=self.api_path,
            api_version=self.api_version,
        )
        uploader.target_dir = self.target_dir
        uploader.CUSTOM_PROPERTIES = {"Domain": self.domain}

        print(f"\n{'=' * 50}")
        print(f"  대상 폴더 : {self.target_dir.name}")
        print(f"  Domain    : {self.domain}")
        print(f"  API       : {uploader.BASE}")
        print(f"  Version   : {uploader.headers['Notion-Version']}")
        print(f"{'=' * 50}\n")

        uploader.run()

        self.print_error_summary()

    def print_error_summary(self) -> None:
        """업로드 에러 리포트가 있으면 요약을 출력한다."""
        error_file = self.target_dir / "upload_errors.json"
        if not error_file.exists():
            return
        report = json.loads(error_file.read_text(encoding="utf-8"))
        failed = report.get("failed", 0)
        total = report.get("total_pages", 0)
        success = report.get("success", 0)
        if failed == 0:
            return
        print(f"\n{'=' * 50}")
        print(f"  업로드 결과: {total}개 중 {success}개 성공, {failed}개 실패")
        print(f"  에러 리포트: {error_file}")
        print(f"{'=' * 50}")


if __name__ == "__main__":
    UploadRunner().run()
