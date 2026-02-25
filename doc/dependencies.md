# 의존성 패키지 및 라이선스

프로젝트에서 사용하는 모든 외부 패키지와 라이선스를 정리한다.

---

## 직접 의존 패키지

`pyproject.toml`의 `dependencies`에 선언된 패키지이다.

| 패키지 | 버전 | 라이선스 | 상업적 사용 | 용도 |
|---|---|---|---|---|
| `confluence-markdown-exporter` | 3.2.0 | MIT | O | Confluence 페이지 → Markdown 변환 |
| `notion-markdown` | (beta) | MIT | O | Markdown → Notion API 블록 JSON 변환 |
| `atlassian-python-api` | latest | Apache 2.0 | O | Confluence/Jira REST API 클라이언트 |
| `python-dotenv` | latest | BSD-3-Clause | O | `.env` 파일에서 환경변수 로드 |
| `requests` | latest | Apache 2.0 | O | Notion API HTTP 호출 |
| `neo4j` | latest | Apache 2.0 | O | Neo4j 드라이버 |
| `neo4j-graphrag` | latest | Apache 2.0 | O | Neo4j GraphRAG 프레임워크 |
| `anthropic[bedrock]` | latest | MIT | O | AWS Bedrock Claude LLM |
| `openai` | latest | MIT | O | Azure OpenAI 임베딩 |
| `fastapi` | latest | MIT | O | 웹 API 서버 |
| `uvicorn[standard]` | latest | BSD-3-Clause | O | ASGI 서버 |

### 프론트엔드 CDN 라이브러리

| 라이브러리 | 버전 | 라이선스 | 상업적 사용 | 용도 |
|---|---|---|---|---|
| `vis-network.js` | latest | Apache 2.0 / MIT | O | 2D 그래프 시각화 |
| `3d-force-graph` | 1.x | MIT | O | 3D 그래프 시각화 |
| `Chart.js` | 4.x | MIT | O | 분석 대시보드 차트 |
| `marked.js` | latest | MIT | O | Markdown 렌더링 |

### confluence-markdown-exporter

- **GitHub**: <https://github.com/Spenhouet/confluence-markdown-exporter>
- **라이선스**: MIT
- **설치 방식**: `package/confluence-markdown-exporter/` 로컬 editable 설치
- **역할**: Confluence 페이지를 Markdown으로 변환하는 핵심 패키지. `Page`, `Space`, `Attachment` 등의 클래스를 제공하며, HTML → Markdown 변환 엔진을 포함한다.
- **사용 위치**: `pipeline/confluence_to_markdown.py`에서 `Page.from_id()`, `page.markdown`, `page.attachments` 등을 사용

### notion-markdown

- **GitHub**: <https://github.com/surepub/notion-markdown>
- **라이선스**: MIT
- **설치 방식**: `package/notion-markdown/` 로컬 editable 설치
- **역할**: Markdown 텍스트를 Notion API가 요구하는 블록 JSON 구조로 변환한다. heading, paragraph, table, list, image, code 등의 블록 타입을 지원한다.
- **사용 위치**: `pipeline/markdown_to_notion.py`에서 Markdown → Notion 블록 변환 시 사용

### atlassian-python-api

- **GitHub**: <https://github.com/atlassian-api/atlassian-python-api>
- **라이선스**: Apache 2.0
- **역할**: Confluence REST API를 Python에서 호출하기 위한 공식 커뮤니티 클라이언트. 페이지 조회(`get_page_by_id`), Space 정보, 하위 페이지 탐색 등에 사용한다.
- **사용 위치**: `run_convert.py`에서 space_key 조회, `pipeline/confluence_to_markdown.py`에서 `ConfluenceClient` 인스턴스 생성

---

## 간접 의존 패키지 (하위 의존성)

직접 의존 패키지가 내부적으로 사용하는 패키지이다. `uv sync` 시 자동으로 설치된다.

### confluence-markdown-exporter의 하위 의존성

| 패키지 | 라이선스 | 용도 |
|---|---|---|
| `markdownify` | MIT | HTML → Markdown 변환 엔진 |
| `pydantic-settings` | MIT | 설정 파일 관리 (앱 데이터 스토어) |
| `pyyaml` | MIT | YAML 파싱 (front matter) |
| `questionary` | MIT | CLI 대화형 입력 |
| `tabulate` | MIT | 테이블 포맷 출력 |
| `tqdm` | MIT / MPL 2.0 | 진행률 표시바 |
| `typer` | MIT | CLI 프레임워크 |
| `jmespath` | MIT | JSON 쿼리 |
| `python-dateutil` | Apache 2.0 / BSD | 날짜 파싱 |
| `lxml` | BSD-3-Clause | XML/HTML 파서 |
| `beautifulsoup4` | MIT | HTML 파싱 (markdownify 의존) |

### notion-markdown의 하위 의존성

| 패키지 | 라이선스 | 용도 |
|---|---|---|
| `mistune` | BSD-3-Clause | Markdown 파서 엔진 |
| `typing_extensions` | PSF | 타입 힌트 호환성 |

---

## 라이선스 요약

| 라이선스 | 상업적 사용 | 수정 | 배포 | 조건 |
|---|---|---|---|---|
| **MIT** | O | O | O | 저작권 표시 유지 |
| **Apache 2.0** | O | O | O | 저작권 표시 + 변경사항 고지 + 특허 허가 |
| **BSD-3-Clause** | O | O | O | 저작권 표시 유지 + 이름 사용 제한 |
| **PSF** | O | O | O | Python Software Foundation License |

**모든 의존 패키지가 상업적 사용을 허용하는 오픈소스 라이선스이다.**

### 주의사항

- `package/` 폴더에 포함된 로컬 패키지(`confluence-markdown-exporter`, `notion-markdown`)의 `LICENSE` 파일은 삭제하지 않는다.
- 프로젝트를 배포할 때 해당 패키지의 저작권 표시(`Copyright`)를 유지해야 한다.
- Apache 2.0 라이선스 패키지(`atlassian-python-api`, `requests`)를 수정하여 배포할 경우, 변경사항을 고지해야 한다.
