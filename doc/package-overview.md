# confluence-markdown-exporter 기능 가이드

- **GitHub**: <https://github.com/Spenhouet/confluence-markdown-exporter>
- **버전**: 3.2.0
- **라이선스**: MIT
- **Python**: >= 3.10

Confluence 페이지를 Markdown 파일로 변환하는 도구.
CLI 명령어로 바로 사용할 수 있고, Python 코드에서 import하여 프로그래밍 방식으로도 사용 가능하다.

---

## 목차

1. [CLI 명령어](#cli-명령어)
2. [설정 (config)](#설정-config)
3. [Python API 사용법](#python-api-사용법)
4. [Confluence 마크다운 변환 지원 범위](#confluence-마크다운-변환-지원-범위)

---

## CLI 명령어

설치 후 `confluence-markdown-exporter` 또는 단축 명령어 `cf-export`로 실행한다.

```bash
confluence-markdown-exporter --help
cf-export --help
```

### pages -- 개별 페이지 내보내기

페이지 ID 또는 URL을 지정하여 하나 이상의 페이지를 Markdown으로 내보낸다.

```bash
# 페이지 ID로 내보내기
cf-export pages 1462521351

# 여러 페이지 동시에
cf-export pages 1462521351 1462521352 1462521353

# URL로 내보내기
cf-export pages "https://your-site.atlassian.net/wiki/spaces/DEV/pages/1462521351"

# 출력 경로 지정
cf-export pages 1462521351 --output-path ./my-output
```

| 인자/옵션 | 설명 |
|---|---|
| `pages` (필수) | 페이지 ID 또는 URL. 여러 개 가능. |
| `--output-path` | 출력 디렉토리. 미지정 시 설정의 `export.output_path` 사용. |

### pages-with-descendants -- 하위 페이지 포함 내보내기

지정한 페이지와 그 아래의 **모든 하위 페이지**를 한 번에 내보낸다.

```bash
# 페이지 + 하위 전체
cf-export pages-with-descendants 1462521351

# URL로
cf-export pages-with-descendants "https://your-site.atlassian.net/wiki/spaces/DEV/pages/1462521351"

# 출력 경로 지정
cf-export pages-with-descendants 1462521351 --output-path ./export
```

| 인자/옵션 | 설명 |
|---|---|
| `pages` (필수) | 최상위 페이지 ID 또는 URL. 여러 개 가능. |
| `--output-path` | 출력 디렉토리. |

### spaces -- 특정 Space 전체 내보내기

Space 키를 지정하여 해당 Space의 **모든 페이지**를 내보낸다.

```bash
# Space 키로 내보내기
cf-export spaces DEV

# 여러 Space 동시에
cf-export spaces DEV TEAM PRODUCT

# 출력 경로 지정
cf-export spaces DEV --output-path ./export
```

| 인자/옵션 | 설명 |
|---|---|
| `space_keys` (필수) | Space 키 (예: `DEV`, `TEAM`). 여러 개 가능. |
| `--output-path` | 출력 디렉토리. |

> Windows PowerShell에서 개인 Space(`~username`)는 틸드 확장이 자동 처리된다.

### all-spaces -- 전체 Confluence 내보내기

Confluence 인스턴스의 **모든 글로벌 Space**를 한 번에 내보낸다.

```bash
cf-export all-spaces

cf-export all-spaces --output-path ./full-export
```

| 인자/옵션 | 설명 |
|---|---|
| `--output-path` | 출력 디렉토리. |

### config -- 설정 관리

대화형 메뉴로 인증, 내보내기 옵션 등을 설정하거나 현재 설정을 확인한다.

```bash
# 대화형 설정 메뉴 열기
cf-export config

# 특정 설정 항목으로 바로 이동
cf-export config --jump-to auth.confluence
cf-export config --jump-to export

# 현재 설정 JSON으로 출력
cf-export config --show
```

| 인자/옵션 | 설명 |
|---|---|
| `--jump-to` | 설정 메뉴의 특정 항목으로 바로 이동 (예: `auth.confluence`, `export`). |
| `--show` | 대화형 메뉴 대신 현재 설정을 JSON으로 표시. |

### version -- 버전 확인

```bash
cf-export version
# 출력: confluence-markdown-exporter 3.2.0
```

---

## 설정 (config)

설정은 `cf-export config` 대화형 메뉴로 관리하거나, Python 코드에서 직접 변경할 수 있다.
설정 파일은 OS별 앱 디렉토리에 `app_data.json`으로 저장된다.
환경변수 `CME_CONFIG_PATH`로 설정 파일 경로를 직접 지정할 수도 있다.

### 내보내기 설정 (export)

| 설정 | 기본값 | 설명 |
|---|---|---|
| `output_path` | `.` (현재 디렉토리) | 내보내기 출력 디렉토리 |
| `page_path` | `{space_name}/{homepage_title}/{ancestor_titles}/{page_title}.md` | Markdown 파일 저장 경로 템플릿 |
| `page_href` | `relative` | 페이지 간 링크 방식 (`absolute` / `relative`) |
| `attachment_path` | `{space_name}/attachments/{attachment_file_id}{attachment_extension}` | 첨부파일 저장 경로 템플릿 |
| `attachment_href` | `relative` | 첨부파일 링크 방식 (`absolute` / `relative`) |
| `attachment_export_all` | `false` | `true`: 모든 첨부파일 / `false`: 본문에서 참조된 것만 |
| `page_breadcrumbs` | `true` | Markdown 상단에 상위 페이지 breadcrumb 링크 표시 |
| `include_document_title` | `true` | Markdown 최상단에 `# 제목` 포함 |
| `filename_encoding` | 특수문자 -> `_` 치환 | 파일명에서 특수문자 치환 규칙 (JSON 형식) |
| `filename_length` | `255` | 파일명 최대 길이 |

#### 경로 템플릿 변수

`page_path`와 `attachment_path`에서 사용할 수 있는 변수:

**공통 변수:**

| 변수 | 설명 | 예시 |
|---|---|---|
| `{space_key}` | Space 키 | `DEV` |
| `{space_name}` | Space 이름 | `Development` |
| `{homepage_id}` | Space 홈페이지 ID | `123456` |
| `{homepage_title}` | Space 홈페이지 제목 | `Home` |
| `{ancestor_ids}` | 상위 페이지 ID (슬래시 구분) | `111/222/333` |
| `{ancestor_titles}` | 상위 페이지 제목 (슬래시 구분) | `Guide/Setup` |

**page_path 전용:**

| 변수 | 설명 |
|---|---|
| `{page_id}` | 페이지 ID |
| `{page_title}` | 페이지 제목 |

**attachment_path 전용:**

| 변수 | 설명 |
|---|---|
| `{attachment_id}` | 첨부파일 ID |
| `{attachment_title}` | 첨부파일 제목 (원본 파일명) |
| `{attachment_file_id}` | 첨부파일 GUID |
| `{attachment_extension}` | 첨부파일 확장자 (`.png`, `.pdf` 등) |

### 연결 설정 (connection_config)

| 설정 | 기본값 | 설명 |
|---|---|---|
| `backoff_and_retry` | `true` | 네트워크 오류 시 자동 재시도 |
| `backoff_factor` | `2` | 재시도 간격 배수 (2초, 4초, 8초...) |
| `max_backoff_seconds` | `60` | 최대 대기 시간 |
| `max_backoff_retries` | `5` | 최대 재시도 횟수 |
| `retry_status_codes` | `[413, 429, 502, 503, 504]` | 재시도할 HTTP 상태 코드 |
| `verify_ssl` | `true` | SSL 인증서 검증 여부 |

### 인증 설정 (auth)

두 가지 인증 방식 중 하나를 선택한다:

**방식 1: Personal Access Token (PAT)**

| 설정 | 설명 |
|---|---|
| `auth.confluence.url` | Confluence URL (예: `https://company.atlassian.net`) |
| `auth.confluence.pat` | Personal Access Token |

**방식 2: Username + API Token**

| 설정 | 설명 |
|---|---|
| `auth.confluence.url` | Confluence URL |
| `auth.confluence.username` | 사용자 이메일 |
| `auth.confluence.api_token` | API 토큰 ([여기서 발급](https://id.atlassian.com/manage-profile/security/api-tokens)) |

Jira 인증도 동일한 구조: `auth.jira.url`, `auth.jira.pat` 등.

### Python에서 설정 변경

```python
from confluence_markdown_exporter.utils.app_data_store import get_settings, set_setting, reset_to_defaults

# 현재 설정 확인
settings = get_settings()
print(settings.export.output_path)
print(settings.export.page_path)

# 개별 설정 변경
set_setting("export.output_path", "./my-output")
set_setting("export.attachment_export_all", True)
set_setting("export.page_breadcrumbs", False)

# 기본값으로 초기화
reset_to_defaults("export")       # export 섹션만 초기화
reset_to_defaults(None)           # 전체 설정 초기화
```

---

## Python API 사용법

CLI 대신 Python 코드에서 직접 import하여 사용할 수 있다.
본 프로젝트의 `page_to_markdown.py`가 이 방식을 사용한다.

### 초기화 패턴

`confluence.py` 모듈은 **import 시점에** `get_confluence_instance()`를 호출하여
전역 Confluence 클라이언트를 생성한다.
코드에서 직접 사용하려면 **import 전에 monkey-patch**해야 한다.

```python
from atlassian import Confluence as ConfluenceClient
import confluence_markdown_exporter.api_clients as _api

# 1. 자체 Confluence 클라이언트 생성
client = ConfluenceClient(url="https://your-site.atlassian.net", token="YOUR_PAT")

# 2. get_confluence_instance를 패치
_api.get_confluence_instance = lambda: client

# 3. 패치 이후에 Page를 import (순서 중요!)
from confluence_markdown_exporter.confluence import Page
```

> **주의**: `Page` import를 패치보다 먼저 하면 대화형 인증이 실행된다.

### Page -- 핵심 클래스

```python
from confluence_markdown_exporter.confluence import Page

# 페이지 ID로 생성
page = Page.from_id(1462521351)

# URL로 생성
page = Page.from_url("https://your-site.atlassian.net/wiki/spaces/DEV/pages/123")
```

| 프로퍼티 | 타입 | 설명 |
|---|---|---|
| `page.id` | `int` | 페이지 고유 ID |
| `page.title` | `str` | 페이지 제목 |
| `page.body` | `str` | 원본 HTML 본문 |
| `page.markdown` | `str` | **Markdown 변환 결과** |
| `page.html` | `str` | 제목 포함 HTML |
| `page.space` | `Space` | 소속 Space 객체 |
| `page.attachments` | `list[Attachment]` | 첨부파일 목록 |
| `page.labels` | `list[Label]` | 라벨 목록 |
| `page.ancestors` | `list[int]` | 상위 페이지 ID 목록 |
| `page.descendants` | `list[int]` | 하위 페이지 ID 목록 |

| 메서드 | 설명 |
|---|---|
| `page.export()` | 첨부파일 + Markdown 파일 한 번에 내보내기 |
| `page.export_attachments()` | 첨부파일만 내보내기 |
| `page.export_markdown()` | Markdown 파일만 저장 |
| `page.export_with_descendants()` | 현재 페이지 + 모든 하위 페이지 내보내기 |
| `page.get_attachment_by_id(id)` | 첨부파일 ID로 검색 |
| `page.get_attachment_by_file_id(file_id)` | 첨부파일 file_id로 검색 |
| `page.get_attachments_by_title(title)` | 제목으로 첨부파일 검색 |

### Space

```python
from confluence_markdown_exporter.confluence import Space

space = Space.from_key("DEV")
print(space.name)         # Space 이름
print(space.pages)        # 모든 페이지 ID 목록
space.export()            # Space 전체 내보내기
```

| 필드 | 설명 |
|---|---|
| `space.key` | Space 키 (예: `"DEV"`) |
| `space.name` | Space 이름 |
| `space.description` | Space 설명 |
| `space.homepage` | 홈페이지 ID |
| `space.pages` | Space 내 모든 페이지 ID |

### Organization

```python
from confluence_markdown_exporter.confluence import Organization

org = Organization.from_api()
print(len(org.spaces))    # 전체 Space 수
print(len(org.pages))     # 전체 페이지 수
org.export()              # 전체 Confluence 내보내기
```

### Attachment

```python
# 페이지의 첨부파일 확인
for att in page.attachments:
    print(f"{att.title} ({att.media_type}, {att.file_size} bytes)")
    att.export()  # 개별 다운로드

# 특정 첨부파일 검색
att = page.get_attachment_by_id("12345")
drawio_files = page.get_attachments_by_title("diagram.drawio")
```

| 필드 | 설명 |
|---|---|
| `att.id` | 첨부파일 ID |
| `att.title` | 파일 제목 (원본 파일명) |
| `att.file_size` | 파일 크기 (bytes) |
| `att.media_type` | MIME 타입 (예: `"image/png"`) |
| `att.file_id` | 파일 GUID |
| `att.extension` | 확장자 (`.png`, `.drawio` 등) |
| `att.filename` | `{file_id}{extension}` 형태 |
| `att.version` | 버전 정보 (`Version` 객체) |

### 보조 클래스

**Label** -- 페이지 라벨

```python
for label in page.labels:
    print(f"{label.name} (prefix: {label.prefix})")
```

**User** -- 사용자 정보

```python
from confluence_markdown_exporter.confluence import User

user = User.from_accountid("abc123")
print(user.display_name, user.email)
```

**Version** -- 버전 정보

```python
att = page.attachments[0]
print(f"수정자: {att.version.by.display_name}")
print(f"수정일: {att.version.when}")
print(f"버전: {att.version.number}")
```

**JiraIssue** -- Jira 이슈 (Jira 연동 시)

```python
from confluence_markdown_exporter.confluence import JiraIssue

issue = JiraIssue.from_key("PROJ-123")
print(f"{issue.key}: {issue.summary} [{issue.status}]")
```

### 유틸리티 함수

```python
from confluence_markdown_exporter.utils.export import save_file, sanitize_filename, sanitize_key
from confluence_markdown_exporter.confluence import export_page, export_pages

# 파일 저장 (부모 디렉토리 자동 생성)
save_file(Path("./out/test.md"), "# Hello")

# 파일명 정리 (특수문자 치환, Windows 예약어 처리)
safe_name = sanitize_filename("My Page: 2024/01")  # -> "My Page_ 2024_01"

# 문자열을 YAML 키로 변환
key = sanitize_key("My Custom Key!")  # -> "my_custom_key"

# 편의 함수로 내보내기
export_page(1462521351)
export_pages([1462521351, 1462521352])  # tqdm 진행 표시줄 포함
```

### 실제 사용 예시 (전체 흐름)

`page_to_markdown.py`에서 사용하는 패턴:

```python
import os
from pathlib import Path
from atlassian import Confluence as ConfluenceClient
from dotenv import load_dotenv
import confluence_markdown_exporter.api_clients as _api

load_dotenv()

client = ConfluenceClient(
    url=os.getenv("CONFLUENCE_URL"),
    token=os.getenv("CONFLUENCE_PAT"),
)
_api.get_confluence_instance = lambda: client

from confluence_markdown_exporter.confluence import Page

page = Page.from_id(1462521351)

# 접근 불가 체크
if page.title == "Page not accessible":
    print("페이지에 접근할 수 없습니다")
else:
    page.export_attachments()    # 첨부파일 다운로드
    markdown = page.markdown     # HTML -> Markdown 변환

    output = Path("./output") / f"{page.id}_{page.title}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
```

---

## Confluence 마크다운 변환 지원 범위

`page.markdown`이 HTML을 Markdown으로 변환할 때 처리하는 Confluence 요소 목록.
아래 목록에 없는 요소는 변환되지 않으므로, 필요하면 별도 처리를 구현해야 한다.

### 기본 서식

| Confluence 요소 | 변환 결과 | 비고 |
|---|---|---|
| 헤딩 (h1 ~ h6) | `# ~ ######` | ATX 스타일 |
| 단락 | 표준 Markdown 단락 | |
| 줄바꿈 | 표준 Markdown | |
| **볼드** | `**text**` | |
| *이탤릭* | `*text*` | |
| 밑줄 | 변환 없음 (Markdown 미지원) | |
| 위첨자 | `<sup>text</sup>` | HTML 태그로 유지 |
| 아래첨자 | `<sub>text</sub>` | HTML 태그로 유지 |

### 구조 요소

| Confluence 요소 | 변환 결과 | 비고 |
|---|---|---|
| 비순서 목록 | `- item` | |
| 순서 목록 | `1. item` | |
| 태스크 리스트 | `- [x] done` / `- [ ] todo` | GitHub 스타일 체크박스 |
| 테이블 | Markdown 테이블 | rowspan/colspan 지원 |
| 코드 블록 | ` ```language ... ``` ` | 언어 자동 감지 (brush 파라미터) |
| 인용문 | `> text` | |

### 링크 / 미디어

| Confluence 요소 | 변환 결과 | 비고 |
|---|---|---|
| 외부 링크 | `[text](url)` | |
| 페이지 간 링크 | `[페이지 제목](상대경로.md)` | 상대/절대 경로 설정 가능 |
| 깨진 링크 | `[[text]]` | 경고 로그 출력 |
| 이미지 | `![alt](path)` | 첨부파일 경로 자동 매핑 |
| 첨부파일 링크 | `[파일명](첨부파일경로)` | |
| 헤딩 앵커 링크 | `[text](#heading-id)` | |

### Confluence 매크로

| 매크로 | 변환 결과 | 비고 |
|---|---|---|
| 알림 - info | `> [!IMPORTANT]` | GitHub 스타일 Alert |
| 알림 - panel | `> [!NOTE]` | |
| 알림 - tip | `> [!TIP]` | |
| 알림 - note | `> [!WARNING]` | |
| 알림 - warning | `> [!CAUTION]` | |
| 확장 컨테이너 (expand) | `<details><summary>...</summary>...</details>` | HTML 접이식 |
| TOC (목차) | 목차 HTML 변환 | |
| 페이지 속성 (details) | YAML front matter | Markdown 상단에 `---` 블록 |
| 첨부파일 목록 매크로 | 파일/수정일 테이블 | |
| 컬럼 레이아웃 | Markdown 테이블로 변환 | 2열 이상 시 |
| 숨겨진 콘텐츠 (scroll-ignore) | `<!-- 주석 -->` | HTML 주석으로 유지 |

### 다이어그램

| 매크로 | 변환 결과 | 비고 |
|---|---|---|
| draw.io | Mermaid 코드 블록 | drawio 파일에서 Mermaid 추출 시 |
| draw.io (Mermaid 없을 때) | `![diagram](preview.png)` 링크 | PNG 미리보기 이미지 사용 |
| PlantUML | ` ```plantuml ... ``` ` | editor2 XML에서 UML 정의 추출 |

### Jira 연동

| 요소 | 변환 결과 | 비고 |
|---|---|---|
| Jira 이슈 링크 | `[[PROJ-123] 이슈 제목](jira-url)` | Jira API 호출하여 제목 조회 |
| Jira 테이블 매크로 | Markdown 테이블 | |

### 사용자 / 메타데이터

| 요소 | 변환 결과 | 비고 |
|---|---|---|
| 사용자 멘션 (@mention) | 사용자 표시 이름 (텍스트) | `(Unlicensed)`, `(Deactivated)` 접미사 제거 |
| 날짜/시간 | ISO 8601 형식 텍스트 | |
| 라벨 | front matter의 `tags` | `#라벨명` 형태 |
| Breadcrumb | 상위 페이지 링크 체인 | `page_breadcrumbs` 설정으로 on/off |
| 각주 | `[^1]` / `[^1]:` | 위첨자 기반 자동 변환 |

### 변환되지 않는 요소 (별도 구현 필요)

- Confluence 매크로 중 위 목록에 없는 커스텀/서드파티 매크로
- `qc-read-and-understood-signature-box` 등 무시 목록에 있는 매크로 (빈 문자열로 변환)
- iframe 내부 콘텐츠
- Confluence 댓글
- 페이지 히스토리 (버전별 diff)
- Space 권한/설정 정보
