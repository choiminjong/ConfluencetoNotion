# 프로젝트 시작 가이드

처음 프로젝트를 받았을 때, 환경 설정부터 실행까지의 전체 과정을 안내한다.

---

## 목차

1. [Quick Start](#quick-start)
2. [사용 절차 (Step-by-Step)](#사용-절차-step-by-step)
3. [Neo4j Desktop 설치](#neo4j-desktop-설치)
4. [VS Code 설정](#vs-code-설정)
5. [환경변수 설정](#환경변수-설정)
6. [Phase 1: Confluence → Notion 마이그레이션](#phase-1-confluence--notion-마이그레이션)
7. [Phase 2: Notion → Neo4j GraphRAG](#phase-2-notion--neo4j-graphrag)
8. [Notion DB 필드 구조](#notion-db-필드-구조)
9. [Notion 블록 업로드 구조](#notion-블록-업로드-구조)
10. [프로젝트 구조](#프로젝트-구조)
11. [가상환경이란?](#가상환경이란)
12. [수동 설치 (선택)](#수동-설치-선택)
13. [Python 기초 (C# 개발자용)](#python-기초-c-개발자용)
14. [문제 해결](#문제-해결)

---

## Quick Start

프로젝트를 클론하고 `init.ps1`을 실행하면 **uv 설치, Python 다운로드, 가상환경 생성, 패키지 설치**가 한 번에 완료된다.

```powershell
git clone https://github.com/choiminjong/ConfluencetoNotion.git
cd ConfluencetoNotion
.\init.ps1
```

`init.ps1`이 수행하는 작업:

1. **uv 설치** -- 없으면 자동으로 다운로드하여 설치
2. **`.env` 복사** -- `.env.example`을 `.env`로 복사 (이미 있으면 건너뜀)
3. **`uv sync`** -- `.python-version`에 지정된 Python을 자동 다운로드하고, `.venv/` 가상환경을 생성하고, `pyproject.toml`에 선언된 모든 패키지를 설치

> Python을 직접 설치할 필요가 없다. uv가 `.python-version` 파일을 읽고 자동으로 다운로드한다.

스크립트 완료 후 화면에 다음 단계가 안내된다:

```
=====================================
  설치 완료!
=====================================

다음 단계:
  1. .env 파일을 열어 환경변수를 설정하세요
  2. VS Code: Ctrl+Shift+P -> 'Python: Select Interpreter'
     -> .venv\Scripts\python.exe 선택
  3. python -m pipeline.run 으로 실행
```

---

## 사용 절차 (Step-by-Step)

프로젝트의 전체 파이프라인을 요약한다. Phase 1만 사용하거나, Phase 2까지 확장할 수 있다.

> 모든 명령어는 `uv run python -m ...` 형식을 권장한다. 가상환경이 이미 활성화된 상태라면 `python -m ...`으로도 실행할 수 있다.

### 전체 워크플로우

```mermaid
flowchart LR
    subgraph phase1 [Phase 1: Confluence → Notion]
        STEP1["STEP 1\npipeline.run\nConfluence → MD → JSON"] --> STEP2["STEP 2\nupload.run\nNotion DB 업로드"]
    end
    subgraph phase2 [Phase 2: GraphRAG]
        STEP3["STEP 3\nstep1_scraper\nNotion → JSON"] --> STEP4["STEP 4\nstep2_graph\nNeo4j 그래프"]
        STEP4 --> STEP5["STEP 5\nstep3_embedding\n임베딩 생성"]
        STEP5 --> STEP6["STEP 6\nstep4_rag\nRAG 검증"]
        STEP6 --> STEP7["STEP 7\nstep5_web\n웹 UI"]
    end
    STEP2 --> STEP3
```

### Phase 1: Confluence → Notion 마이그레이션

Confluence 문서를 Notion DB로 옮기는 과정이다. **STEP 1-2만 실행하면 된다.**

| 순서 | 명령어 | 하는 일 | 전제 조건 | 결과물 |
|---|---|---|---|---|
| **STEP 1** | `uv run python -m pipeline.run` | Confluence 페이지를 Markdown으로 변환하고, Notion API 블록 JSON을 생성한다 | `.env`에 `CONFLUENCE_*` 환경변수 설정 | `output/{SPACE}_{ID}_{날짜}/` 폴더 (Markdown, JSON, 첨부파일) |
| **STEP 2** | `uv run python -m upload.run` | 변환된 JSON과 미디어를 Notion DB에 업로드한다 | STEP 1 완료 + `.env`에 `NOTION_*` 환경변수 설정 | Notion DB에 페이지 생성 완료 |

```bash
# 1. Confluence → Markdown → Notion JSON
uv run python -m pipeline.run       # 또는: python -m pipeline.run

# 2. Notion DB에 업로드 (대화형으로 폴더/Domain 선택)
uv run python -m upload.run         # 또는: python -m upload.run
```

> Phase 1만 필요하면 여기서 끝이다. Neo4j, AWS, Azure 설정은 불필요하다.

### Phase 2: Notion → Neo4j GraphRAG

Phase 1에서 업로드한 Notion DB를 기반으로 지식 그래프를 구축하고 RAG 검색을 제공한다. **STEP 3-7을 순서대로 실행한다.**

| 순서 | 명령어 | 하는 일 | 전제 조건 | 결과물 |
|---|---|---|---|---|
| **STEP 3** | `uv run python -m graphrag.step1_scraper.run` | Notion DB 전체 페이지를 조회하여 속성과 본문을 JSON으로 추출한다 | Phase 1 완료 (Notion DB에 데이터 존재) | `output/graphrag/pages_*.json` |
| **STEP 4** | `uv run python -m graphrag.step2_graph.run` | JSON에서 Page/Content 노드와 관계를 생성하여 Neo4j 그래프를 구축한다 | STEP 3 완료 + Neo4j 실행 중 | Neo4j에 그래프 데이터 생성 |
| **STEP 5** | `uv run python -m graphrag.step3_embedding.run` | Content 노드에 Azure OpenAI 임베딩을 생성하고 벡터 인덱스를 구축한다 | STEP 4 완료 + Azure OpenAI 설정 | Neo4j Content 노드에 임베딩 추가 |
| **STEP 6** | `uv run python -m graphrag.step4_rag.run` | GraphRAG 파이프라인(VectorCypher + Text2Cypher)을 구성하고 테스트 질의로 검증한다 | STEP 5 완료 + AWS Bedrock 설정 | 파이프라인 동작 확인 |
| **STEP 7** | `uv run python -m graphrag.step5_web.run` | FastAPI 웹 서버를 시작한다. 그래프 시각화와 RAG 질의 UI를 제공한다 | STEP 4 이상 완료 | http://localhost:8000 |

```bash
# 3. Notion DB → JSON 추출
uv run python -m graphrag.step1_scraper.run

# 4. JSON → Neo4j 그래프 구축
uv run python -m graphrag.step2_graph.run

# 5. 임베딩 생성
uv run python -m graphrag.step3_embedding.run

# 6. RAG 파이프라인 검증
uv run python -m graphrag.step4_rag.run

# 7. 웹 UI 실행
uv run python -m graphrag.step5_web.run
```

> STEP 7 웹 UI는 **그래프 시각화만** 사용할 경우 AWS/Azure 자격증명 없이 STEP 4까지만 완료해도 실행할 수 있다. RAG 질의 기능을 사용하려면 STEP 5-6까지 완료해야 한다.

### 사전 점검 (선택)

Phase 2 실행 전에 Neo4j, Azure OpenAI, AWS Bedrock 연결을 미리 확인할 수 있다:

```bash
uv run python -m graphrag.step3_embedding.precheck
```

각 단계의 상세 옵션과 설정은 아래 [Phase 1](#phase-1-confluence--notion-마이그레이션), [Phase 2](#phase-2-notion--neo4j-graphrag) 섹션을 참고한다.

---

## Neo4j Desktop 설치

Phase 2 (GraphRAG)를 사용하려면 Neo4j가 필요하다.

### 다운로드 및 설치

1. [Neo4j Desktop 다운로드](https://neo4j.com/download/) 페이지에서 Windows 버전을 다운로드
2. 설치 프로그램을 실행하고 기본 설정으로 설치

### 데이터베이스 생성

1. Neo4j Desktop을 실행
2. **New** > **Create project** 클릭
3. 프로젝트 내에서 **Add** > **Local DBMS** 클릭
4. 이름과 **비밀번호**를 설정 (이 비밀번호를 `.env`의 `NEO4J_PASSWORD`에 입력)
5. 버전은 기본값으로 두고 **Create** 클릭

### 실행 및 확인

1. 생성된 DBMS의 **Start** 버튼 클릭
2. 상태가 "Running"으로 바뀌면 정상
3. **Open** > **Neo4j Browser** 클릭하여 http://localhost:7474 접속 확인
4. `.env`에 아래 값이 맞는지 확인:

```env
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=위에서-설정한-비밀번호
NEO4J_DB=neo4j
```

---

## VS Code 설정

### Python 확장 설치

1. VS Code에서 Extensions(확장) 패널 열기 (`Ctrl+Shift+X`)
2. **Python** 검색 → Microsoft의 **Python** 확장 설치
3. 추천 확장: **Pylance** (자동 완성), **Python Debugger** (디버깅)

### 인터프리터 선택

`init.ps1` 실행 후 `.venv/` 폴더가 생성되면, VS Code에 이 가상환경을 알려줘야 한다:

1. `Ctrl+Shift+P` → **"Python: Select Interpreter"** 입력
2. 목록에서 **`.venv\Scripts\python.exe`** 선택
3. 하단 상태바에 `Python 3.12.x ('.venv')` 가 표시되면 정상
4. 터미널을 새로 열면 프롬프트 앞에 `(.venv)`가 표시된다

> 인터프리터를 선택하지 않으면 `import` 에러가 발생할 수 있다.

---

## 환경변수 설정

`init.ps1`을 실행했다면 `.env` 파일이 자동으로 생성되어 있다. `.env`를 열어 값을 채워 넣는다.

### 전체 환경변수

```env
# Phase 1: Confluence → Notion 마이그레이션
CONFLUENCE_URL=https://your-site.atlassian.net
CONFLUENCE_PAT=your-personal-access-token
CONFLUENCE_PAGE_IDS=1427741158

NOTION_TOKEN=ntn_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_DATABASE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
NOTION_API_URL=https://api.notion.com
NOTION_API_PATH=v1
NOTION_API_VERSION=2022-06-28

# Phase 2: Notion → Neo4j GraphRAG
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=
NEO4J_DB=neo4j

AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=us-east-1
BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0

AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-ada-002
AZURE_OPENAI_API_VERSION=2024-02-01
```

| 변수 | Phase | 필수 | 설명 |
|---|---|---|---|
| `CONFLUENCE_URL` | 1 | O | Confluence 인스턴스 URL (끝에 `/wiki` 붙이지 않음) |
| `CONFLUENCE_PAT` | 1 | O | Personal Access Token |
| `CONFLUENCE_PAGE_IDS` | 1 | O | 변환할 루트 페이지 ID (쉼표로 여러 개 지정 가능) |
| `NOTION_TOKEN` | 1, 2 | O | Notion Integration 토큰 ([My Integrations](https://www.notion.so/my-integrations)에서 생성) |
| `NOTION_DATABASE_ID` | 1, 2 | O | 업로드/조회 대상 Notion DB ID (`utils/get_bot_databases.py`로 조회 가능) |
| `NOTION_API_URL` | 1 | O | Notion API 기본 URL (사내 프록시 경유 시 변경) |
| `NOTION_API_PATH` | 1 | O | API 경로 (기본 `v1`, 프록시 버전에 따라 변경) |
| `NOTION_API_VERSION` | 1 | O | Notion API 버전 (기본 `2022-06-28`) |
| `NEO4J_URI` | 2 | O | Neo4j 접속 URI |
| `NEO4J_USERNAME` | 2 | O | Neo4j 사용자명 |
| `NEO4J_PASSWORD` | 2 | O | Neo4j 비밀번호 |
| `NEO4J_DB` | 2 | - | Neo4j 데이터베이스명 (기본: `neo4j`) |
| `AWS_ACCESS_KEY_ID` | 2 | O | AWS Bedrock 인증 키 |
| `AWS_SECRET_ACCESS_KEY` | 2 | O | AWS Bedrock 시크릿 |
| `AWS_DEFAULT_REGION` | 2 | - | AWS 리전 (기본: `us-east-1`) |
| `BEDROCK_MODEL_ID` | 2 | - | Bedrock LLM 모델 ID |
| `AZURE_OPENAI_ENDPOINT` | 2 | O | Azure OpenAI 엔드포인트 |
| `AZURE_OPENAI_API_KEY` | 2 | O | Azure OpenAI API 키 |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | 2 | - | 임베딩 모델 배포명 (기본: `text-embedding-ada-002`) |

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

## Phase 1: Confluence → Notion 마이그레이션

Confluence 페이지를 Notion으로 마이그레이션하는 파이프라인이다. 모든 실행은 프로젝트 루트에서 `python -m` 패턴을 사용한다.

### STEP 1: Confluence → Markdown → Notion JSON 변환

```bash
python -m pipeline.run
```

`.env`의 `CONFLUENCE_PAGE_IDS`에 지정된 페이지를 가져온다. 여러 페이지를 동시에 변환하려면:

```env
CONFLUENCE_PAGE_IDS=1427741158,1462521351,1462521353
```

`pipeline/run.py` 내부에서 변환 옵션을 조정할 수 있다:

```python
Pipeline(
    include_descendants=True,           # True: 하위 페이지 전부 포함
    download_all_attachments=False,     # True: 본문에 없는 첨부파일도 다운로드
    run_step1=True,                     # Confluence → Markdown 변환
    run_step2=True,                     # Markdown → Notion JSON 변환
).run()
```

`include_descendants=True`로 설정하면 `CONFLUENCE_PAGE_IDS`에 상위 페이지 하나만 넣어도 모든 하위 페이지를 자동으로 수집하여 함께 변환한다.

### STEP 2: Notion DB 업로드

```bash
python -m upload.run                              # 대화형 폴더 선택
python -m upload.run AGUIDE_1427741158_20260222   # 폴더 직접 지정
```

실행 시 다음을 대화형으로 입력받는다:

1. **대상 폴더 선택** — `output/` 하위 폴더 목록에서 번호로 선택 (또는 인자로 직접 지정)
2. **Domain 입력** — 문서의 주제 영역 (예: `Jira`, `Confluence`, `CI/CD`, `Security`)
3. **Topics 포함 여부** — Confluence 라벨을 Notion Topics에 포함할지 선택 (`y`/`n`, 기본값: `y`)

입력 후 요약 정보를 보여주고 업로드가 진행된다.

### 유틸리티: Bot 접근 가능 DB 조회

```bash
python utils/get_bot_databases.py
```

Notion Integration(Bot)이 접근할 수 있는 데이터베이스 목록을 출력한다. `.env`에 `NOTION_DATABASE_ID`를 설정할 때 참고한다.

---

## Phase 2: Notion → Neo4j GraphRAG

Phase 1에서 마이그레이션한 Notion DB 데이터를 활용하여 Neo4j 그래프를 구축하고, GraphRAG 기반 검색과 웹 시각화를 제공한다.

### 사전 준비

1. **Neo4j Desktop** -- [Neo4j Desktop 설치](#neo4j-desktop-설치) 섹션을 참고하여 로컬 DB를 생성하고 Start한다.
2. **AWS Bedrock** -- Claude 모델 접근을 위한 AWS 자격증명을 `.env`에 설정한다.
3. **Azure OpenAI** -- 텍스트 임베딩을 위한 Azure OpenAI 엔드포인트를 `.env`에 설정한다.

### STEP 3: Notion DB → JSON

```bash
python -m graphrag.step1_scraper.run
```

Notion DB의 모든 페이지를 조회하여 속성(Title, Space, Domain, Topics 등)과 본문 텍스트를 추출하고 `output/graphrag/pages_*.json`으로 저장한다. 각 페이지는 `ContentParser`에 의해 heading 기반 섹션 트리로 구조화되며, DB 스키마 정보도 함께 포함된다.

### STEP 4: JSON → Neo4j 그래프

```bash
python -m graphrag.step2_graph.run
```

`GraphRunner`가 JSON 파일을 로딩하고 `GraphBuilder`에게 그래프 구축을 위임한다. `GraphBuilder`는 내부적으로 `TextChunker`를 사용하여 섹션 기반 하이브리드 청킹을 수행하고, Page, Content 노드를 생성하며, DB 스키마의 select/multi_select 필드를 자동으로 노드와 관계로 매핑한다. NEXT_CHUNK 관계로 청크 순서를 보존한다.

### STEP 5: 임베딩 생성

```bash
python -m graphrag.step3_embedding.run
```

Content 노드에 Azure OpenAI 임베딩을 배치로 생성하고, 벡터 인덱스를 구축한다. 증분 임베딩을 지원하여 이미 임베딩된 노드는 건너뛴다.

### STEP 6: GraphRAG 파이프라인 검증

```bash
python -m graphrag.step4_rag.run
```

VectorCypherRetriever + Text2CypherRetriever를 ToolsRetriever로 통합한 GraphRAG 파이프라인을 구성하고, 테스트 질의로 동작을 검증한다.

### STEP 7: 웹 시각화 서버

```bash
python -m graphrag.step5_web.run
```

FastAPI 기반 웹 UI를 http://localhost:8000 에서 제공한다. vis-network.js(2D)와 3d-force-graph(3D) 전환, 노드 필터/검색, 분석 대시보드, 노드 상세 정보 패널, 허브 노드 자동 dim, 그래프 커스터마이징 등을 지원한다. AWS/Azure 자격증명 없이도 그래프 시각화가 동작한다.

### GraphRAG 출력

STEP 3 실행 시 `output/graphrag/pages_YYYYMMDD_HHMMSS.json` 파일이 생성된다. 각 페이지는 heading 기반 섹션 구조로 파싱되며, DB 스키마 정보도 포함된다.

### Phase 1 출력 구조

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
  "local_media": ["image-2025-3-4_14-45-49.png", "..."]
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

Notion API가 429 (Too Many Requests) 응답을 반환하면 `Retry-After` 헤더를 참고하여 자동으로 대기 후 재시도한다. 요청 간 `REQUEST_INTERVAL` (0.20초) 간격을 두어 Rate Limit을 예방한다.

---

## 프로젝트 구조

```
ConfluencetoNotion/
├── pipeline/                           # Phase 1 STEP 1: Confluence → Markdown → Notion JSON
│   ├── __init__.py
│   ├── run.py                          # 진입점: python -m pipeline.run
│   ├── confluence_to_markdown.py       # Confluence → Markdown + 첨부파일
│   ├── converter_overrides.py          # 패키지 Converter 메서드 오버라이딩
│   ├── md_preprocessor.py             # Markdown 전처리 (정규식 기반 정제)
│   ├── notion_postprocessor.py        # Notion JSON 후처리 (블록 보정)
│   └── markdown_to_notion.py          # Markdown → Notion 블록 JSON
│
├── upload/                             # Phase 1 STEP 2: Notion DB 업로드
│   ├── __init__.py
│   ├── run.py                          # 진입점: python -m upload.run
│   ├── block_utils.py                  # 블록 변환·분할 유틸리티
│   └── upload.py                       # NotionUploader 클래스
│
├── graphrag/                           # Phase 2: Notion → Neo4j GraphRAG
│   ├── step1_scraper/                  # STEP 3: Notion 데이터 추출
│   │   ├── run.py                      # python -m graphrag.step1_scraper.run
│   │   ├── notion_client.py            # Notion API 클라이언트
│   │   └── content_parser.py           # Notion 블록 → 텍스트/섹션 변환
│   ├── step2_graph/                    # STEP 4: Neo4j 그래프 구축
│   │   ├── run.py                      # GraphRunner (python -m graphrag.step2_graph.run)
│   │   ├── builder.py                  # GraphBuilder (노드/관계 생성)
│   │   └── chunker.py                  # TextChunker (텍스트 청킹)
│   ├── step3_embedding/                # STEP 5: 임베딩 생성
│   │   ├── run.py                      # python -m graphrag.step3_embedding.run
│   │   ├── embedder.py                 # 배치 임베딩 + 벡터 인덱스
│   │   └── precheck.py                 # 사전 점검 스크립트
│   ├── step4_rag/                      # STEP 6: GraphRAG 파이프라인
│   │   ├── run.py                      # python -m graphrag.step4_rag.run
│   │   └── rag_pipeline.py             # ToolsRetriever + 프롬프트
│   └── step5_web/                      # STEP 7: 웹 시각화 서버
│       ├── run.py                      # python -m graphrag.step5_web.run
│       ├── app.py                      # FastAPI 진입점
│       ├── config.py                   # 환경변수, 설정값
│       ├── routers/                    # API 라우트
│       ├── services/                   # LLM, RAG, 파서
│       └── static/index.html           # 프론트엔드 UI
│
├── package/                            # 외부 패키지 (editable 설치)
│   ├── confluence-markdown-exporter/
│   └── notion-markdown/
├── utils/                              # 유틸리티
├── doc/                                # 문서
├── output/                             # 변환/추출 결과 (git 제외)
├── pyproject.toml                      # 의존성 + 빌드 설정
├── .env.example                        # 환경변수 템플릿
└── .gitignore
```

### 핵심 파일 설명

| 파일 | 역할 |
|---|---|
| `pipeline/run.py` | Phase 1 STEP 1 진입점. Pipeline 클래스. Confluence → Markdown + Notion JSON 변환 |
| `upload/run.py` | Phase 1 STEP 2 진입점. UploadRunner 클래스. 대화형 폴더/Domain 선택 후 Notion DB 업로드 |
| `pipeline/confluence_to_markdown.py` | Confluence → Markdown + 첨부파일 + meta.json |
| `pipeline/converter_overrides.py` | confluence-markdown-exporter 패키지 Converter 메서드 오버라이딩 |
| `pipeline/md_preprocessor.py` | Markdown 전처리 (Confluence 고유 패턴 변환) |
| `pipeline/notion_postprocessor.py` | Notion JSON 후처리 (Notion API 호환 형태로 보정) |
| `pipeline/markdown_to_notion.py` | Markdown → Notion 블록 JSON |
| `upload/upload.py` | NotionUploader 클래스. DB 스키마 관리 + 블록 분할 전송 + 미디어 업로드 |
| `graphrag/step1_scraper/run.py` | Phase 2 STEP 3 진입점. NotionScraper 클래스. Notion DB 전체 페이지 추출 → JSON |
| `graphrag/step1_scraper/content_parser.py` | ContentParser 클래스. Notion 블록 → 텍스트/섹션 변환 (27개 블록 타입 지원) |
| `graphrag/step2_graph/run.py` | Phase 2 STEP 4 진입점. GraphRunner 클래스. JSON → Neo4j 그래프 구축 |
| `graphrag/step2_graph/builder.py` | GraphBuilder 클래스. 스키마 기반 노드/관계 생성, TextChunker로 청킹 위임 |
| `graphrag/step2_graph/chunker.py` | TextChunker 클래스. 섹션 기반 하이브리드 청킹 + recursive 청킹 |
| `graphrag/step3_embedding/run.py` | Phase 2 STEP 5 진입점. Content 노드에 임베딩 생성 |
| `graphrag/step4_rag/run.py` | Phase 2 STEP 6 진입점. GraphRAG 파이프라인 구성 + 검증 |
| `graphrag/step4_rag/rag_pipeline.py` | VectorCypherRetriever + Text2CypherRetriever + ToolsRetriever |
| `graphrag/step5_web/run.py` | Phase 2 STEP 7 진입점. FastAPI 웹 시각화 서버 |
| `graphrag/step5_web/services/llm.py` | BedrockLLM + AzureOpenAIEmbeddings 어댑터 |

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

`python -m pipeline.run` 또는 `python -m upload.run` 실행 시 필수 환경변수가 누락되면 에러 메시지와 함께 종료된다. `.env` 파일이 프로젝트 루트에 있는지, 모든 필수 변수가 채워져 있는지 확인한다.

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

### Neo4j 연결 실패

Neo4j Desktop에서 DBMS가 "Running" 상태인지 확인한다.

1. Neo4j Desktop을 열고 해당 DBMS의 **Start** 버튼 클릭
2. 상태가 "Running"으로 바뀌면 `.env`의 값을 확인:

```env
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_PASSWORD=Neo4j-Desktop에서-설정한-비밀번호
```

Docker 사용 시:

```bash
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/your-password neo4j:latest
```

### AWS Bedrock 인증 오류

AWS 자격증명이 `.env`에 올바르게 설정되어 있는지 확인한다. Bedrock 모델 접근 권한이 활성화되어 있는지 AWS 콘솔에서 확인한다.

### Azure OpenAI 임베딩 실패

`AZURE_OPENAI_ENDPOINT`와 `AZURE_OPENAI_API_KEY`가 올바른지, 지정한 `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` 배포가 존재하는지 확인한다.

---

## 가상환경이란?

> C# 개발자를 위한 설명

Python의 **가상환경(`.venv/`)** 은 C#의 NuGet packages 폴더와 유사한 개념이다.

| C# (.NET) | Python |
|---|---|
| NuGet packages 폴더 | `.venv/` 폴더 |
| `.csproj`의 `<PackageReference>` | `pyproject.toml`의 `dependencies` |
| `dotnet restore` | `uv sync` |
| `packages.lock.json` | `uv.lock` |
| 솔루션별 독립 패키지 | 프로젝트별 독립 패키지 |

- `init.ps1` (내부 `uv sync`)이 `.venv/` 폴더를 자동 생성한다
- VS Code에서 인터프리터를 `.venv\Scripts\python.exe`로 선택해야 패키지를 인식한다
- `.venv/` 폴더는 `.gitignore`에 포함되어 있어 Git에 올라가지 않는다

### editable 설치란?

`package/confluence-markdown-exporter/` 폴더의 소스 코드가 가상환경에 직접 링크된다.
소스 코드를 수정하면 별도 재설치 없이 즉시 반영된다. C#에서 프로젝트 참조(ProjectReference)로 다른 프로젝트를 직접 참조하는 것과 같다.

이 설정은 `pyproject.toml`의 아래 부분에서 관리된다:

```toml
[tool.uv.sources]
confluence-markdown-exporter = { path = "package/confluence-markdown-exporter", editable = true }
notion-markdown = { path = "package/notion-markdown", editable = true }
```

---

## 수동 설치 (선택)

`init.ps1` 대신 수동으로 설치하려면 아래 단계를 따른다.

### uv 설치

uv는 Python 프로젝트의 가상환경 생성, 의존성 설치, Python 버전 관리를 한 번에 처리하는 도구이다.

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

설치 확인:

```bash
uv --version
```

> uv에 대한 자세한 내용: <https://docs.astral.sh/uv/>

### 프로젝트 동기화

```bash
uv sync
```

이 명령어가 수행하는 작업:

1. `.python-version`에 지정된 Python을 자동 다운로드 (없는 경우)
2. `.venv/` 가상환경 생성
3. `pyproject.toml`에 선언된 의존성 설치
4. `uv.lock` 파일 생성/갱신 (의존성 버전 고정)

### .env 파일 생성

`init.ps1`이 `.env.example` → `.env` 복사를 자동으로 처리한다. 수동으로 생성해야 하는 경우:

```bash
copy .env.example .env    # Windows (PowerShell)
```

---

## Python 기초 (C# 개발자용)

Python을 처음 접하는 C# 개발자를 위한 주요 관용구 대응표이다.

### 진입점 (Entry Point)

```python
# Python                              # C# 대응
if __name__ == "__main__":            # static void Main(string[] args)
    main()                            # {  Main();  }
```

`python -m pipeline.run`으로 실행하면 해당 파일의 `if __name__ == "__main__":` 블록이 실행된다.

### 리소스 관리

```python
# Python                              # C# 대응
with driver.session() as session:     # using (var session = driver.Session())
    session.run(query)                # {  session.Run(query);  }
```

`with ... as`는 C#의 `using`과 동일하다. 블록을 벗어나면 자동으로 `close()`가 호출된다.

### 타입 힌트

| Python | C# |
|---|---|
| `list[dict]` | `List<Dictionary<string, object>>` |
| `str \| None` | `string?` |
| `Path \| None` | `FileInfo?` |
| `frozenset` | `IReadOnlySet<T>` |
| `dict[str, Any]` | `Dictionary<string, object>` |

### 주요 관용구

| Python | C# 대응 | 설명 |
|---|---|---|
| `sys.path` | `.csproj`의 `ProjectReference` | 모듈 검색 경로 |
| `**kwargs` | `params Dictionary<string, object>` | 키워드 인자 |
| `props.pop("key", "")` | `dict.Remove(key)` + 반환값 | 꺼내면서 삭제 |
| `Path(__file__)` | `Assembly.GetExecutingAssembly().Location` | 현재 파일 경로 |
| `lambda x: x + 1` | `x => x + 1` | 익명 함수 |
| `[x for x in items]` | `items.Select(x => x).ToList()` | LINQ 변환 |

### 클로저 (내부 함수)

```python
def parse_sections(self, blocks):
    sections = []

    def _flush():                     # C#: 로컬 함수 void Flush() { ... }
        sections.append(current)      # 외부 변수 sections를 직접 참조 (캡처)

    for block in blocks:
        # ...
        _flush()
    return sections
```

Python의 내부 함수(`_flush`)는 C#의 로컬 함수와 동일하다. 외부 스코프의 변수를 캡처하여 사용한다.
