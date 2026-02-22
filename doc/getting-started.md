# 프로젝트 시작 가이드

처음 프로젝트를 받았을 때, 환경 설정부터 실행까지의 전체 과정을 안내한다.

---

## 목차

1. [사전 요구사항](#사전-요구사항)
2. [uv 설치](#uv-설치)
3. [프로젝트 동기화 (uv sync)](#프로젝트-동기화-uv-sync)
4. [환경변수 설정](#환경변수-설정)
5. [실행](#실행)
6. [Notion DB 필드 구조](#notion-db-필드-구조)
7. [Notion 블록 업로드 구조](#notion-블록-업로드-구조)
8. [프로젝트 구조](#프로젝트-구조)
9. [문제 해결](#문제-해결)

---

## 사전 요구사항

- **Python 3.10 이상** (uv가 자동 설치해주므로 직접 설치하지 않아도 됨)
- **uv** (Python 패키지 매니저)

---

## uv 설치

uv는 Python 프로젝트의 가상환경 생성, 의존성 설치, Python 버전 관리를 한 번에 처리하는 도구이다.

### Windows (PowerShell)

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### macOS / Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 설치 확인

```bash
uv --version
```

> uv에 대한 자세한 내용: <https://docs.astral.sh/uv/>

---

## 프로젝트 동기화 (uv sync)

프로젝트 루트 디렉토리에서 아래 명령어 하나만 실행하면 된다:

```bash
uv sync
```

이 명령어가 수행하는 작업:

1. `.python-version`에 지정된 Python 3.12를 자동 다운로드 (없는 경우)
2. `.venv/` 가상환경 생성
3. `pyproject.toml`에 선언된 의존성 설치:
   - `atlassian-python-api` -- Confluence/Jira REST API 클라이언트
   - `python-dotenv` -- `.env` 파일 로드
   - `confluence-markdown-exporter` -- **로컬 패키지 editable 설치** (`package/confluence-markdown-exporter/`)
   - `notion-markdown` -- **로컬 패키지 editable 설치** (`package/notion-markdown/`)
4. 각 패키지의 하위 의존성도 자동 설치됨 (markdownify, pydantic-settings, mistune 등 약 40개)
5. `uv.lock` 파일 생성/갱신 (의존성 버전 고정)

### editable 설치란?

`package/confluence-markdown-exporter/` 폴더의 소스 코드가 가상환경에 직접 링크된다.
소스 코드를 수정하면 별도 재설치 없이 즉시 반영된다. (`pip install -e .`와 동일)

이 설정은 `pyproject.toml`의 아래 부분에서 관리된다:

```toml
[tool.uv.sources]
confluence-markdown-exporter = { path = "package/confluence-markdown-exporter", editable = true }
notion-markdown = { path = "package/notion-markdown", editable = true }
```

---

## 환경변수 설정

프로젝트 루트의 `.env.example`을 복사하여 `.env`로 이름을 변경한 뒤 값을 채워 넣는다.

```bash
cp .env.example .env      # Linux/Mac
copy .env.example .env    # Windows
```

### 전체 환경변수

```env
# Step 1: Confluence 데이터 가져오기
CONFLUENCE_URL=https://your-site.atlassian.net
CONFLUENCE_PAT=your-personal-access-token
CONFLUENCE_PAGE_IDS=1427741158

# Step 2: Notion DB 업로드
NOTION_TOKEN=ntn_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_DATABASE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
NOTION_API_URL=https://api.notion.com
NOTION_API_PATH=v1
NOTION_API_VERSION=2022-06-28
```

| 변수 | 단계 | 필수 | 설명 |
|---|---|---|---|
| `CONFLUENCE_URL` | Step 1 | O | Confluence 인스턴스 URL (끝에 `/wiki` 붙이지 않음) |
| `CONFLUENCE_PAT` | Step 1 | O | Personal Access Token |
| `CONFLUENCE_PAGE_IDS` | Step 1 | O | 변환할 루트 페이지 ID (쉼표로 여러 개 지정 가능) |
| `NOTION_TOKEN` | Step 2 | O | Notion Integration 토큰 ([My Integrations](https://www.notion.so/my-integrations)에서 생성) |
| `NOTION_DATABASE_ID` | Step 2 | O | 업로드 대상 Notion DB ID (`utils/get_bot_databases.py`로 조회 가능) |
| `NOTION_API_URL` | Step 2 | O | Notion API 기본 URL (사내 프록시 경유 시 변경) |
| `NOTION_API_PATH` | Step 2 | O | API 경로 (기본 `v1`, 프록시 버전에 따라 변경) |
| `NOTION_API_VERSION` | Step 2 | O | Notion API 버전 (기본 `2022-06-28`) |

### PAT 발급 방법

- **Confluence Cloud**: [Atlassian API 토큰 관리](https://id.atlassian.com/manage-profile/security/api-tokens)에서 생성
- **Confluence Server/Data Center**: 프로필 > 개인 액세스 토큰 > 토큰 만들기

### Notion Integration 연결

Notion Integration을 생성한 후, 대상 데이터베이스 페이지에서 수동으로 연결해야 한다:

1. 대상 DB 페이지로 이동
2. 우측 상단 `···` 클릭
3. **연결 추가** > 생성한 Integration 선택

연결하지 않으면 API 호출 시 404 에러가 발생한다.

---

## 실행

실행은 두 단계로 나뉜다. 각 단계는 독립 실행된다.

`uv run`은 `.venv`의 Python을 자동으로 사용한다. 별도로 가상환경을 활성화(`activate`)할 필요가 없다.

### Step 1: Confluence → Markdown → Notion JSON 변환

```bash
uv run python run_convert.py
```

`.env`의 `CONFLUENCE_PAGE_IDS`에 지정된 페이지를 가져온다. 여러 페이지를 동시에 변환하려면:

```env
CONFLUENCE_PAGE_IDS=1427741158,1462521351,1462521353
```

`run_convert.py` 내부에서 변환 옵션을 조정할 수 있다:

```python
Pipeline(
    output_base="./output",             # 출력 디렉토리
    include_descendants=True,           # True: 하위 페이지 전부 포함
    download_all_attachments=False,     # True: 본문에 없는 첨부파일도 다운로드
    run_step1=True,                     # Confluence → Markdown 변환
    run_step2=True,                     # Markdown → Notion JSON 변환
).run()
```

`include_descendants=True`로 설정하면 `CONFLUENCE_PAGE_IDS`에 상위 페이지 하나만 넣어도 모든 하위 페이지를 자동으로 수집하여 함께 변환한다.

### Step 2: Notion DB 업로드

```bash
uv run python run_upload.py                              # 대화형 폴더 선택
uv run python run_upload.py AGUIDE_1427741158_20260222   # 폴더 직접 지정
```

실행 시 다음을 대화형으로 입력받는다:

1. **대상 폴더 선택** — `output/` 하위 폴더 목록에서 번호로 선택 (또는 인자로 직접 지정)
2. **Domain 입력** — 문서의 주제 영역 (예: `Jira`, `Confluence`, `CI/CD`, `Security`)

입력 후 요약 정보를 보여주고 업로드가 진행된다.

### 유틸리티: Bot 접근 가능 DB 조회

```bash
uv run python utils/get_bot_databases.py
```

Notion Integration(Bot)이 접근할 수 있는 데이터베이스 목록을 출력한다. `.env`에 `NOTION_DATABASE_ID`를 설정할 때 참고한다.

### 출력 구조

각 페이지가 페이지 ID 폴더 단위로 저장된다. Markdown, Notion 블록 JSON, 첨부파일, 메타 정보가 같은 폴더에 위치하여 Notion API 업로드 시 바로 사용할 수 있다.

```
output/
├── AGUIDE_1427741158_20260222/          ← Space_RootID_날짜 폴더
│   ├── index.json                       ← 전체 페이지 트리 구조
│   ├── 1427741158/
│   │   ├── confluence.md                ← Step 1: Markdown
│   │   ├── notion.json                  ← Step 2: Notion API 블록 JSON
│   │   ├── meta.json                    ← 페이지 메타 정보
│   │   ├── image-2025-3-4_14-45-49.png  ← 첨부파일
│   │   └── image-2025-3-4_14-46-59.png
│   ├── 1462521351/                      ← 하위 페이지
│   │   ├── confluence.md
│   │   ├── notion.json
│   │   ├── meta.json
│   │   └── ...
│   └── ...
```

**meta.json** -- 각 페이지의 정보를 담고 있어 Notion 업로드 시 활용한다:

```json
{
  "id": 1462521351,
  "title": "01. Jira 이슈 타입 생성/추가/삭제 요청",
  "space": "Confluence / Jira 가이드",
  "space_key": "AGUIDE",
  "updated": "2025-03-04T14:48:16.000+09:00",
  "source_url": "https://confluence.example.com/pages/viewpage.action?pageId=1462521351",
  "parent_id": 1427741158,
  "depth": 3,
  "children": [],
  "attachments": ["image-2025-3-4_14-45-49.png", "..."]
}
```

**notion.json** -- Notion API에 바로 전달할 수 있는 블록 JSON:

```json
{
  "page_id": 1462521351,
  "title": "01. Jira 이슈 타입 생성/추가/삭제 요청",
  "blocks": [ ... ],
  "local_images": ["image-2025-3-4_14-45-49.png", "..."]
}
```

**index.json** -- 전체 페이지의 트리 구조를 JSON으로 관리한다. 페이지 간 상하위 관계와 depth를 한눈에 파악할 수 있다.

---

## Notion DB 필드 구조

업로드 시 Notion DB에 자동으로 생성되는 필드와 커스텀 필드이다.

### 자동 관리 필드 (시스템)

| 필드 | 타입 | 설명 |
|---|---|---|
| `Name` | title | 페이지 제목 (Notion 기본 필드) |
| `Space` | rich_text | Confluence Space 이름 |
| `Updated` | date | Confluence 페이지 마지막 수정일 |
| `Parent Title` | rich_text | 상위 페이지 제목 |
| `Source URL` | url | Confluence 원본 페이지 URL (출처 추적) |
| `Status` | select | 문서 상태 (Active / Deprecated / Draft, 기본값: Active) |
| `Topics` | multi_select | 문서 주제 태그 (향후 온톨로지 구현 시 활용) |

### 커스텀 필드 (사용자 입력)

| 필드 | 타입 | 설명 |
|---|---|---|
| `Domain` | select | 문서의 주제 영역 (예: Jira, Confluence, CI/CD, Security, Infra) |

`Domain`은 `run_upload.py` 실행 시 대화형으로 입력받는다. Space Key 하나에 여러 도메인이 섞일 수 있으므로 시스템 자동 분류가 아닌 사용자가 직접 지정한다.

---

## Notion 블록 업로드 구조

### 블록이란?

Notion 페이지의 콘텐츠는 **블록(block)** 단위로 구성된다. 각 블록은 하나의 `type`을 가진 JSON 객체이다.

```json
{ "type": "heading_1", "heading_1": { "rich_text": [...] } }
{ "type": "paragraph", "paragraph": { "rich_text": [...] } }
{ "type": "table",     "table":     { "children": [...] } }
```

주요 블록 타입:

| 타입 | 설명 |
|---|---|
| `heading_1`, `heading_2`, `heading_3` | 제목 |
| `paragraph` | 일반 텍스트 단락 |
| `bulleted_list_item` | 비순서 목록 |
| `numbered_list_item` | 순서 목록 |
| `table` | 테이블 (내부에 `table_row` 포함) |
| `callout` | 알림/콜아웃 박스 |
| `code` | 코드 블록 |
| `image` | 이미지 |
| `divider` | 구분선 |

### 100개 단위 분할 전송

Notion API (`PATCH /blocks/{id}/children`)는 한 번의 요청에 **최상위 블록 최대 100개**까지만 허용한다. `upload.py`는 이 제한에 맞춰 블록 리스트를 100개씩 나눠서 순서대로 전송한다.

```
블록 250개인 페이지:
  1회차: blocks[0:100]   → 1~100번 블록
  2회차: blocks[100:200] → 101~200번 블록
  3회차: blocks[200:300] → 201~250번 블록 (50개)
```

- **순서 보장**: 각 요청의 블록이 페이지 끝에 이어 붙여지므로 원본 순서가 유지된다.
- **중복/누락 없음**: Python 슬라이싱으로 겹치는 구간 없이 정확히 분할된다.
- **블록 내부는 잘리지 않음**: 블록 사이에서만 나누므로 블록 하나의 JSON 내용이 중간에 잘리는 일이 없다.

### 중첩 블록 카운트

100개 제한은 **최상위 블록만** 카운트한다. `table` 블록 안의 `table_row`나 `toggle` 안의 하위 블록은 부모 블록의 JSON 안에 포함되어 있으므로 별도로 세지 않는다.

```
blocks = [
  { "type": "heading_1", ... },       ← 블록 1
  { "type": "callout", ... },         ← 블록 2
  { "type": "table", "table": {       ← 블록 3 (table_row 10개 포함)
      "children": [
        { "type": "table_row", ... },
        { "type": "table_row", ... },
        ...
      ]
  }},
  { "type": "divider" },              ← 블록 4
]
→ 최상위 블록 수: 4개
```

### 이미지 업로드

로컬 이미지 파일은 Notion File Upload API로 먼저 업로드한 뒤, 반환된 `file_upload_id`를 블록의 이미지 참조로 교체한다. 이 과정은 블록 전송 전에 자동으로 수행된다.

### Rate Limit 처리

Notion API가 429 (Too Many Requests) 응답을 반환하면 `Retry-After` 헤더를 참고하여 자동으로 대기 후 재시도한다. 요청 간 `REQUEST_INTERVAL` (0.35초) 간격을 두어 Rate Limit을 예방한다.

---

## 프로젝트 구조

```
confluencetoNotion/
├── .venv/                              # 가상환경 (uv sync 시 자동 생성)
├── package/
│   ├── confluence-markdown-exporter/   # Step 1 패키지 (editable 설치됨)
│   └── notion-markdown/               # Step 2 패키지 (editable 설치됨)
├── pipeline/                           # 변환 파이프라인 모듈
│   ├── __init__.py
│   ├── confluence_to_markdown.py       # Step 1: Confluence → Markdown
│   └── markdown_to_notion.py          # Step 2: Markdown → Notion 블록
├── upload/                             # Notion 업로드 모듈
│   ├── __init__.py
│   └── upload.py                       # NotionUploader 클래스
├── utils/                              # 유틸리티
│   ├── __init__.py
│   └── get_bot_databases.py           # Bot 접근 가능 DB 조회 (DatabaseFinder)
├── doc/                                # 문서
│   ├── getting-started.md              # 이 문서
│   ├── dependencies.md                 # 의존성 패키지 및 라이선스
│   ├── package-overview.md             # 패키지 기능 가이드
│   └── release/
│       └── CHANGELOG.md                # 릴리즈 기록
├── output/                             # 변환 결과 (실행 시 생성, git 제외)
├── run_convert.py                      # 진입점: Confluence → Markdown → Notion JSON (Pipeline 클래스)
├── run_upload.py                       # 진입점: Notion DB 업로드 (UploadRunner 클래스, 대화형)
├── pyproject.toml                      # 프로젝트 루트 설정 (의존성 + uv.sources)
├── .python-version                     # Python 3.12 지정
├── .env                                # 환경변수 (직접 생성 필요, git 제외)
├── .env.example                        # 환경변수 템플릿 (저장소에 포함)
├── .gitignore                          # git 제외 파일 설정
└── uv.lock                             # 의존성 lock 파일
```

### 핵심 파일 설명

| 파일 | 역할 |
|---|---|
| `run_convert.py` | Step 1 진입점. Pipeline 클래스 포함. `.env`에서 설정을 읽어 Confluence 데이터를 Markdown + Notion JSON으로 변환 |
| `run_upload.py` | Step 2 진입점. UploadRunner 클래스 포함. 대화형으로 폴더/Domain 선택 후 Notion DB에 업로드 |
| `pipeline/confluence_to_markdown.py` | Step 1: Confluence → Markdown + 첨부파일 + meta.json |
| `pipeline/markdown_to_notion.py` | Step 2: Markdown 전처리 → Notion 블록 JSON |
| `upload/upload.py` | NotionUploader 클래스. DB 스키마 관리 + 페이지 생성 + 블록 분할 전송 + 이미지 업로드 |
| `utils/get_bot_databases.py` | DatabaseFinder 클래스. Notion Integration이 접근 가능한 DB 목록 조회 |
| `.env` | Confluence/Notion 연결 정보 및 API 설정 (git에 포함하지 않음) |
| `.env.example` | `.env` 작성 참고용 템플릿 (git에 포함) |

---

## 문제 해결

### `uv` 명령어를 찾을 수 없음

uv 설치 후 터미널을 재시작한다. PATH에 추가되지 않았다면:

```powershell
# Windows - 설치 경로 확인
$env:USERPROFILE\.local\bin\uv --version
```

### `uv sync` 실패 -- Python 다운로드 오류

네트워크 환경(프록시, VPN)을 확인한다. uv는 Python을 자동 다운로드하므로 인터넷 연결이 필요하다.

### `.env` 환경변수 누락 에러

`run_convert.py` 또는 `run_upload.py` 실행 시 필수 환경변수가 누락되면 에러 메시지와 함께 종료된다. `.env` 파일이 프로젝트 루트에 있는지, 모든 필수 변수가 채워져 있는지 확인한다.

```
ERROR: .env에 다음 항목이 필요합니다: NOTION_TOKEN, NOTION_API_URL
```

### Notion API 에러

| 에러 코드 | 원인 | 해결 |
|---|---|---|
| 401 | `NOTION_TOKEN`이 유효하지 않음 | 토큰 재발급 |
| 403 | DB 접근 권한 없음 | Notion에서 Integration 연결 확인 |
| 404 | DB를 찾을 수 없음 | `NOTION_DATABASE_ID` 확인, Integration 연결 확인 |
| 400 | 잘못된 요청 (이미지 URL 오류 등) | 에러 메시지 상세 내용 확인 |
| 429 | Rate Limit 초과 | 자동 재시도됨, 대기 후 진행 |

### 페이지 접근 불가 (`SKIP: ... (접근 불가)`)

PAT에 해당 페이지의 읽기 권한이 있는지 확인한다. Space 제한이나 페이지 권한 설정을 점검한다.

### 패키지 수정 후 반영 안 됨

editable 설치이므로 `package/confluence-markdown-exporter/` 내 코드 수정은 즉시 반영된다.
반영이 안 되면 `uv sync`를 다시 실행한다.
