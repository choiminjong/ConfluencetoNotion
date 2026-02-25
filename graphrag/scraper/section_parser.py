"""Notion 블록 JSON → 헤딩 기반 섹션 구조화 파서.

Notion API가 반환하는 블록 리스트를 heading 계층 기반의 섹션으로 분할한다.
각 섹션은 heading_path(계층 경로), content_type, 본문 텍스트를 포함하여
의미 단위 청킹과 Topic 추출에 적합한 구조를 제공한다.

Notion API 전체 27개 블록 타입을 지원한다.
"""

from __future__ import annotations

import re

_ATTACHMENT_RE = re.compile(r"📎\s*\S+\.\w{2,5}")
_MEDIA_TAG_RE = re.compile(r"\[(이미지|비디오|오디오):[^\]]*\]")


def _clean_media_noise(text: str) -> str:
    """첨부파일 참조(📎)와 미디어 태그([이미지: ...])를 제거한다."""
    text = _ATTACHMENT_RE.sub("", text)
    text = _MEDIA_TAG_RE.sub("", text)
    return text


# ---------------------------------------------------------------------------
# rich_text 유틸
# ---------------------------------------------------------------------------

def _rich_text_to_plain(rich_text_list: list[dict]) -> str:
    """rich_text 배열에서 plain_text만 이어 붙인다."""
    return "".join(item.get("plain_text", "") for item in rich_text_list)


# ---------------------------------------------------------------------------
# 개별 블록 → 텍스트 변환 (섹션 내부에서 사용)
# ---------------------------------------------------------------------------

_IGNORED_TYPES = frozenset({
    "breadcrumb", "table_of_contents", "divider", "unsupported",
})


def _block_to_text(block: dict, depth: int = 0) -> str:
    """단일 블록을 텍스트로 변환한다. heading 블록은 여기서 처리하지 않는다."""
    block_type = block.get("type", "")
    data = block.get(block_type, {})
    indent = "  " * depth

    if block_type in _IGNORED_TYPES:
        return ""

    # --- 텍스트 블록 ---
    if block_type in ("paragraph", "quote"):
        text = _rich_text_to_plain(data.get("rich_text", []))
        children_text = _children_to_text(data.get("children", []), depth)
        parts = [f"{indent}{text}"] if text else []
        if children_text:
            parts.append(children_text)
        return "\n".join(parts)

    if block_type == "callout":
        text = _rich_text_to_plain(data.get("rich_text", []))
        children_text = _children_to_text(data.get("children", []), depth)
        parts = [f"{indent}{text}"] if text else []
        if children_text:
            parts.append(children_text)
        return "\n".join(parts)

    if block_type == "bulleted_list_item":
        text = _rich_text_to_plain(data.get("rich_text", []))
        children_text = _children_to_text(data.get("children", []), depth + 1)
        result = f"{indent}- {text}"
        if children_text:
            result += "\n" + children_text
        return result

    if block_type == "numbered_list_item":
        text = _rich_text_to_plain(data.get("rich_text", []))
        children_text = _children_to_text(data.get("children", []), depth + 1)
        result = f"{indent}1. {text}"
        if children_text:
            result += "\n" + children_text
        return result

    if block_type == "to_do":
        text = _rich_text_to_plain(data.get("rich_text", []))
        checked = "x" if data.get("checked") else " "
        children_text = _children_to_text(data.get("children", []), depth + 1)
        result = f"{indent}- [{checked}] {text}"
        if children_text:
            result += "\n" + children_text
        return result

    if block_type == "toggle":
        text = _rich_text_to_plain(data.get("rich_text", []))
        children_text = _children_to_text(data.get("children", []), depth)
        parts = [f"{indent}{text}"] if text else []
        if children_text:
            parts.append(children_text)
        return "\n".join(parts)

    # --- 코드/수식 ---
    if block_type == "code":
        text = _rich_text_to_plain(data.get("rich_text", []))
        lang = data.get("language", "")
        return f"{indent}```{lang}\n{text}\n{indent}```"

    if block_type == "equation":
        return f"{indent}{data.get('expression', '')}"

    # --- 테이블 ---
    if block_type == "table":
        return _parse_table(data, indent)

    # --- 구조/레이아웃 블록 (children 재귀) ---
    if block_type == "synced_block":
        synced = data.get("synced_from")
        children = data.get("children", [])
        if children:
            return _children_to_text(children, depth)
        return ""

    if block_type == "column_list":
        children = data.get("children", [])
        parts = []
        for col in children:
            col_data = col.get("column", {})
            col_children = col_data.get("children", [])
            text = _children_to_text(col_children, depth)
            if text:
                parts.append(text)
        return "\n".join(parts)

    if block_type == "column":
        children = data.get("children", [])
        return _children_to_text(children, depth)

    if block_type == "template":
        children = data.get("children", [])
        return _children_to_text(children, depth)

    # --- 참조/미디어 블록 ---
    if block_type == "child_page":
        title = data.get("title", "")
        return f"{indent}[하위 페이지: {title}]" if title else ""

    if block_type == "child_database":
        title = data.get("title", "")
        return f"{indent}[인라인 DB: {title}]" if title else ""

    if block_type in ("image", "video", "audio"):
        return ""

    if block_type in ("file", "pdf"):
        caption = _rich_text_to_plain(data.get("caption", []))
        name = data.get("name", "")
        label = name or caption
        tag = "PDF" if block_type == "pdf" else "파일"
        return f"{indent}[{tag}: {label}]" if label else ""

    if block_type == "bookmark":
        caption = _rich_text_to_plain(data.get("caption", []))
        url = data.get("url", "")
        return f"{indent}{caption or url}" if (caption or url) else ""

    if block_type == "embed":
        url = data.get("url", "")
        return f"{indent}[임베드: {url}]" if url else ""

    if block_type == "link_preview":
        url = data.get("url", "")
        return f"{indent}[링크: {url}]" if url else ""

    # heading 블록이 이 함수에 들어온 경우 (toggleable heading의 children 등)
    if block_type.startswith("heading_"):
        text = _rich_text_to_plain(data.get("rich_text", []))
        level = int(block_type[-1])
        return f"{indent}{'#' * level} {text}"

    return ""


