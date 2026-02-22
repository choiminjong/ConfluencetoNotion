"""Notion Bot이 접근 가능한 데이터베이스 목록을 조회한다.

사용법:
    uv run python utils/get_bot_databases.py
"""

import os
import sys
import time

import requests
from dotenv import load_dotenv

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


class DatabaseFinder:
    """Notion Integration에 연결된 데이터베이스를 조회한다."""

    ERROR_MESSAGES = {
        401: "NOTION_TOKEN이 유효하지 않습니다. 토큰을 확인하세요.",
        403: "접근 권한이 없습니다. Notion에서 Integration 연결을 확인하세요.",
        404: "리소스를 찾을 수 없습니다. ID를 확인하세요.",
    }

    def __init__(self):
        load_dotenv()

        self.token = os.getenv("NOTION_TOKEN", "")
        self.api_url = os.getenv("NOTION_API_URL", "")
        self.api_path = os.getenv("NOTION_API_PATH", "")
        self.api_version = os.getenv("NOTION_API_VERSION", "")

        if not self.token or not self.api_url or not self.api_path or not self.api_version:
            print("ERROR: .env에 NOTION_TOKEN, NOTION_API_URL, NOTION_API_PATH, NOTION_API_VERSION 설정 필요")
            sys.exit(1)

        self.base = f"{self.api_url.rstrip('/')}/{self.api_path.strip('/')}"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.api_version,
            "Content-Type": "application/json",
        }

    def api(self, method: str, url: str, **kwargs) -> requests.Response:
        """Rate limit 을 고려한 API 호출."""
        for attempt in range(5):
            resp = requests.request(method, url, headers=self.headers, **kwargs)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 2 ** attempt))
                print(f"  Rate limited, waiting {wait}s ...")
                time.sleep(wait)
                continue
            self._check_response(resp)
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

    def _extract_title(self, db_data: dict) -> str:
        """DB 응답에서 제목을 추출한다. search 결과에 없으면 직접 조회한다."""
        title_parts = db_data.get("title", [])
        title = "".join(t.get("plain_text", "") for t in title_parts)
        if title:
            return title

        db_id = db_data["id"]
        detail = self.api("GET", f"{self.base}/databases/{db_id}").json()
        title_parts = detail.get("title", [])
        return "".join(t.get("plain_text", "") for t in title_parts)

    def list_all(self) -> list[dict]:
        """Integration이 접근 가능한 모든 데이터베이스를 조회한다."""
        resp = self.api(
            "POST",
            f"{self.base}/search",
            json={"filter": {"property": "object", "value": "database"}},
        )
        results = resp.json().get("results", [])
        databases = []
        for db in results:
            title = self._extract_title(db)
            databases.append({"id": db["id"], "title": title, "url": db.get("url", "")})
        return databases

    def run(self):
        """DB 목록을 조회하여 출력한다."""
        databases = self.list_all()

        if not databases:
            print("접근 가능한 데이터베이스가 없습니다.")
            print("Notion Integration이 데이터베이스에 연결되어 있는지 확인해주세요.")
            return

        print("Bot이 접근 가능한 Notion 데이터베이스 목록:\n")
        for i, db in enumerate(databases, 1):
            print(f"  {i}. {db['title'] or '(제목 없음)'} (ID: {db['id']})")
            if db["url"]:
                print(f"     {db['url']}")
            print()

        print(".env에 NOTION_DATABASE_ID를 설정해주세요.")


if __name__ == "__main__":
    DatabaseFinder().run()
