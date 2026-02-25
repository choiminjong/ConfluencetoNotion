"""Notion API 클라이언트.

Notion DB에서 페이지 목록을 조회하고, 각 페이지의 블록 콘텐츠를 읽어온다.
"""

from __future__ import annotations

import time

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class NotionClient:
    """Notion API를 통해 DB 페이지와 블록을 조회한다."""

    API_BASE = "https://api.notion.com/v1"
    REQUEST_INTERVAL = 0.2

    def __init__(self, token: str):
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

    def _get(self, url: str, **kwargs) -> dict:
        """GET 요청을 보내고 JSON 응답을 반환한다."""
        time.sleep(self.REQUEST_INTERVAL)
        resp = requests.get(url, headers=self.headers, verify=False, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def _post(self, url: str, json_body: dict | None = None) -> dict:
        """POST 요청을 보내고 JSON 응답을 반환한다."""
        time.sleep(self.REQUEST_INTERVAL)
        resp = requests.post(
            url, headers=self.headers, json=json_body or {}, verify=False
        )
        resp.raise_for_status()
        return resp.json()

    def query_database(self, database_id: str) -> list[dict]:
        """DB의 모든 페이지를 페이지네이션으로 조회한다."""
        url = f"{self.API_BASE}/databases/{database_id}/query"
        pages: list[dict] = []
        body: dict = {"page_size": 100}

        while True:
            data = self._post(url, body)
            pages.extend(data.get("results", []))

            if not data.get("has_more"):
                break
            body["start_cursor"] = data["next_cursor"]

        return pages

    def get_block_children(self, block_id: str) -> list[dict]:
        """블록의 children을 재귀적으로 모두 가져온다."""
        url = f"{self.API_BASE}/blocks/{block_id}/children"
        blocks: list[dict] = []
        params: dict = {"page_size": 100}

        while True:
            data = self._get(url, params=params)
            results = data.get("results", [])

            for block in results:
                if block.get("has_children"):
                    child_blocks = self.get_block_children(block["id"])
                    block_type = block.get("type", "")
                    if block_type in block:
                        block[block_type]["children"] = child_blocks
                blocks.append(block)

            if not data.get("has_more"):
                break
            params["start_cursor"] = data["next_cursor"]

        return blocks

    def extract_page_properties(self, page: dict) -> dict:
        """페이지 객체에서 DB 속성을 추출한다."""
        props = page.get("properties", {})
        result = {"page_id": page["id"]}

        for name, prop in props.items():
            prop_type = prop.get("type", "")

            if prop_type == "title":
                texts = prop.get("title", [])
                result["title"] = "".join(t.get("plain_text", "") for t in texts)

            elif prop_type == "rich_text":
                texts = prop.get("rich_text", [])
                result[name] = "".join(t.get("plain_text", "") for t in texts)

            elif prop_type == "select":
                sel = prop.get("select")
                result[name] = sel.get("name", "") if sel else ""

            elif prop_type == "multi_select":
                options = prop.get("multi_select", [])
                result[name] = ", ".join(o.get("name", "") for o in options)

            elif prop_type == "url":
                result[name] = prop.get("url", "") or ""

            elif prop_type == "date":
                date_obj = prop.get("date")
                result[name] = date_obj.get("start", "") if date_obj else ""

        return result
