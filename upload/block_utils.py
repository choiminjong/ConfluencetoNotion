"""Notion 블록 데이터 변환·분할 유틸리티.

Notion API와 무관한 순수 데이터 처리 함수만 포함한다.
- 블록 내 이미지/비디오 URL → file_upload 참조 교체
- rich_text UTF-16 기준 자동 분할 (Notion API 2,000자 제한 대응)
"""

import copy
from urllib.parse import unquote

MAX_TEXT_LENGTH = 2000
MAX_RICH_TEXT_ARRAY = 100


# ------------------------------------------------------------------
# Block Transform
# ------------------------------------------------------------------


_MEDIA_TYPES = frozenset({"image", "video"})


def transform_blocks(blocks: list[dict], media_map: dict[str, str]) -> list[dict]:
    """블록 내 로컬 이미지/비디오 URL 을 file_upload 참조로 교체한다."""
    transformed = copy.deepcopy(blocks)
    stack = list(transformed)

    while stack:
        block = stack.pop()
        block_type = block.get("type", "")

        if block_type in _MEDIA_TYPES:
            media_data = block.get(block_type, {})
            if media_data.get("type") == "external":
                url = media_data.get("external", {}).get("url", "")
                decoded_url = unquote(url) if url else ""
                lookup = decoded_url if decoded_url in media_map else url
                if url and not url.startswith("http") and lookup in media_map:
                    caption = media_data.get("caption")
                    block[block_type] = {
                        "type": "file_upload",
                        "file_upload": {"id": media_map[lookup]},
                    }
                    if caption:
                        block[block_type]["caption"] = caption

        children = block.get(block_type, {}).get("children", [])
        if children:
            stack.extend(children)

    return transformed


# ------------------------------------------------------------------
# Block Sanitize (Notion API rich_text 제한 대응)
# ------------------------------------------------------------------


def utf16_len(text: str) -> int:
    """Notion API(JavaScript)와 동일한 UTF-16 코드 유닛 수를 반환한다."""
    return len(text.encode("utf-16-le")) // 2


def split_text(text: str, limit: int = MAX_TEXT_LENGTH) -> list[str]:
    """긴 텍스트를 limit 이하 청크로 분할한다.

    Notion API는 UTF-16 코드 유닛 기준으로 길이를 측정하므로
    BMP 밖 문자(이모지 등)를 정확히 고려한다.
    분할 위치 우선순위: 줄바꿈 > 공백 > 강제 절단.
    """
    chunks: list[str] = []
    while utf16_len(text) > limit:
        surplus = utf16_len(text[:limit]) - limit
        cut = limit - max(surplus, 0)
        while cut > 0 and utf16_len(text[:cut]) > limit:
            cut -= 1
        best = text.rfind("\n", 0, cut + 1)
        if best <= 0:
            best = text.rfind(" ", 0, cut + 1)
        if best <= 0:
            best = cut
        chunks.append(text[:best])
        text = text[best:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


def split_rich_text(
    rich_text_list: list[dict],
    limit: int = MAX_TEXT_LENGTH,
    max_array: int = MAX_RICH_TEXT_ARRAY,
) -> list[dict]:
    """rich_text 배열의 모든 text.content 를 limit 이하로 분할한다.

    annotations(bold, italic 등)은 원본에서 복사하여 유지한다.
    """
    result: list[dict] = []
    for item in rich_text_list:
        content = item.get("text", {}).get("content", "")
        if utf16_len(content) <= limit:
            result.append(item)
            continue
        for chunk in split_text(content, limit):
            new_item = copy.deepcopy(item)
            new_item["text"]["content"] = chunk
            result.append(new_item)
    return result[:max_array]


def sanitize_blocks(
    blocks: list[dict],
    limit: int = MAX_TEXT_LENGTH,
    max_array: int = MAX_RICH_TEXT_ARRAY,
) -> list[dict]:
    """모든 블록의 rich_text 를 Notion API 제한에 맞게 분할한다."""
    for block in blocks:
        block_type = block.get("type", "")
        block_data = block.get(block_type, {})
        if "rich_text" in block_data:
            block_data["rich_text"] = split_rich_text(block_data["rich_text"], limit, max_array)
        if "children" in block_data:
            sanitize_blocks(block_data["children"], limit, max_array)
        if block_type == "table_row" and "cells" in block_data:
            block_data["cells"] = [
                split_rich_text(cell, limit, max_array) for cell in block_data["cells"]
            ]
    return blocks


# ------------------------------------------------------------------
# Invalid Media Filter (Notion API "Invalid image/video url" 방어)
# ------------------------------------------------------------------

def filter_invalid_media(blocks: list[dict]) -> list[dict]:
    """유효하지 않은 external 이미지/비디오 블록을 제거한다.

    file_upload로 변환되지 않은 non-HTTP URL은 Notion API에서
    "Invalid image url" 에러를 유발하므로 사전에 제거한다.
    """
    result: list[dict] = []
    for block in blocks:
        block_type = block.get("type", "")
        if block_type in _MEDIA_TYPES:
            media_data = block.get(block_type, {})
            if media_data.get("type") == "external":
                url = media_data.get("external", {}).get("url", "")
                if url and not url.startswith("http"):
                    print(f"  WARN: 잘못된 {block_type} URL 제거: {url}")
                    continue
        children = block.get(block_type, {}).get("children", [])
        if children:
            block[block_type]["children"] = filter_invalid_media(children)
        result.append(block)
    return result
