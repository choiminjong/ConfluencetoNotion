"""Step 1: Confluence 페이지를 Markdown + 첨부파일 + meta.json 으로 변환한다."""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from atlassian import Confluence as ConfluenceClient

import confluence_markdown_exporter.api_clients as _api
from confluence_markdown_exporter.utils.app_data_store import set_setting

from pipeline.converter_overrides import (
    apply_overrides,
    replace_emoticon_markdown,
    reset_unsupported_macros,
    unsupported_macros,
)
from pipeline.md_preprocessor import VIDEO_EXT_PATTERN


class ConfluenceExporter:
    """Confluence 페이지를 Markdown + 첨부파일 + meta.json 폴더 구조로 변환한다."""

    def __init__(self, url: str, pat: str, output_dir: str, page_ids: list[int],
                 include_descendants: bool = False, download_all_attachments: bool = False,
                 include_document_title: bool = True, page_breadcrumbs: bool = False):
        self.url = url.rstrip("/")
        self.client = ConfluenceClient(url=url, token=pat)
        self.output_dir = Path(output_dir)
        self.page_ids = page_ids
        self.include_descendants = include_descendants
        self.download_all_attachments = download_all_attachments
        self.exported: dict[int, dict] = {}
        self.skipped_parents: dict[int, int | None] = {}
        self.errors: list[dict] = []

        _api.get_confluence_instance = lambda: self.client
        set_setting("export.page_breadcrumbs", page_breadcrumbs)
        set_setting("export.include_document_title", include_document_title)

        from confluence_markdown_exporter.confluence import Page
        self.Page = Page
        apply_overrides(self.Page.Converter)

    _VIDEO_LINK_RE = re.compile(
        rf"\[([^\]]+\.(?:{VIDEO_EXT_PATTERN}))\]\([^)]+\)",
        re.IGNORECASE,
    )

    def rewrite_image_paths(self, markdown: str) -> str:
        """Confluence Server URL 형식의 이미지 경로를 로컬 파일명으로 치환한다."""
        return re.sub(
            r"/download/attachments/\d+/([^?)]+)\??[^)]*",
            lambda m: unquote(m.group(1)),
            markdown,
        )

    def rewrite_video_paths(self, markdown: str) -> str:
        """비디오 링크의 깨진 상대경로를 파일명으로 교체한다.

        `[name.mp4](..\\..\\attachments\\.mp4)` -> `[name.mp4](name.mp4)`
        """
        def _replace(m: re.Match) -> str:
            filename = m.group(1)
            return f"[{filename}]({filename})"

        return self._VIDEO_LINK_RE.sub(_replace, markdown)

    def inject_tab_children(self, page_id: int, markdown: str) -> str:
        """TAB_CHILDREN 플레이스홀더를 실제 하위 페이지 이름으로 교체하고 blockquote를 정리한다."""
        if "<!-- TAB_CHILDREN:" not in markdown:
            return markdown

        category_map: dict[str, list[str]] = {}
        for child_id in self.get_child_page_ids(page_id):
            child = self.client.get_page_by_id(child_id)
            cat_title = child["title"]
            grandchildren = []
            for gc_id in self.get_child_page_ids(child_id):
                gc = self.client.get_page_by_id(gc_id)
                grandchildren.append(gc["title"])
            category_map[cat_title] = grandchildren

        for cat_title, names in category_map.items():
            placeholder = f"<!-- TAB_CHILDREN:{cat_title} -->"
            if names:
                bullet_list = "\n".join(f"- {n}" for n in names)
            else:
                bullet_list = "- (하위 페이지 없음)"
            markdown = markdown.replace(placeholder, bullet_list)

        markdown = re.sub(r"<!-- TAB_CHILDREN:[^>]+ -->", "- (하위 페이지 참조)", markdown)
        markdown = self._clean_tabs_blockquote(markdown)
        return markdown

    @staticmethod
    def _clean_tabs_blockquote(markdown: str) -> str:
        """blockquote 안의 <details> 블록을 최상위로 추출한다.

        Confluence panel 매크로가 blockquote로 변환되면서
        <details> 블록이 > 접두사에 감싸이는 문제를 해결한다.
        """
        lines = markdown.split("\n")
        result: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if (
                line.strip() in ("> [!NOTE]", "> [!TIP]", "> [!WARNING]")
                and i + 1 < len(lines)
                and "<details>" in lines[i + 1]
            ):
                i += 1
                while i < len(lines):
                    ln = lines[i]
                    if ln.startswith("> "):
                        result.append(ln[2:])
                    elif ln.strip() == ">":
                        result.append("")
                    elif ln.startswith(">"):
                        result.append(ln[1:])
                    else:
                        result.append(ln)
                    if not ln.startswith(">") and not ln.strip().startswith("-") and ln.strip() == "":
                        peek = i + 1
                        if peek >= len(lines) or not lines[peek].startswith(">"):
                            i += 1
                            break
                    i += 1
            else:
                result.append(line)
                i += 1
        return "\n".join(result)

    def extract_referenced_files(self, markdown: str) -> set[str]:
        """마크다운에서 참조하는 로컬 파일명(이미지 + 비디오) 목록을 추출한다."""
        refs: set[str] = set()
        for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", markdown):
            src = m.group(1)
            if not src.startswith(("http://", "https://")):
                refs.add(unquote(src))
        for m in self._VIDEO_LINK_RE.finditer(markdown):
            refs.add(m.group(1))
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

        self.Page.Converter._current_page_id = page_id
        markdown = self.rewrite_image_paths(page.markdown)
        markdown = self.rewrite_video_paths(markdown)
        markdown = replace_emoticon_markdown(markdown)
        markdown = self.inject_tab_children(page_id, markdown)

        if len(markdown.strip()) < 10:
            print(f"  SKIP: '{page.title}' (빈 컨테이너 페이지)")
            parent_id = raw_ancestors[-1]["id"] if raw_ancestors else None
            self.skipped_parents[page_id] = int(parent_id) if parent_id else None
            return None

        page_dir = self.output_dir / str(page_id)
        page_dir.mkdir(parents=True, exist_ok=True)

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

    def _resolve_parent(self, parent_id: int | None) -> int | None:
        """SKIP된 부모를 건너뛰고 가장 가까운 내보낸 조상 ID를 반환한다."""
        visited: set[int] = set()
        while parent_id is not None and parent_id not in self.exported:
            if parent_id in visited:
                return None
            visited.add(parent_id)
            parent_id = self.skipped_parents.get(parent_id)
        return parent_id

    def update_children(self) -> None:
        """각 meta.json 의 children 필드를 채우고 파일을 갱신한다.

        SKIP된 컨테이너 페이지의 자식은 가장 가까운 내보낸 조상에 연결한다.
        """
        for page_id, meta in self.exported.items():
            meta["parent_id"] = self._resolve_parent(meta.get("parent_id"))
            meta_path = self.output_dir / str(page_id) / "meta.json"
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

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

    def _save_error_report(self) -> None:
        """수집된 에러를 convert_errors.json 으로 저장한다."""
        report = {
            "run_dir": str(self.output_dir),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_pages": len(self.exported) + len(self.errors),
            "success": len(self.exported),
            "failed": len(self.errors),
            "errors": self.errors,
        }
        path = self.output_dir / "convert_errors.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def _save_unsupported_macros_report(self) -> None:
        """미지원 매크로를 unsupported_macros.json 으로 저장한다."""
        if not unsupported_macros:
            return

        grouped: dict[str, list[str]] = {}
        for entry in unsupported_macros:
            name = entry["macro_name"]
            pid = entry["page_id"]
            grouped.setdefault(name, [])
            if pid not in grouped[name]:
                grouped[name].append(pid)

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_unique_macros": len(grouped),
            "macros": [
                {"macro_name": name, "pages": pages}
                for name, pages in sorted(grouped.items())
            ],
        }
        path = self.output_dir / "unsupported_macros.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"\n  미지원 매크로 {len(grouped)}종 감지 → {path}")
        for name, pages in sorted(grouped.items()):
            print(f"    - {name} ({len(pages)}개 페이지)")

    def export_pages(self) -> None:
        """전체 실행: 페이지 수집 → 변환 → children 갱신 → index.json 생성."""
        reset_unsupported_macros()

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
                self.errors.append({
                    "page_id": str(pid),
                    "title": self.exported.get(pid, {}).get("title", ""),
                    "step": "convert_html_to_md",
                    "error_type": type(e).__name__,
                    "message": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                print(f"  ERROR: {e}")
            print()

        self.update_children()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.write_index_json()

        self._save_error_report()
        self._save_unsupported_macros_report()

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
