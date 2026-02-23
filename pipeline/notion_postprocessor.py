"""Notion JSON 후처리 유틸리티.

notion-markdown 패키지가 생성한 블록 JSON 을 Notion API 에 맞게 보정한다.
모든 함수는 stateless 순수 함수이다.
"""

import os
import re
from urllib.parse import unquote

from pipeline.md_preprocessor import _VIDEO_EXTENSIONS


# ------------------------------------------------------------------
# 컴파일된 정규식 패턴
# ------------------------------------------------------------------

_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

_MD_TOKEN_RE = re.compile(
    r"(\*\*\[([^\]]+)\]\(([^)]+)\)\*\*)"
    r"|(\*\*(.+?)\*\*)"
    r"|(\[([^\]]+)\]\(([^)]+)\))"
    r"|(!\[([^\]]*)\]\(([^)]+)\))"
)


# ------------------------------------------------------------------
# 개별 후처리 함수
# ------------------------------------------------------------------

def parse_callout_content(text: str) -> tuple[list[dict], list[dict]]:
    """콜아웃 텍스트를 파싱하여 (rich_text, children_image_blocks) 를 반환한다.

    bold, 링크, bold+링크, 이미지를 모두 처리한다.
    """
    rich_text: list[dict] = []
    image_children: list[dict] = []
    last = 0

    for m in _MD_TOKEN_RE.finditer(text):
        if m.start() > last:
            plain = text[last:m.start()]
            if plain:
                rich_text.append({"type": "text", "text": {"content": plain}})

        if m.group(1):
            link_text = m.group(2)
            link_url = m.group(3)
            rich_text.append({
                "type": "text",
                "text": {"content": link_text, "link": {"url": link_url}},
                "annotations": {"bold": True},
            })
        elif m.group(4):
            bold_text = m.group(5)
            rich_text.append({
                "type": "text",
                "text": {"content": bold_text},
                "annotations": {"bold": True},
            })
        elif m.group(6):
            link_text = m.group(7)
            link_url = m.group(8)
            rich_text.append({
                "type": "text",
                "text": {"content": link_text, "link": {"url": link_url}},
            })
        elif m.group(9):
            img_url = m.group(11)
            image_children.append({
                "type": "image",
                "image": {"type": "external", "external": {"url": img_url}},
            })

        last = m.end()

    if last < len(text):
        tail = text[last:]
        if tail:
            rich_text.append({"type": "text", "text": {"content": tail}})

    if not rich_text:
        rich_text = [{"type": "text", "text": {"content": text}}]

    return rich_text, image_children


def fix_callout_content(blocks: list[dict]) -> list[dict]:
    """callout 블록의 rich_text 에서 bold, 링크, 이미지를 파싱한다.

    - **bold** -> annotation
    - [text](url) -> Notion link
    - ![](img) -> children image block
    - {{BR}} -> 줄바꿈
    """
    for block in blocks:
        if block.get("type") != "callout":
            continue
        rt = block.get("callout", {}).get("rich_text", [])
        if not rt:
            continue

        full_text = "".join(seg.get("text", {}).get("content", "") for seg in rt)
        full_text = full_text.replace("{{BR}}", "\n")

        needs_parse = any(marker in full_text for marker in ("**", "[", "!["))
        text_changed = full_text != rt[0].get("text", {}).get("content", "")

        if needs_parse:
            new_rt, image_children = parse_callout_content(full_text)
            block["callout"]["rich_text"] = new_rt
            if image_children:
                existing = block["callout"].get("children", [])
                block["callout"]["children"] = image_children + existing
        elif text_changed:
            block["callout"]["rich_text"] = [{"type": "text", "text": {"content": full_text}}]

    return blocks


