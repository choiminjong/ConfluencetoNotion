"""마크다운 전처리 유틸리티.

Confluence Markdown 을 notion-markdown 패키지가 올바르게 처리할 수 있도록
정규식 기반 정제를 수행한다.  모든 함수는 stateless 순수 함수이다.
"""

import re
from urllib.parse import quote

from bs4 import BeautifulSoup


# ------------------------------------------------------------------
# 상수
# ------------------------------------------------------------------

ALERT_ICONS: dict[str, str] = {
    "TIP": "💡",
    "WARNING": "⚠️",
    "NOTE": "📝",
    "CAUTION": "🚨",
    "IMPORTANT": "❗",
}

# ------------------------------------------------------------------
# 컴파일된 정규식 패턴
# ------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_TAG_RE = re.compile(r'^\s*-\s*"?#?([^"]+)"?\s*$', re.MULTILINE)
_UNICODE_ESC_RE = re.compile(r"\\u([0-9a-fA-F]{4})")

_EMPTY_HEADING_RE = re.compile(r"^#{1,6}\s*$\n?", re.MULTILINE)

_ALERT_RE = re.compile(
    r"^> \[!(TIP|WARNING|NOTE|CAUTION|IMPORTANT)\]\s*\n"
    r"((?:^>.*\n?)+)",
    re.MULTILINE,
)

_BOLD_HEADING_RE = re.compile(
    r"^(#{1,3})\s+\*\*(.+?)\*\*\s*$",
    re.MULTILINE,
)

_CONFLUENCE_LINK_RE = re.compile(
    r'\[([^\]]+)\]\(/pages/viewpage\.action\?pageId=\d+(?:\s+"[^"]*")?\)'
)

_LIST_HEADING_RE = re.compile(
    r"^(\s*[-*+]\s+)#{1,6}\s+(.+)$",
    re.MULTILINE,
)

_HTML_TABLE_RE = re.compile(r"<table[\s>].*?</table>", re.DOTALL)

_INLINE_HEADING_RE = re.compile(r"(?<=[^\s#])(#{1,6}\s+)")

_TRIPLE_URL_RE = re.compile(
    r"<(https?://[^>]+)>\s*\1\s*\(\s*\1\s*\)"
)

_H456_RE = re.compile(r"^#{4,6}(\s+)", re.MULTILINE)

_BR_MACRO_RE = re.compile(r"\{\{BR\}\}", re.IGNORECASE)

_INNERMOST_DETAILS_RE = re.compile(
    r"<details>\s*\n?\s*<summary>(.*?)</summary>\s*\n?"
    r"((?:(?!<details>)[\s\S])*?)"
    r"\s*</details>",
)

_ATTACHMENT_SECTION_RE = re.compile(
    r"^#{1,6}\s+\*?\*?첨부\s*파일\*?\*?\s*\n"
    r"[\s\S]*?"
    r"(?=^#{1,6}\s|\Z)",
    re.MULTILINE,
)

_BOLD_IMAGE_RE = re.compile(
    r"\*\*!\[([^\]]*)\]\(([^)]+)\)\*\*",
)

_HEADING_IMAGE_RE = re.compile(
    r"^(#{1,6})\s+(?:\*\*)?!\[([^\]]*)\]\(([^)]+)\)(?:\*\*)?\s*$",
    re.MULTILINE,
)

_BROKEN_EMAIL_RE = re.compile(
    r"([\w.\-+]+)@\[([^\]]+)\]\(https?://[^)]+\)",
)

_VELOCITY_IMAGE_RE = re.compile(
    r"!\[\]\(\$\w+(?:\.\w+(?:\([^)]*\))?)+\)\s*",
)

_PAGETREE_ENTRY_RE = re.compile(
    r"\[!\[\]\(\$\w+(?:\.\w+(?:\([^)]*\))?)+\)\s+"
    r"(.+?)\n"
    r"\s*[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}"
    r"\]\(/pages/viewpage\.action\?pageId=\d+"
    r'(?:\s+"[^"]*")?\)',
)

_NESTED_QUOTE_RE = re.compile(r"^(?:>\s*){2,}", re.MULTILINE)

_QUOTED_DETAILS_RE = re.compile(
    r">?\s?<details>\s*\n(>\s?<summary>[\s\S]*?>\s*</details>)",
)

_VIDEO_EXTENSIONS = frozenset({".mp4", ".webm", ".mov", ".avi", ".wmv", ".mkv"})
VIDEO_EXT_PATTERN = "|".join(ext.lstrip(".") for ext in sorted(_VIDEO_EXTENSIONS))

_VIDEO_LINK_RE = re.compile(
    rf"(?:^#{{1,6}}\s+)?(?:\*\*)?\[([^\]]+\.(?:{VIDEO_EXT_PATTERN}))\]\([^)]+\)(?:\*\*)?",
    re.MULTILINE | re.IGNORECASE,
)


# ------------------------------------------------------------------
# 개별 전처리 함수
# ------------------------------------------------------------------

def _decode_unicode_escapes(s: str) -> str:
    return _UNICODE_ESC_RE.sub(lambda m: chr(int(m.group(1), 16)), s)


