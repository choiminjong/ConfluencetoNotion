"""Notion 블록 → 플레인 텍스트 / 구조화 섹션 변환.

Notion API가 반환하는 블록 리스트를 두 가지 형태로 변환한다:
  - 플레인 텍스트: 사람이 읽을 수 있는 단순 텍스트
  - 섹션 리스트: heading 계층 기반의 구조화된 섹션

heading, paragraph, list, table, code, callout, toggle 등
Notion API 전체 27개 블록 타입을 지원한다.
"""

from __future__ import annotations

import re

_ATTACHMENT_RE = re.compile(r"📎\s*\S+\.\w{2,5}")
_MEDIA_TAG_RE = re.compile(r"\[(이미지|비디오|오디오):[^\]]*\]")

_IGNORED_TYPES = frozenset({
    "breadcrumb", "table_of_contents", "divider", "unsupported",
})

_CODE_TYPES = frozenset({"code", "equation"})
_TABLE_TYPES = frozenset({"table"})
_TEXT_TYPES = frozenset({
    "paragraph", "quote", "callout", "bulleted_list_item",
    "numbered_list_item", "to_do", "toggle",
})


class ContentParser:
    """Notion 블록 JSON을 플레인 텍스트 또는 heading 기반 섹션으로 변환한다."""

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def parse_text(self, blocks: list[dict]) -> str:
        """블록 리스트 전체를 플레인 텍스트로 변환한다."""
        return self._clean_media_noise(self._parse_children(blocks))

    def parse_sections(self, blocks: list[dict]) -> list[dict]:
        """블록 리스트를 heading 기반 섹션으로 분할한다.

        Returns:
            섹션 딕셔너리 리스트. 각 섹션:
            - heading: 현재 섹션의 헤딩 텍스트
            - heading_level: 헤딩 레벨 (1, 2, 3). 헤딩 없는 첫 섹션은 0
            - heading_path: 상위 헤딩을 포함한 계층 경로 리스트
            - content_type: "text" | "code" | "table" | "mixed"
            - text: 섹션 본문 텍스트
        """
        flat_blocks = self._flatten_structural_blocks(blocks)

        sections: list[dict] = []
        heading_stack: list[tuple[int, str]] = []
        current_texts: list[str] = []
        current_block_types: list[str] = []

        # 클로저: 외부 변수 sections, heading_stack, current_texts, current_block_types를
        # 캡처하여, 현재까지 모인 텍스트를 하나의 섹션으로 확정하고 sections에 추가한다.
        def _flush() -> None:
            text = self._clean_media_noise("\n".join(current_texts)).strip()
            if not text and not heading_stack:
                return
            if not text and heading_stack:
                text = heading_stack[-1][1]
            sections.append({
                "heading": heading_stack[-1][1] if heading_stack else "",
                "heading_level": heading_stack[-1][0] if heading_stack else 0,
                "heading_path": [h[1] for h in heading_stack],
                "content_type": self._determine_content_type(current_block_types),
                "text": text,
            })

        for block in flat_blocks:
            block_type = block.get("type", "")
            data = block.get(block_type, {})

            if block_type.startswith("heading_"):
                _flush()
                current_texts.clear()
                current_block_types.clear()

                level = int(block_type[-1])
                heading_text = self._rich_text_to_plain(data.get("rich_text", []))

                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, heading_text))

                if data.get("is_toggleable") and data.get("children"):
                    for child in data["children"]:
                        child_text = self._section_block_to_text(child)
                        if child_text:
                            current_texts.append(child_text)
                        current_block_types.append(child.get("type", ""))
            else:
                text = self._section_block_to_text(block)
                if text:
                    current_texts.append(text)
                current_block_types.append(block_type)

        _flush()
        return sections

    # ------------------------------------------------------------------
    # 공유 유틸
    # ------------------------------------------------------------------

    def _rich_text_to_plain(self, rich_text_list: list[dict]) -> str:
        """rich_text 배열에서 plain_text만 이어 붙인다."""
        return "".join(item.get("plain_text", "") for item in rich_text_list)

    def _clean_media_noise(self, text: str) -> str:
        """첨부파일 참조(📎)와 미디어 태그([이미지: ...])를 제거한다."""
        text = _ATTACHMENT_RE.sub("", text)
        text = _MEDIA_TAG_RE.sub("", text)
        return text

    def _parse_table(self, data: dict) -> str:
        """테이블 블록을 파이프 기호 없이 평문으로 변환한다.

        첫 행이 헤더이고 2열인 경우 'key: value' 형태,
        그 외는 셀을 쉼표로 구분한다.
        """
        rows = data.get("children", [])
        if not rows:
            return ""

        parsed = []
        for row in rows:
            row_data = row.get("table_row", {})
            cells = row_data.get("cells", [])
            parsed.append([self._rich_text_to_plain(cell) for cell in cells])

        has_header = data.get("has_column_header", False)
        is_kv = len(parsed) > 0 and all(len(r) == 2 for r in parsed)

        lines: list[str] = []
        start = 0
        if has_header and not is_kv:
            header = ", ".join(c for c in parsed[0] if c)
            if header:
                lines.append(header)
            start = 1

        for row_cells in parsed[start:]:
            if is_kv:
                key, val = row_cells
                if key or val:
                    lines.append(f"{key}: {val}" if key else val)
            else:
                line = ", ".join(c for c in row_cells if c)
                if line:
                    lines.append(line)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 플레인 텍스트 변환 내부 (parse_text 계열)
    # ------------------------------------------------------------------

    def _parse_block(self, block: dict, depth: int = 0) -> str:
        """단일 블록을 플레인 텍스트로 변환한다."""
        block_type = block.get("type", "")
        data = block.get(block_type, {})

        if block_type in ("paragraph", "quote"):
            text = self._rich_text_to_plain(data.get("rich_text", []))
            children_text = self._parse_children(data.get("children", []), depth)
            parts = [text] if text else []
            if children_text:
                parts.append(children_text)
            return "\n".join(parts)

        if block_type.startswith("heading_"):
            return self._rich_text_to_plain(data.get("rich_text", []))

        if block_type in ("bulleted_list_item", "numbered_list_item", "to_do"):
            text = self._rich_text_to_plain(data.get("rich_text", []))
            children_text = self._parse_children(data.get("children", []), depth + 1)
            result = text
            if children_text:
                result += "\n" + children_text
            return result

        if block_type == "code":
            return self._rich_text_to_plain(data.get("rich_text", []))

        if block_type == "callout":
            text = self._rich_text_to_plain(data.get("rich_text", []))
            children_text = self._parse_children(data.get("children", []), depth)
            parts = [text] if text else []
            if children_text:
                parts.append(children_text)
            return "\n".join(parts)

        if block_type == "toggle":
            text = self._rich_text_to_plain(data.get("rich_text", []))
            children_text = self._parse_children(data.get("children", []), depth)
            parts = [text] if text else []
            if children_text:
                parts.append(children_text)
            return "\n".join(parts)

        if block_type == "divider":
            return ""

        if block_type == "table":
            return self._parse_table(data)

        if block_type in ("image", "video", "audio"):
            return ""

        if block_type in ("child_page", "child_database"):
            return ""

        if block_type in ("file", "pdf"):
            return ""

        if block_type == "equation":
            return data.get("expression", "")

        if block_type == "bookmark":
            caption = self._rich_text_to_plain(data.get("caption", []))
            return caption if caption else ""

        if block_type in ("embed", "link_preview"):
            return ""

        return ""

    def _parse_children(self, children: list[dict], depth: int = 0) -> str:
        """children 블록 리스트를 재귀적으로 텍스트로 변환한다."""
        parts = []
        for child in children:
            text = self._parse_block(child, depth)
            if text:
                parts.append(text)
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # 섹션 변환 내부 (parse_sections 계열)
    # ------------------------------------------------------------------

    def _section_block_to_text(self, block: dict, depth: int = 0) -> str:
        """단일 블록을 섹션용 텍스트로 변환한다. heading 블록도 처리한다."""
        block_type = block.get("type", "")
        data = block.get(block_type, {})

        if block_type in _IGNORED_TYPES:
            return ""

        if block_type in ("paragraph", "quote"):
            text = self._rich_text_to_plain(data.get("rich_text", []))
            children_text = self._section_children_to_text(data.get("children", []), depth)
            parts = [text] if text else []
            if children_text:
                parts.append(children_text)
            return "\n".join(parts)

        if block_type == "callout":
            text = self._rich_text_to_plain(data.get("rich_text", []))
            children_text = self._section_children_to_text(data.get("children", []), depth)
            parts = [text] if text else []
            if children_text:
                parts.append(children_text)
            return "\n".join(parts)

        if block_type == "bulleted_list_item":
            text = self._rich_text_to_plain(data.get("rich_text", []))
            children_text = self._section_children_to_text(data.get("children", []), depth + 1)
            result = text
            if children_text:
                result += "\n" + children_text
            return result

        if block_type == "numbered_list_item":
            text = self._rich_text_to_plain(data.get("rich_text", []))
            children_text = self._section_children_to_text(data.get("children", []), depth + 1)
            result = text
            if children_text:
                result += "\n" + children_text
            return result

        if block_type == "to_do":
            text = self._rich_text_to_plain(data.get("rich_text", []))
            children_text = self._section_children_to_text(data.get("children", []), depth + 1)
            result = text
            if children_text:
                result += "\n" + children_text
            return result

        if block_type == "toggle":
            text = self._rich_text_to_plain(data.get("rich_text", []))
            children_text = self._section_children_to_text(data.get("children", []), depth)
            parts = [text] if text else []
            if children_text:
                parts.append(children_text)
            return "\n".join(parts)

        if block_type == "code":
            return self._rich_text_to_plain(data.get("rich_text", []))

        if block_type == "equation":
            return data.get("expression", "")

        if block_type == "table":
            return self._parse_table(data)

        if block_type == "synced_block":
            children = data.get("children", [])
            if children:
                return self._section_children_to_text(children, depth)
            return ""

        if block_type == "column_list":
            children = data.get("children", [])
            parts = []
            for col in children:
                col_data = col.get("column", {})
                col_children = col_data.get("children", [])
                text = self._section_children_to_text(col_children, depth)
                if text:
                    parts.append(text)
            return "\n".join(parts)

        if block_type == "column":
            return self._section_children_to_text(data.get("children", []), depth)

        if block_type == "template":
            return self._section_children_to_text(data.get("children", []), depth)

        if block_type in ("child_page", "child_database"):
            return ""

        if block_type in ("image", "video", "audio"):
            return ""

        if block_type in ("file", "pdf"):
            return ""

        if block_type == "bookmark":
            caption = self._rich_text_to_plain(data.get("caption", []))
            return caption if caption else ""

        if block_type in ("embed", "link_preview"):
            return ""

        if block_type.startswith("heading_"):
            return self._rich_text_to_plain(data.get("rich_text", []))

        return ""

    def _section_children_to_text(self, children: list[dict], depth: int = 0) -> str:
        """children 블록 리스트를 섹션용 텍스트로 변환한다."""
        parts = []
        for child in children:
            text = self._section_block_to_text(child, depth)
            if text:
                parts.append(text)
        return "\n".join(parts)

    def _flatten_structural_blocks(self, blocks: list[dict]) -> list[dict]:
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
                result.extend(self._flatten_structural_blocks(children))
            elif block_type == "column_list":
                for col in data.get("children", []):
                    col_data = col.get("column", {})
                    result.extend(
                        self._flatten_structural_blocks(col_data.get("children", []))
                    )
            elif block_type == "column":
                result.extend(self._flatten_structural_blocks(data.get("children", [])))
            else:
                result.append(block)

        return result

    def _determine_content_type(self, block_types: list[str]) -> str:
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