def _parse_table(data: dict, indent: str) -> str:
    """테이블 블록을 텍스트로 변환한다."""
    rows = data.get("children", [])
    if not rows:
        return ""

    lines = []
    for row in rows:
        row_data = row.get("table_row", {})
        cells = row_data.get("cells", [])
        cell_texts = [_rich_text_to_plain(cell) for cell in cells]
        lines.append(f"{indent}| " + " | ".join(cell_texts) + " |")
    return "\n".join(lines)


def _children_to_text(children: list[dict], depth: int = 0) -> str:
    """children 블록 리스트를 텍스트로 변환한다."""
    parts = []
    for child in children:
        text = _block_to_text(child, depth)
        if text:
            parts.append(text)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# content_type 판별
# ---------------------------------------------------------------------------

_CODE_TYPES = frozenset({"code", "equation"})
_TABLE_TYPES = frozenset({"table"})
_TEXT_TYPES = frozenset({
    "paragraph", "quote", "callout", "bulleted_list_item",
    "numbered_list_item", "to_do", "toggle",
})


def _determine_content_type(block_types: list[str]) -> str:
    """섹션 내 블록 타입 목록을 분석하여 content_type을 결정한다."""
    if not block_types:
        return "text"

    meaningful = [t for t in block_types if t not in _IGNORED_TYPES]
    if not meaningful:
        return "text"

    has_code = any(t in _CODE_TYPES for t in meaningful)
    has_table = any(t in _TABLE_TYPES for t in meaningful)
    has_text = any(t in _TEXT_TYPES for t in meaningful)

    categories = sum([has_code, has_table, has_text])

    if categories > 1:
        return "mixed"
    if has_code:
        return "code"
    if has_table:
        return "table"
    return "text"


# ---------------------------------------------------------------------------
# 메인 함수: blocks → sections
# ---------------------------------------------------------------------------

def _flatten_structural_blocks(blocks: list[dict]) -> list[dict]:
    """synced_block, column_list/column 등 구조 블록의 children을 풀어낸다.

    heading 블록은 그대로 유지하고, 구조 블록 안의 콘텐츠를
    최상위 레벨로 끌어올려 섹션 파서가 올바르게 처리할 수 있게 한다.
    """
    result: list[dict] = []

    for block in blocks:
        block_type = block.get("type", "")
        data = block.get(block_type, {})

        if block_type == "synced_block":
            children = data.get("children", [])
            result.extend(_flatten_structural_blocks(children))
        elif block_type == "column_list":
            for col in data.get("children", []):
                col_data = col.get("column", {})
                result.extend(_flatten_structural_blocks(col_data.get("children", [])))
        elif block_type == "column":
            result.extend(_flatten_structural_blocks(data.get("children", [])))
        else:
            result.append(block)

    return result


def blocks_to_sections(blocks: list[dict]) -> list[dict]:
    """Notion 블록 리스트를 헤딩 기반 섹션으로 분할한다.

    Returns:
        섹션 딕셔너리 리스트. 각 섹션:
        - heading: 현재 섹션의 헤딩 텍스트
        - heading_level: 헤딩 레벨 (1, 2, 3). 헤딩 없는 첫 섹션은 0
        - heading_path: 상위 헤딩을 포함한 계층 경로 리스트
        - content_type: "text" | "code" | "table" | "mixed"
        - text: 섹션 본문 텍스트
    """
    flat_blocks = _flatten_structural_blocks(blocks)

    sections: list[dict] = []
    heading_stack: list[tuple[int, str]] = []
    current_texts: list[str] = []
    current_block_types: list[str] = []

    def _flush_section() -> None:
        """현재 누적된 블록들을 하나의 섹션으로 저장한다."""
        text = _clean_media_noise("\n".join(current_texts)).strip()
        if not text and not heading_stack:
            return

        sections.append({
            "heading": heading_stack[-1][1] if heading_stack else "",
            "heading_level": heading_stack[-1][0] if heading_stack else 0,
            "heading_path": [h[1] for h in heading_stack],
            "content_type": _determine_content_type(current_block_types),
            "text": text,
        })

    for block in flat_blocks:
        block_type = block.get("type", "")
        data = block.get(block_type, {})

        if block_type.startswith("heading_"):
            _flush_section()
            current_texts.clear()
            current_block_types.clear()

            level = int(block_type[-1])
            heading_text = _rich_text_to_plain(data.get("rich_text", []))

            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, heading_text))

            if data.get("is_toggleable") and data.get("children"):
                for child in data["children"]:
                    child_text = _block_to_text(child)
                    if child_text:
                        current_texts.append(child_text)
                    current_block_types.append(child.get("type", ""))
        else:
            text = _block_to_text(block)
            if text:
                current_texts.append(text)
            current_block_types.append(block_type)

    _flush_section()

    return sections