def extract_images_from_text_blocks(blocks: list[dict]) -> list[dict]:
    """토글/콜아웃 children 의 paragraph rich_text 에서 인라인 이미지를 추출하여 별도 블록으로 분리한다."""
    for block in blocks:
        block_type = block.get("type", "")
        if block_type not in ("toggle", "callout"):
            continue
        block_data = block.get(block_type, {})
        children = block_data.get("children", [])
        if not children:
            continue

        new_children: list[dict] = []
        for child in children:
            if child.get("type") != "paragraph":
                new_children.append(child)
                continue

            rt = child.get("paragraph", {}).get("rich_text", [])
            if not rt:
                new_children.append(child)
                continue

            full = "".join(seg.get("text", {}).get("content", "") for seg in rt)
            if "![" not in full:
                new_children.append(child)
                continue

            parts = _MD_IMAGE_RE.split(full)
            i = 0
            while i < len(parts):
                if i + 2 < len(parts):
                    text_before = parts[i]
                    _ = parts[i + 1]
                    img_url = parts[i + 2]
                    if text_before.strip():
                        new_children.append({
                            "type": "paragraph",
                            "paragraph": {"rich_text": [{"type": "text", "text": {"content": text_before.strip()}}]},
                        })
                    new_children.append({
                        "type": "image",
                        "image": {"type": "external", "external": {"url": img_url}},
                    })
                    i += 3
                else:
                    leftover = parts[i]
                    if leftover.strip():
                        new_children.append({
                            "type": "paragraph",
                            "paragraph": {"rich_text": [{"type": "text", "text": {"content": leftover.strip()}}]},
                        })
                    i += 1

        block_data["children"] = new_children

    return blocks


def fix_toggle_children(blocks: list[dict]) -> list[dict]:
    """토글 블록의 한 줄 '- item' 텍스트를 bulleted_list_item 블록 목록으로 변환한다."""
    for block in blocks:
        if block.get("type") != "toggle":
            continue
        children = block.get("toggle", {}).get("children", [])
        if len(children) != 1 or children[0].get("type") != "paragraph":
            continue

        content = children[0]["paragraph"]["rich_text"][0]["text"]["content"]
        if not content.lstrip().startswith("- "):
            continue

        items = [s.strip() for s in re.split(r"\s*-\s+", content) if s.strip()]
        block["toggle"]["children"] = [
            {
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": item}}]
                },
            }
            for item in items
        ]
    return blocks


def convert_image_to_video(blocks: list[dict]) -> list[dict]:
    """URL 확장자가 비디오인 image 블록을 video 블록으로 변환한다."""
    for i, block in enumerate(blocks):
        block_type = block.get("type", "")

        if block_type == "image":
            url = block.get("image", {}).get("external", {}).get("url", "")
            ext = os.path.splitext(url)[1].lower()
            if ext in _VIDEO_EXTENSIONS:
                blocks[i] = {
                    "type": "video",
                    "video": block["image"],
                }

        block_data = block.get(block_type, {})
        children = block_data.get("children", [])
        if children:
            convert_image_to_video(children)

    return blocks


def extract_local_media(blocks: list[dict]) -> list[str]:
    """Notion 블록 목록에서 로컬 이미지/비디오 파일명을 재귀적으로 추출한다."""
    media: list[str] = []
    for block in blocks:
        block_type = block.get("type", "")
        if block_type in ("image", "video"):
            block_data = block.get(block_type, {})
            url = block_data.get("external", {}).get("url", "")
            if url and not url.startswith("http"):
                media.append(unquote(url))

        block_data = block.get(block_type, {})
        children = block_data.get("children", [])
        if children:
            media.extend(extract_local_media(children))

    return media



# ------------------------------------------------------------------
# 파이프라인 (위 함수들을 순서대로 호출)
# ------------------------------------------------------------------

def postprocess(blocks: list[dict]) -> list[dict]:
    """Notion JSON 블록 목록을 후처리하여 API 호환성을 보정한다."""
    blocks = fix_callout_content(blocks)
    blocks = fix_toggle_children(blocks)
    blocks = extract_images_from_text_blocks(blocks)
    blocks = convert_image_to_video(blocks)
    return blocks
