"""Notion DB에 변환된 페이지를 업로드한다.

사용법:
    uv run python run_upload.py
"""

import copy
import json
import mimetypes
import sys
import time
from pathlib import Path

import requests

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


class NotionUploader:
    """output 폴더의 notion.json + 이미지를 Notion DB에 업로드한다."""

    MAX_BLOCKS_PER_REQUEST = 100
    REQUEST_INTERVAL = 0.35
    REQUIRED_PROPERTIES = {
        "Space": {"rich_text": {}},
        "Updated": {"date": {}},
        "Parent Title": {"rich_text": {}},
        "Source URL": {"url": {}},
        "Status": {"select": {"options": [{"name": "Active"}, {"name": "Deprecated"}, {"name": "Draft"}]}},
    }
    CUSTOM_PROPERTIES: dict[str, str] = {
        "Domain": "Jira",
    }

    def __init__(
        self,
        token: str,
        database_id: str,
        api_url: str,
        api_path: str,
        api_version: str,
    ):
        self.token = token
        self.database_id = database_id
        self.BASE = f"{api_url.rstrip('/')}/{api_path.strip('/')}"
        self.target_dir = Path(".")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": api_version,
            "Content-Type": "application/json",
        }
        self.title_property = "Name"
        self.db_properties: dict = {}

    def run(self):
        """전체 업로드 흐름을 위에서 아래로 실행한다."""
        if not self.token or not self.database_id:
            print("ERROR: .env에 NOTION_TOKEN, NOTION_DATABASE_ID 설정 필요")
            return
        if not self.target_dir.exists():
            print(f"ERROR: target_dir 경로가 없습니다: {self.target_dir}")
            return

        self.load_db_schema()
        self.ensure_properties()

        index_path = self.target_dir / "index.json"
        if not index_path.exists():
            print(f"ERROR: {index_path} 가 없습니다.")
            return

        index = json.loads(index_path.read_text(encoding="utf-8"))
        tree = index.get("tree", [])
        total = index.get("total_pages", 0)

        print(f"Notion DB 업로드 시작: {total}개 페이지")
        print(f"Database: {self.database_id}")
        print(f"Target: {self.target_dir}\n")

        uploaded = 0
        queue: list[tuple[dict, str]] = [(node, "") for node in tree]

        while queue:
            node, parent_title = queue.pop(0)
            page_id = node["id"]
            title = node.get("title", "")
            page_dir = self.target_dir / str(page_id)

            print(f"[Page {page_id}]")
            try:
                result = self.upload_page(page_dir, parent_title)
                if result:
                    uploaded += 1
            except Exception as e:
                print(f"  ERROR: {e}")
            print()

            for child in node.get("children", []):
                queue.append((child, title))

        print(f"Done. {uploaded}/{total} pages uploaded to Notion DB.")

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    ERROR_MESSAGES = {
        401: "NOTION_TOKEN이 유효하지 않습니다. 토큰을 확인하세요.",
        403: "해당 DB에 접근 권한이 없습니다. Notion에서 Integration 연결을 확인하세요.",
        404: "DB를 찾을 수 없습니다. NOTION_DATABASE_ID를 확인하거나, Notion에서 Integration(봇)을 연결하세요.",
    }

    def api(self, method: str, url: str, **kwargs) -> requests.Response:
        """Rate limit 을 고려한 API 호출. 429 응답 시 자동 재시도한다."""
        for attempt in range(5):
            resp = requests.request(method, url, **kwargs)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 2 ** attempt))
                print(f"  Rate limited, waiting {wait}s ...")
                time.sleep(wait)
                continue
            self._check_response(resp)
            time.sleep(self.REQUEST_INTERVAL)
            return resp
        self._check_response(resp)
        return resp

    def _check_response(self, resp: requests.Response) -> None:
        """HTTP 응답을 확인하고, 에러 시 안내 메시지를 출력 후 종료한다."""
        if resp.ok:
            return

        code = resp.status_code
        msg = self.ERROR_MESSAGES.get(code)

        if msg:
            print(f"\nERROR [{code}]: {msg}")
        elif code == 400:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            print(f"\nERROR [400 Bad Request]: {body.get('message', resp.text)}")
        else:
            print(f"\nERROR [{code}]: {resp.text}")

        print(f"  URL: {resp.request.method} {resp.url}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # DB Schema
    # ------------------------------------------------------------------

    def load_db_schema(self):
        """DB 스키마를 조회하여 title 속성명과 전체 속성 목록을 저장한다."""
        resp = self.api(
            "GET",
            f"{self.BASE}/databases/{self.database_id}",
            headers=self.headers,
        )
        self.db_properties = resp.json().get("properties", {})
        for name, config in self.db_properties.items():
            if config.get("type") == "title":
                self.title_property = name
                break

    def ensure_properties(self):
        """DB에 필수 속성·커스텀 속성이 없으면 자동으로 추가한다."""
        existing = set(self.db_properties.keys())
        missing: dict[str, dict] = {
            name: schema
            for name, schema in self.REQUIRED_PROPERTIES.items()
            if name not in existing
        }
        for name in self.CUSTOM_PROPERTIES:
            if name not in existing:
                missing[name] = {"select": {}}

        if "Topics" not in existing:
            missing["Topics"] = {"multi_select": {}}

        if not missing:
            return

        print(f"  DB 속성 추가: {', '.join(missing.keys())}")
        self.api(
            "PATCH",
            f"{self.BASE}/databases/{self.database_id}",
            headers=self.headers,
            json={"properties": missing},
        )

    # ------------------------------------------------------------------
    # File Upload
    # ------------------------------------------------------------------

    def upload_file(self, file_path: Path) -> str:
        """로컬 파일을 Notion에 업로드하고 file_upload_id 를 반환한다."""
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"

        create_resp = self.api(
            "POST",
            f"{self.BASE}/file_uploads",
            headers=self.headers,
            json={"filename": file_path.name, "content_type": content_type},
        )
        upload_id = create_resp.json()["id"]

        upload_headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.headers["Notion-Version"],
        }
        with open(file_path, "rb") as f:
            self.api(
                "POST",
                f"{self.BASE}/file_uploads/{upload_id}/send",
                headers=upload_headers,
                files={"file": (file_path.name, f, content_type)},
            )

        return upload_id

    # ------------------------------------------------------------------
    # Block Transform
    # ------------------------------------------------------------------

    def transform_blocks(self, blocks: list[dict], image_map: dict[str, str]) -> list[dict]:
        """블록 내 로컬 이미지 URL 을 file_upload 참조로 교체한다."""
        transformed = copy.deepcopy(blocks)
        stack = list(transformed)

        while stack:
            block = stack.pop()
            block_type = block.get("type", "")

            if block_type == "image":
                image_data = block.get("image", {})
                if image_data.get("type") == "external":
                    url = image_data.get("external", {}).get("url", "")
                    if url and not url.startswith("http") and url in image_map:
                        caption = image_data.get("caption")
                        block["image"] = {
                            "type": "file_upload",
                            "file_upload": {"id": image_map[url]},
                        }
                        if caption:
                            block["image"]["caption"] = caption

            children = block.get(block_type, {}).get("children", [])
            if children:
                stack.extend(children)

        return transformed

    # ------------------------------------------------------------------
    # Page / Block Creation
    # ------------------------------------------------------------------

    def create_page(self, title: str, meta: dict, parent_title: str = "") -> str:
        """DB에 페이지를 생성하고 page_id 를 반환한다."""
        properties: dict = {
            self.title_property: {
                "title": [{"text": {"content": title}}],
            },
        }

        space = meta.get("space", "")
        if space:
            properties["Space"] = {
                "rich_text": [{"text": {"content": space}}],
            }

        updated = meta.get("updated", "")
        if updated:
            properties["Updated"] = {"date": {"start": updated[:10]}}

        if parent_title:
            properties["Parent Title"] = {
                "rich_text": [{"text": {"content": parent_title}}],
            }

        source_url = meta.get("source_url", "")
        if source_url:
            properties["Source URL"] = {"url": source_url}

        properties["Status"] = {"select": {"name": "Active"}}

        for prop_name, prop_value in self.CUSTOM_PROPERTIES.items():
            if prop_value:
                properties[prop_name] = {"select": {"name": prop_value}}

        resp = self.api(
            "POST",
            f"{self.BASE}/pages",
            headers=self.headers,
            json={
                "parent": {"database_id": self.database_id},
                "properties": properties,
            },
        )
        return resp.json()["id"]

    def append_blocks(self, parent_id: str, blocks: list[dict]) -> None:
        """블록을 100개씩 분할하여 추가한다."""
        for i in range(0, len(blocks), self.MAX_BLOCKS_PER_REQUEST):
            chunk = blocks[i : i + self.MAX_BLOCKS_PER_REQUEST]
            self.api(
                "PATCH",
                f"{self.BASE}/blocks/{parent_id}/children",
                headers=self.headers,
                json={"children": chunk},
            )

    # ------------------------------------------------------------------
    # Page Upload
    # ------------------------------------------------------------------

    def upload_page(self, page_dir: Path, parent_title: str = "") -> str | None:
        """단일 페이지 폴더를 Notion DB에 업로드한다."""
        notion_path = page_dir / "notion.json"
        meta_path = page_dir / "meta.json"

        if not notion_path.exists() or not meta_path.exists():
            print(f"  SKIP: {page_dir.name} (notion.json 또는 meta.json 없음)")
            return None

        notion_data = json.loads(notion_path.read_text(encoding="utf-8"))
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

        title = notion_data.get("title", meta.get("title", "Untitled"))
        blocks = notion_data.get("blocks", [])
        local_images = notion_data.get("local_images", [])

        image_map: dict[str, str] = {}
        for filename in local_images:
            file_path = page_dir / filename
            if file_path.exists():
                print(f"  Uploading image: {filename}")
                try:
                    image_map[filename] = self.upload_file(file_path)
                except Exception as e:
                    print(f"  WARN: 이미지 업로드 실패 '{filename}': {e}")
            else:
                print(f"  WARN: 이미지 파일 없음 '{filename}'")

        transformed = self.transform_blocks(blocks, image_map)

        print(f"  Creating page: {title}")
        page_id = self.create_page(title, meta, parent_title)

        if transformed:
            print(f"  Appending {len(transformed)} blocks ...")
            self.append_blocks(page_id, transformed)

        print(f"  Done: https://notion.so/{page_id.replace('-', '')}")
        return page_id


if __name__ == "__main__":
    NotionUploader().run()
