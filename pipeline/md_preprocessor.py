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
    r"\[([^\]]+)\]\(/pages/viewpage\.action\?pageId=\d+\)"
)

_LIST_HEADING_RE = re.compile(
    r"^(\s*[-*+]\s+)#{1,6}\s+(.+)$",
    re.MULTILINE,
)

_HTML_TABLE_RE = re.compile(r"<table[\s>].*?</table>", re.DOTALL)

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

_VIDEO_EXTENSIONS = frozenset({".mp4", ".webm", ".mov", ".avi", ".wmv", ".mkv"})

_VIDEO_LINK_RE = re.compile(
    r"(?:^#{1,6}\s+)?(?:\*\*)?\[([^\]]+\.(?:mp4|webm|mov|avi|wmv|mkv))\]\([^)]+\)(?:\*\*)?",
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
    """GitHub Alert (`> [!TIP]` 등) 을 `<aside>` 태그로 변환한다."""

    def _replace(m: re.Match) -> str:
        alert_type = m.group(1)
        icon = ALERT_ICONS.get(alert_type, "💡")
        body_lines = m.group(2).strip().splitlines()
        content_parts: list[str] = []
        for line in body_lines:
            stripped = re.sub(r"^>\s?", "", line)
            stripped = re.sub(r"^###?\s*", "", stripped)
            if stripped.strip():
                content_parts.append(stripped.strip())
        content = "{{BR}}".join(content_parts)
        return f"<aside>{icon} {content}</aside>\n"

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
    md = fix_broken_email_links(md)
    md = strip_bold_images(md)
    md = extract_heading_images(md)
    md = convert_video_links(md)
    md = strip_empty_headings(md)
    md = convert_alerts_to_callouts(md)
    md = strip_bold_headings(md)
    md = strip_confluence_links(md)
    md = convert_list_headings(md)
    md = convert_html_tables(md)
    return md
