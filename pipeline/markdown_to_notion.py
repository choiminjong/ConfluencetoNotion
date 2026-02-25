"""Step 2: Confluence Markdown 을 전처리하고 Notion 블록 JSON 으로 변환한다."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from notion_markdown import to_notion

from pipeline.md_preprocessor import preprocess, strip_frontmatter
from pipeline.notion_postprocessor import extract_local_media, postprocess


class NotionConverter:
    """Confluence Markdown 을 Notion API 블록 JSON 으로 변환한다."""

    def __init__(self, output_dir: str = str(Path(__file__).resolve().parent.parent / "output")):
        self.output_dir = Path(output_dir)
        self.errors: list[dict] = []

    def convert_page(self, page_dir: Path) -> dict | None:
        """단일 페이지 폴더의 confluence.md -> notion.json 변환."""
        md_path = page_dir / "confluence.md"
        meta_path = page_dir / "meta.json"

        if not md_path.exists() or not meta_path.exists():
            print(f"  SKIP: {page_dir.name} (confluence.md 또는 meta.json 없음)")
            return None

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        raw_md = md_path.read_text(encoding="utf-8")

        raw_md, tags = strip_frontmatter(raw_md)
        processed_md = preprocess(raw_md)

        blocks = to_notion(processed_md)
        blocks = postprocess(blocks)
        local_media = extract_local_media(blocks)

        result = {
            "page_id": meta["id"],
            "title": meta["title"],
            "tags": tags,
            "blocks": blocks,
            "local_media": local_media,
        }

        (page_dir / "notion.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"  Title: {meta['title']}")
        print(f"  Blocks: {len(blocks)}")
        print(f"  Local media: {len(local_media)}")
        return result

    def _save_error_report(self, total: int, success: int) -> None:
        """수집된 에러를 convert_errors.json 에 병합 저장한다."""
        report_path = self.output_dir / "convert_errors.json"
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["errors"].extend(self.errors)
            report["failed"] = len(report["errors"])
            report["success"] = report["total_pages"] - report["failed"]
        else:
            report = {
                "run_dir": str(self.output_dir),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_pages": total,
                "success": success,
                "failed": len(self.errors),
                "errors": self.errors,
            }
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
        )

    def convert_all(self) -> None:
        """output/ 하위 모든 페이지 폴더를 순회하며 변환한다."""
        page_dirs = sorted(
            [d for d in self.output_dir.iterdir() if d.is_dir()],
            key=lambda d: d.name,
        )

        if not page_dirs:
            print("변환할 페이지 폴더가 없습니다.")
            return

        print(f"Notion 블록 변환 시작: {len(page_dirs)}개 페이지\n")

        converted = 0
        for page_dir in page_dirs:
            print(f"[Page {page_dir.name}]")
            try:
                result = self.convert_page(page_dir)
                if result:
                    converted += 1
            except Exception as e:
                meta_path = page_dir / "meta.json"
                title = ""
                if meta_path.exists():
                    title = json.loads(meta_path.read_text(encoding="utf-8")).get("title", "")
                self.errors.append({
                    "page_id": page_dir.name,
                    "title": title,
                    "step": "convert_md_to_notion",
                    "error_type": type(e).__name__,
                    "message": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                print(f"  ERROR: {e}")
            print()

        if self.errors:
            self._save_error_report(len(page_dirs), converted)

        print(f"Done. {converted}/{len(page_dirs)} pages converted to notion.json")


if __name__ == "__main__":
    converter = NotionConverter()
    converter.convert_all()
