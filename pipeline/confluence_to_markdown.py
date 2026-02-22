"""Step 1: Confluence 페이지를 Markdown + 첨부파일 + meta.json 으로 변환한다."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from urllib.parse import unquote

from atlassian import Confluence as ConfluenceClient
from bs4 import Tag
from tabulate import tabulate

import confluence_markdown_exporter.api_clients as _api
from confluence_markdown_exporter.utils.app_data_store import set_setting
from confluence_markdown_exporter.utils.table_converter import pad


class TableOverride:
    """테이블 HTML -> Markdown 변환 오버라이드.

    중첩 테이블은 HTML 유지, 이미지는 텍스트 링크로 대체 후 하단에 배치한다.
    """

    BLOCK_TAGS = frozenset({
        "p", "h1", "h2", "h3", "h4", "h5", "h6",
        "div", "ul", "ol", "blockquote", "pre",
    })

    def __init__(self, converter, el):
        self.converter = converter
        self.el = el

    def extract_images(self) -> list[str]:
        """이미지를 텍스트 링크로 대체하고, 하단 배치용 마크다운 목록을 반환한다."""
        extracted: list[str] = []
        for img in self.el.find_all("img"):
            src = img.get("data-image-src") or img.get("src") or ""
            alt = img.get("alt") or ""
            raw_name = unquote(src.rsplit("/", 1)[-1]) if src else alt or "image"
            filename = raw_name.split("?")[0]
            img.replace_with(f"📎 {filename}")
            extracted.append(f"**📎 {filename}**\n\n![{alt}]({src})")
        return extracted

    def cell_to_text(self, cell: Tag) -> str:
        """단일 셀을 마크다운 텍스트로 변환한다."""
        block_children = [
            child for child in cell.children
            if isinstance(child, Tag) and child.name in self.BLOCK_TAGS
        ]
        if len(block_children) > 1:
            parts = []
            for child in block_children:
                md = self.converter.convert(str(child)).strip()
                md = re.sub(r"^#{1,6}\s+", "", md)
                md = md.replace("\n", "<br>")
                if md:
                    parts.append(md)
            result = "<br>".join(parts)
        else:
            inner_html = cell.decode_contents()
            result = self.converter.convert(inner_html).strip()
            result = re.sub(r"^#{1,6}\s+", "", result)
            result = re.sub(r"\n+", "<br>", result)
        result = result.replace("****", "**<br>**")
        return result

    def convert(self) -> str:
        """테이블 전체를 마크다운으로 변환한다."""
        if self.el.find("table"):
            return "\n\n" + str(self.el) + "\n\n"

        extracted_images = self.extract_images()

        rows = [
            cast("list[Tag]", tr.find_all(["td", "th"]))
            for tr in cast("list[Tag]", self.el.find_all("tr"))
            if tr
        ]
        if not rows:
            return ""

        padded_rows = pad(rows)
        converted = [[self.cell_to_text(cell) for cell in row] for row in padded_rows]

        has_header = all(cell.name == "th" for cell in rows[0])
        if has_header:
            result = "\n\n" + tabulate(converted[1:], headers=converted[0], tablefmt="pipe") + "\n\n"
        else:
            result = "\n\n" + tabulate(converted, headers=[""] * len(converted[0]), tablefmt="pipe") + "\n\n"

        if extracted_images:
            result += "\n\n".join(extracted_images) + "\n\n"

        return result


def _convert_table_custom(self, el, text, parent_tags):
    return TableOverride(self, el).convert()


class ConfluenceExporter:
    """Confluence 페이지를 Markdown + 첨부파일 + meta.json 폴더 구조로 변환한다."""

    def __init__(self, url: str, pat: str, output_dir: str, page_ids: list[int],
                 include_descendants: bool = False, download_all_attachments: bool = False):
        self.url = url.rstrip("/")
        self.client = ConfluenceClient(url=url, token=pat)
        self.output_dir = Path(output_dir)
        self.page_ids = page_ids
        self.include_descendants = include_descendants
        self.download_all_attachments = download_all_attachments
        self.exported: dict[int, dict] = {}

        _api.get_confluence_instance = lambda: self.client
        set_setting("export.page_breadcrumbs", False)

        from confluence_markdown_exporter.confluence import Page
        self.Page = Page
        self.Page.Converter.convert_table = _convert_table_custom

    def rewrite_image_paths(self, markdown: str) -> str:
        """Confluence Server URL 형식의 이미지 경로를 로컬 파일명으로 치환한다."""
        return re.sub(
            r"/download/attachments/\d+/([^?)]+)\??[^)]*",
            lambda m: unquote(m.group(1)),
            markdown,
        )

    def extract_referenced_files(self, markdown: str) -> set[str]:
        """마크다운에서 참조하는 로컬 파일명 목록을 추출한다."""
        refs: set[str] = set()
        for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", markdown):
            src = m.group(1)
            if not src.startswith(("http://", "https://")):
                refs.add(unquote(src))
        return refs

    def download_attachments(self, page, page_dir: Path, referenced: set[str] | None = None) -> list[str]:
        """첨부파일을 page_dir에 다운로드한다.

        referenced가 주어지면 해당 파일만, None이면 모든 첨부파일을 다운로드한다.
        """
        downloaded: list[str] = []
        for att in page.attachments:
            if referenced is not None and att.title not in referenced:
                continue
            try:
                resp = self.client._session.get(self.url + att.download_link)
                resp.raise_for_status()
                (page_dir / att.title).write_bytes(resp.content)
                downloaded.append(att.title)
            except Exception as e:
                print(f"  WARN: 첨부파일 다운로드 실패 '{att.title}': {e}")
        return downloaded

    def export_page(self, page_id: int) -> dict | None:
        """단일 페이지를 폴더 단위(confluence.md + 첨부파일 + meta.json)로 내보낸다."""
        raw = self.client.get_page_by_id(page_id, expand="version,ancestors")
        version = raw.get("version", {})
        last_updated = version.get("when", "")
        raw_ancestors = raw.get("ancestors", [])

        page = self.Page.from_id(page_id)
        if page.title == "Page not accessible":
            print(f"  SKIP: {page_id} (접근 불가)")
            return None

        page_dir = self.output_dir / str(page_id)
        page_dir.mkdir(parents=True, exist_ok=True)

        markdown = self.rewrite_image_paths(page.markdown)
        (page_dir / "confluence.md").write_text(markdown, encoding="utf-8")

        referenced = None if self.download_all_attachments else self.extract_referenced_files(markdown)
        downloaded = self.download_attachments(page, page_dir, referenced)

        parent_id = raw_ancestors[-1]["id"] if raw_ancestors else None
        depth = len(raw_ancestors)

        meta = {
            "id": page_id,
            "title": page.title,
            "space": page.space.name,
            "space_key": page.space.key,
            "updated": last_updated,
            "source_url": f"{self.url}/pages/viewpage.action?pageId={page_id}",
            "parent_id": int(parent_id) if parent_id else None,
            "depth": depth,
            "children": [],
            "attachments": downloaded,
        }
        (page_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self.exported[page_id] = meta

        print(f"  Title: {page.title}")
        print(f"  Space: {page.space.name}")
        print(f"  Updated: {last_updated}")
        print(f"  Depth: {depth}")
        print(f"  Attachments: {len(downloaded)}")
        print(f"  Output: {page_dir}")
        return meta

    def get_child_page_ids(self, page_id: int) -> list[int]:
        """특정 페이지의 직접 자식 페이지 ID 목록을 반환한다. (CQL 불사용)"""
        children: list[int] = []
        start = 0
        limit = 100
        while True:
            results = self.client.get_page_child_by_type(
                page_id, type="page", start=start, limit=limit,
            )
            if not results:
                break
            for child in results:
                children.append(int(child["id"]))
            if len(results) < limit:
                break
            start += limit
        return children

    def collect_page_ids(self) -> list[int]:
        """include_descendants 가 True 면 child API 를 재귀 호출하여 하위 페이지를 수집한다."""
        if not self.include_descendants:
            return list(self.page_ids)

        all_ids: list[int] = []
        queue = list(self.page_ids)

        while queue:
            pid = queue.pop(0)
            if pid in all_ids:
                continue
            all_ids.append(pid)
            for child_id in self.get_child_page_ids(pid):
                if child_id not in all_ids:
                    queue.append(child_id)

        print(
            f"  수집된 페이지: {len(all_ids)}개"
            f" (원본 {len(self.page_ids)} + 하위 {len(all_ids) - len(self.page_ids)})"
        )
        return all_ids

    def update_children(self) -> None:
        """각 meta.json 의 children 필드를 채우고 파일을 갱신한다."""
        for page_id, meta in self.exported.items():
            meta["children"] = [
                pid
                for pid, m in self.exported.items()
                if m.get("parent_id") == page_id
            ]
            meta_path = self.output_dir / str(page_id) / "meta.json"
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def write_index_json(self) -> None:
        """output/index.json 에 페이지 트리 구조를 저장한다."""

        def build_tree(parent_id: int | None) -> list[dict]:
            nodes = []
            for page_id, meta in self.exported.items():
                if meta.get("parent_id") == parent_id:
                    nodes.append({
                        "id": page_id,
                        "title": meta["title"],
                        "depth": meta["depth"],
                        "children": build_tree(page_id),
                    })
            return nodes

        root_ids = {m.get("parent_id") for m in self.exported.values()}
        exported_ids = set(self.exported.keys())
        top_parent_ids = root_ids - exported_ids

        tree: list[dict] = []
        for top_id in top_parent_ids:
            tree.extend(build_tree(top_id))
        if not tree:
            tree = build_tree(None)

        index = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "total_pages": len(self.exported),
            "include_descendants": self.include_descendants,
            "tree": tree,
        }
        index_path = self.output_dir / "index.json"
        index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Index: {index_path}")

    def export_pages(self) -> None:
        """전체 실행: 페이지 수집 → 변환 → children 갱신 → index.json 생성."""
        print(f"URL: {self.url}")
        print(f"Pages: {self.page_ids}")
        print(f"Include descendants: {self.include_descendants}\n")

        all_ids = self.collect_page_ids()
        print()

        for pid in all_ids:
            print(f"[Page {pid}]")
            try:
                self.export_page(pid)
            except Exception as e:
                print(f"  ERROR: {e}")
            print()

        self.update_children()
        self.write_index_json()
        print(f"Done. {len(self.exported)} pages exported to {self.output_dir}")


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    exporter = ConfluenceExporter(
        url=os.getenv("CONFLUENCE_URL", ""),
        pat=os.getenv("CONFLUENCE_PAT", ""),
        output_dir="./output",
        page_ids=[1427741158],
        include_descendants=True,
    )
    exporter.export_pages()