def strip_frontmatter(markdown: str) -> tuple[str, list[str]]:
    """YAML 프론트매터를 제거하고, tags 값을 추출하여 반환한다."""
    m = _FRONTMATTER_RE.match(markdown)
    if not m:
        return markdown, []

    fm_body = m.group(1)
    tags: list[str] = []
    if "tags:" in fm_body:
        raw = [t.strip() for t in _TAG_RE.findall(fm_body) if t.strip()]
        tags = [_decode_unicode_escapes(t) for t in raw]

    return markdown[m.end():], tags


def strip_empty_headings(markdown: str) -> str:
    """텍스트 없는 빈 헤딩(`# `, `## ` 등)을 제거한다."""
    return _EMPTY_HEADING_RE.sub("", markdown)


def convert_alerts_to_callouts(markdown: str) -> str:
    """GitHub Alert (`> [!TIP]` 등) 을 `<aside>` 태그로 변환한다.

    callout 내부에 <details> 블록이 있으면 callout 밖으로 분리한다.
    """

    def _replace(m: re.Match) -> str:
        alert_type = m.group(1)
        icon = ALERT_ICONS.get(alert_type, "💡")
        body_lines = m.group(2).strip().splitlines()

        stripped_lines: list[str] = []
        for line in body_lines:
            stripped_lines.append(re.sub(r"^>\s?", "", line))
        body_text = "\n".join(stripped_lines)

        details_blocks: list[str] = []
        remaining = body_text
        while "<details>" in remaining.lower():
            start = remaining.lower().find("<details>")
            end = remaining.lower().find("</details>", start)
            if end == -1:
                break
            end += len("</details>")
            details_blocks.append(remaining[start:end])
            remaining = remaining[:start] + remaining[end:]

        content_parts: list[str] = []
        for line in remaining.splitlines():
            stripped = re.sub(r"^###?\s*", "", line)
            if stripped.strip():
                content_parts.append(stripped.strip())

        result = ""
        if content_parts:
            content = "\n".join(content_parts)
            result = f"<aside>{icon} {content}</aside>\n"

        for block in details_blocks:
            cleaned = "\n".join(
                re.sub(r"^>\s?", "", line) for line in block.splitlines()
            )
            result += f"\n{cleaned}\n"

        return result

    return _ALERT_RE.sub(_replace, markdown)


def strip_bold_headings(markdown: str) -> str:
    """헤딩 내부의 불필요한 bold 마크를 제거한다. `# **text**` -> `# text`"""
    return _BOLD_HEADING_RE.sub(r"\1 \2", markdown)


def strip_confluence_links(markdown: str) -> str:
    """Confluence 내부 링크를 텍스트만 남기고 제거한다."""

    def _replace(m: re.Match) -> str:
        text = m.group(1)
        text = re.sub(r"^(\d+)\.", r"\1\\.", text)
        return text

    return _CONFLUENCE_LINK_RE.sub(_replace, markdown)


def convert_list_headings(markdown: str) -> str:
    """리스트 안의 heading 마크를 bold 로 변환한다. `- ### text` -> `- **text**`"""
    return _LIST_HEADING_RE.sub(r"\1**\2**", markdown)


def convert_html_tables(markdown: str) -> str:
    """Markdown 내 잔존 HTML <table> 블록을 pipe 테이블로 변환한다."""

    def _table_to_pipe(m: re.Match) -> str:
        soup = BeautifulSoup(m.group(0), "html.parser")
        table = soup.find("table")
        if not table:
            return m.group(0)

        rows: list[list[str]] = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            rows.append([c.get_text(" ", strip=True) for c in cells])

        if not rows:
            return m.group(0)

        col_count = max(len(r) for r in rows)
        for row in rows:
            while len(row) < col_count:
                row.append("")

        header = rows[0]
        body = rows[1:] if len(rows) > 1 else []

        lines = ["| " + " | ".join(header) + " |"]
        lines.append("|" + "|".join(" --- " for _ in header) + "|")
        for row in body:
            lines.append("| " + " | ".join(row) + " |")

        return "\n\n" + "\n".join(lines) + "\n\n"

    return _HTML_TABLE_RE.sub(_table_to_pipe, markdown)


def strip_bold_images(markdown: str) -> str:
    """볼드로 감싸진 이미지를 풀어준다. `**![](img)**` -> `![](img)`"""
    return _BOLD_IMAGE_RE.sub(r"![\1](\2)", markdown)


def extract_heading_images(markdown: str) -> str:
    """헤딩 안에 이미지만 있는 경우 헤딩을 제거하고 이미지만 남긴다."""
    return _HEADING_IMAGE_RE.sub(r"![\2](\3)", markdown)


def fix_broken_email_links(markdown: str) -> str:
    """깨진 이메일 링크를 mailto 링크로 수정한다.

    `text@[domain.com](http://domain.com)` -> `[text@domain.com](mailto:text@domain.com)`
    """
    return _BROKEN_EMAIL_RE.sub(r"[\1@\2](mailto:\1@\2)", markdown)


