"""Step 2: Confluence Markdown 을 전처리하고 Notion 블록 JSON 으로 변환한다."""

import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, Tag

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from notion_markdown import to_notion


class NotionConverter:
    """Confluence Markdown 을 Notion API 블록 JSON 으로 변환한다."""

    def __init__(self, output_dir: str = "./output"):
        self.output_dir = Path(output_dir)

        self.alert_icons = {
            "TIP": "💡",
            "WARNING": "⚠️",
            "NOTE": "📝",
            "CAUTION": "🚨",
            "IMPORTANT": "❗",
        }

        self.alert_pattern = re.compile(
            r"^> \[!(TIP|WARNING|NOTE|CAUTION|IMPORTANT)\]\s*\n"
            r"((?:^>.*\n?)+)",
            re.MULTILINE,
        )

        self.bold_heading_pattern = re.compile(
            r"^(#{1,3})\s+\*\*(.+?)\*\*\s*$",
            re.MULTILINE,
        )

        self.confluence_link_pattern = re.compile(
            r"\[([^\]]+)\]\(/pages/viewpage\.action\?pageId=\d+\)"
        )

        self.html_table_pattern = re.compile(
            r"<table[\s>].*?</table>",
            re.DOTALL,
        )

        self.list_heading_pattern = re.compile(
            r"^(\s*[-*+]\s+)#{1,6}\s+(.+)$",
            re.MULTILINE,
        )

    def convert_alerts_to_callouts(self, markdown: str) -> str:
        """GitHub Alert (`> [!TIP]` 등) 을 `<aside>` 태그로 변환한다."""

        def replace_alert(m: re.Match) -> str:
            alert_type = m.group(1)
            icon = self.alert_icons.get(alert_type, "💡")
            body_lines = m.group(2).strip().splitlines()
            content_parts: list[str] = []
            for line in body_lines:
                stripped = re.sub(r"^>\s?", "", line)
                stripped = re.sub(r"^###?\s*", "", stripped)
                if stripped.strip():
                    content_parts.append(stripped.strip())
            content = " ".join(content_parts)
            return f"<aside>{icon} {content}</aside>\n"

        return self.alert_pattern.sub(replace_alert, markdown)

    def strip_bold_headings(self, markdown: str) -> str:
        """헤딩 내부의 불필요한 bold 마크를 제거한다. `# **text**` → `# text`"""
        return self.bold_heading_pattern.sub(r"\1 \2", markdown)

    def strip_confluence_links(self, markdown: str) -> str:
        """Confluence 내부 링크를 텍스트만 남기고 제거한다."""

        def _replace(m: re.Match) -> str:
            text = m.group(1)
            text = re.sub(r"^(\d+)\.", r"\1\\.", text)
            return text

        return self.confluence_link_pattern.sub(_replace, markdown)

    def convert_list_headings(self, markdown: str) -> str:
        """리스트 안의 heading 마크를 bold 로 변환한다. `- ### text` → `- **text**`"""
        return self.list_heading_pattern.sub(r"\1**\2**", markdown)

    def convert_html_tables(self, markdown: str) -> str:
        """Markdown 내 잔존 HTML <table> 블록을 pipe 테이블로 변환한다."""

        def _table_to_pipe(m: re.Match) -> str:
            soup = BeautifulSoup(m.group(0), "html.parser")
            table = soup.find("table")
            if not table:
                return m.group(0)

            rows: list[list[str]] = []
            for tr in table.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                rows.append([c.get_text(" ", strip=True) for c in cells])

            if not rows:
                return m.group(0)

            col_count = max(len(r) for r in rows)
            for row in rows:
                while len(row) < col_count:
                    row.append("")

            header = rows[0]
            body = rows[1:] if len(rows) > 1 else []

            lines = ["| " + " | ".join(header) + " |"]
            lines.append("|" + "|".join(" --- " for _ in header) + "|")
            for row in body:
                lines.append("| " + " | ".join(row) + " |")

            return "\n\n" + "\n".join(lines) + "\n\n"

        return self.html_table_pattern.sub(_table_to_pipe, markdown)

    def extract_local_images(self, blocks: list[dict]) -> list[str]:
        """Notion 블록 목록에서 로컬 이미지 파일명을 추출한다."""
        images: list[str] = []
        for block in blocks:
            if block.get("type") != "image":
                continue
            url = block.get("image", {}).get("external", {}).get("url", "")
            if url and not url.startswith("http"):
                images.append(url)
        return images

    def preprocess_markdown(self, markdown: str) -> str:
        """notion-markdown 이 올바르게 처리할 수 있도록 Confluence 고유 패턴을 변환한다."""
        md = markdown
        md = self.convert_alerts_to_callouts(md)
        md = self.strip_bold_headings(md)
        md = self.strip_confluence_links(md)
        md = self.convert_list_headings(md)
        md = self.convert_html_tables(md)
        return md

    def convert_page(self, page_dir: Path) -> dict | None:
        """단일 페이지 폴더의 confluence.md → notion.json 변환."""
        md_path = page_dir / "confluence.md"
        meta_path = page_dir / "meta.json"

        if not md_path.exists() or not meta_path.exists():
            print(f"  SKIP: {page_dir.name} (confluence.md 또는 meta.json 없음)")
            return None

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        raw_md = md_path.read_text(encoding="utf-8")
        processed_md = self.preprocess_markdown(raw_md)

        blocks = to_notion(processed_md)
        local_images = self.extract_local_images(blocks)

        result = {
            "page_id": meta["id"],
            "title": meta["title"],
            "blocks": blocks,
            "local_images": local_images,
        }

        (page_dir / "notion.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"  Title: {meta['title']}")
        print(f"  Blocks: {len(blocks)}")
        print(f"  Local images: {len(local_images)}")
        return result

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
                print(f"  ERROR: {e}")
            print()

        print(f"Done. {converted}/{len(page_dirs)} pages converted to notion.json")


if __name__ == "__main__":
    converter = NotionConverter()
    converter.convert_all()
