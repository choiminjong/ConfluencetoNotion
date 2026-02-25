"""Notion 블록 JSON → 플레인 텍스트 변환.

Notion API가 반환하는 블록 객체 리스트를 사람이 읽을 수 있는 텍스트로 변환한다.
heading, paragraph, list, table, code, callout, toggle 등을 지원한다.
"""

from __future__ import annotations


def _rich_text_to_plain(rich_text_list: list[dict]) -> str:
    """rich_text 배열에서 plain_text만 이어 붙인다."""
    return "".join(item.get("plain_text", "") for item in rich_text_list)


def _parse_block(block: dict, depth: int = 0) -> str:
    """단일 블록을 텍스트로 변환한다."""
    block_type = block.get("type", "")
    data = block.get(block_type, {})
    indent = "  " * depth

    if block_type in ("paragraph", "quote"):
        text = _rich_text_to_plain(data.get("rich_text", []))
        return f"{indent}{text}" if text else ""

    if block_type.startswith("heading_"):
        text = _rich_text_to_plain(data.get("rich_text", []))
        level = block_type[-1]
        return f"{indent}{'#' * int(level)} {text}"

    if block_type == "bulleted_list_item":
        text = _rich_text_to_plain(data.get("rich_text", []))
        children_text = _parse_children(data.get("children", []), depth + 1)
        result = f"{indent}- {text}"
        if children_text:
            result += "\n" + children_text
        return result

    if block_type == "numbered_list_item":
        text = _rich_text_to_plain(data.get("rich_text", []))
        children_text = _parse_children(data.get("children", []), depth + 1)
        result = f"{indent}1. {text}"
        if children_text:
            result += "\n" + children_text
        return result

    if block_type == "to_do":
        text = _rich_text_to_plain(data.get("rich_text", []))
        checked = "x" if data.get("checked") else " "
        return f"{indent}- [{checked}] {text}"

    if block_type == "code":
        text = _rich_text_to_plain(data.get("rich_text", []))
        lang = data.get("language", "")
        return f"{indent}```{lang}\n{text}\n{indent}```"

    if block_type == "callout":
        text = _rich_text_to_plain(data.get("rich_text", []))
        children_text = _parse_children(data.get("children", []), depth)
        parts = [text] if text else []
        if children_text:
            parts.append(children_text)
        return "\n".join(parts)

    if block_type == "toggle":
        text = _rich_text_to_plain(data.get("rich_text", []))
        children_text = _parse_children(data.get("children", []), depth)
        parts = [f"{indent}{text}"] if text else []
        if children_text:
            parts.append(children_text)
        return "\n".join(parts)

    if block_type == "divider":
        return f"{indent}---"

    if block_type == "table":
        return _parse_table(data, indent)

    if block_type == "image":
        caption = _rich_text_to_plain(data.get("caption", []))
        return f"{indent}[이미지: {caption}]" if caption else ""

    if block_type == "video":
        caption = _rich_text_to_plain(data.get("caption", []))
        return f"{indent}[비디오: {caption}]" if caption else ""

    if block_type == "equation":
        return f"{indent}{data.get('expression', '')}"

    if block_type == "bookmark":
        return f"{indent}{data.get('url', '')}"

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


def _parse_children(children: list[dict], depth: int = 0) -> str:
    """children 블록 리스트를 재귀적으로 텍스트로 변환한다."""
    parts = []
    for child in children:
        text = _parse_block(child, depth)
        if text:
            parts.append(text)
    return "\n".join(parts)


def blocks_to_text(blocks: list[dict]) -> str:
    """블록 리스트 전체를 플레인 텍스트로 변환한다."""
    return _parse_children(blocks)