def fix_inline_headings(markdown: str) -> str:
    """헤딩이 이전 텍스트에 줄바꿈 없이 붙어 있는 경우 빈 줄을 삽입한다.

    `text## heading` → `text\n\n## heading`
    """
    return _INLINE_HEADING_RE.sub(r"\n\n\1", markdown)


def deduplicate_urls(markdown: str) -> str:
    """3중 중복 URL 패턴을 정리한다.

    `<url>url (url)` → `[url](url)`
    """
    return _TRIPLE_URL_RE.sub(r"[\1](\1)", markdown)


def normalize_heading_levels(markdown: str) -> str:
    """H4-H6 를 H3 으로 변환한다 (Notion은 H1-H3만 지원)."""
    return _H456_RE.sub(r"###\1", markdown)


def replace_br_macros(markdown: str) -> str:
    """Confluence {{BR}} 매크로를 줄바꿈으로 변환한다."""
    return _BR_MACRO_RE.sub("\n", markdown)


def convert_details_to_delimiters(markdown: str) -> str:
    """<details>/<summary> 를 TOGGLE_START/END 마커로 변환한다.

    notion-markdown 이 내부 콘텐츠를 정상 파싱하도록 HTML 태그 대신
    텍스트 구분자를 사용한다.  중첩을 위해 가장 안쪽부터 반복 치환한다.
    """
    def _replace(m: re.Match) -> str:
        title = m.group(1).strip() or "Toggle"
        content = m.group(2).strip()
        return f"\nTOGGLE_START::{title}\n\n{content}\n\nTOGGLE_END\n"

    prev = None
    while prev != markdown:
        prev = markdown
        markdown = _INNERMOST_DETAILS_RE.sub(_replace, markdown)
    return markdown


def strip_attachments_section(markdown: str) -> str:
    """Confluence 첨부파일 목록 섹션을 제거한다."""
    return _ATTACHMENT_SECTION_RE.sub("", markdown)


def clean_pagetree_entries(markdown: str) -> str:
    """Confluence pagetree/children 매크로 출력을 불릿 리스트로 변환한다."""
    return _PAGETREE_ENTRY_RE.sub(r"- \1", markdown)


def strip_velocity_images(markdown: str) -> str:
    """Velocity 템플릿 이미지 참조($action.*, $child.* 등)를 제거한다."""
    return _VELOCITY_IMAGE_RE.sub("", markdown)


def strip_blockquote_in_details(markdown: str) -> str:
    """<details> 내부에 > 접두사가 있으면 제거한다.

    Confluence 내보내기에서 blockquote 안의 <details> 태그는
    <summary>, 콘텐츠, </details> 모두에 > 접두사가 붙는다.
    이를 제거하여 convert_details_to_delimiters 가 정상 매칭하도록 한다.
    """
    def _clean(m: re.Match) -> str:
        content = m.group(1)
        cleaned = re.sub(r"^>\s?", "", content, flags=re.MULTILINE)
        return "<details>\n" + cleaned

    prev = None
    while prev != markdown:
        prev = markdown
        markdown = _QUOTED_DETAILS_RE.sub(_clean, markdown)
    return markdown


def flatten_nested_blockquotes(markdown: str) -> str:
    """이중 이상의 블록인용(> > text)을 단일 인용(> text)으로 변환한다.

    Notion API 는 quote 안의 quote 를 허용하지 않으므로 마크다운 단계에서
    중첩 인용을 제거한다.
    """
    return _NESTED_QUOTE_RE.sub("> ", markdown)


def convert_video_links(markdown: str) -> str:
    """비디오 파일 링크를 이미지 구문으로 변환하여 블록으로 인식시킨다.

    `[name.mp4](path)` 또는 `### **[name.mp4](path)**` -> `![video](name.mp4)`
    파일명에 공백/한글이 있으면 URL 인코딩한다.
    """
    def _replace(m: re.Match) -> str:
        filename = m.group(1)
        encoded = quote(filename, safe="")
        return f"![video]({encoded})"

    return _VIDEO_LINK_RE.sub(_replace, markdown)


# ------------------------------------------------------------------
# 파이프라인 (위 함수들을 순서대로 호출)
# ------------------------------------------------------------------

def preprocess(markdown: str) -> str:
    """notion-markdown 이 올바르게 처리할 수 있도록 Confluence 고유 패턴을 변환한다."""
    md = markdown
    md = replace_br_macros(md)
    md = fix_inline_headings(md)
    md = deduplicate_urls(md)
    md = strip_attachments_section(md)
    md = fix_broken_email_links(md)
    md = strip_bold_images(md)
    md = extract_heading_images(md)
    md = convert_video_links(md)
    md = strip_empty_headings(md)
    md = normalize_heading_levels(md)
    md = convert_alerts_to_callouts(md)
    md = strip_bold_headings(md)
    md = clean_pagetree_entries(md)
    md = strip_velocity_images(md)
    md = strip_confluence_links(md)
    md = convert_list_headings(md)
    md = convert_html_tables(md)
    md = strip_blockquote_in_details(md)
    md = flatten_nested_blockquotes(md)
    md = convert_details_to_delimiters(md)
    return md
