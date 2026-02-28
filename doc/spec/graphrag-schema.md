# GraphRAG 그래프 스키마

> Phase 1에서 마이그레이션한 Notion DB 데이터를 Neo4j 그래프로 구축할 때 사용하는 스키마입니다.

---

## 노드 타입

| 노드 | 속성 | 설명 |
|------|------|------|
| `Page` | `page_id`, `title`, `source_url`, `updated`, `status` | Notion 페이지 (Confluence 원본) |
| `Content` | `content_id`, `chunk`, `chunk_index`, `page_id`, `title`, `heading_path`, `content_type`, `embedding` | 페이지 본문의 텍스트 청크 (임베딩 대상) |
| `Space` | `name` | Confluence Space |
| `Domain` | `name` | 문서 도메인 (Jira, Confluence, CI/CD 등) |
| `Topic` | `name` | 문서 토픽 태그 |
| (동적) | `name` | DB 스키마의 select/multi_select 필드에 따라 자동 생성 |

---

## 관계 타입

| 관계 | 방향 | 설명 |
|------|------|------|
| `HAS_CHUNK` | Page → Content | 페이지의 본문 청크 |
| `NEXT_CHUNK` | Content → Content | 청크 순서 관계 |
| `BELONGS_TO` | Page → Domain | 도메인 분류 |
| `IN_SPACE` | Page → Space | Confluence Space 소속 |
| `HAS_TOPIC` | Page → Topic | 토픽 태그 |
| `CHILD_OF` | Page → Page | 부모-자식 페이지 계층 |
| (동적) | Page → (동적 노드) | DB 스키마의 select/multi_select 필드에 따라 자동 생성 |

---

## 스키마 다이어그램

```
Space ──IN_SPACE──► Page ──HAS_CHUNK──► Content ──NEXT_CHUNK──► Content
                     │
                     ├──BELONGS_TO──► Domain
                     ├──HAS_TOPIC──► Topic
                     └──CHILD_OF──► Page (Parent)
```

---

## 청킹 전략

- **방식**: 섹션 기반 하이브리드 청킹 (Heading 구조 기반)
- **최소 청크 크기**: 500자 (미만 시 인접 섹션과 병합)
- **컨텍스트 주입**: 각 청크에 `heading_path` (섹션 계층 경로) 자동 삽입
- **미디어 노이즈 제거**: `📎 파일명`, `[이미지: ...]` 등 첨부파일 참조 텍스트 자동 제거
- **폴백**: 섹션 구조가 없는 페이지는 기존 recursive 텍스트 분할(500자, 100자 오버랩) 사용
- **구분자 우선순위** (recursive 폴백): 문단(`\n\n`) → 줄바꿈(`\n`) → 마침표(`. `) → 쉼표(`, `) → 공백(` `)
