"""confluence-markdown-exporter 패키지 Converter 오버라이딩 모음.

패키지 원본은 수정하지 않고, Converter 메서드를 외부에서 교체한다.
새 매크로/변환 로직이 필요하면 이 파일에 추가한다.
"""

import re
from typing import cast
from urllib.parse import unquote

from bs4 import Tag
from tabulate import tabulate

from confluence_markdown_exporter.utils.table_converter import _get_int_attr


# ============================================================
# Table 오버라이드 — rowspan/colspan 셀 내용 복제
# ============================================================

def _pad_with_content(rows: list[list[Tag]]) -> list[list[Tag]]:
    """rowspan/colspan 셀을 빈 셀 대신 원본 셀 내용으로 복제한다.

    패키지 원본 pad()는 병합 영역을 빈 <td>로 채우지만,
    Notion 테이블에서는 병합을 지원하지 않으므로 원본 내용을 반복하는 것이 가독성에 유리하다.
    """
    padded: list[list[Tag]] = []
    occ: dict[tuple[int, int], Tag] = {}
    for r, row in enumerate(rows):
        if not row:
            continue
        cur: list[Tag] = []
        c = 0
        for cell in row:
            while (r, c) in occ:
                cur.append(occ.pop((r, c)))
                c += 1
            rs = _get_int_attr(cell, "rowspan", "1")
            cs = _get_int_attr(cell, "colspan", "1")
            cur.append(cell)
            if cs > 1:
                cur.extend(cell for _ in range(1, cs))
            for i in range(rs):
                for j in range(cs):
                    if i or j:
                        occ[(r + i, c + j)] = cell
            c += cs
        while (r, c) in occ:
            cur.append(occ.pop((r, c)))
            c += 1
        padded.append(cur)
    return padded


# ============================================================
# Table 오버라이드
# ============================================================

CONFLUENCE_EMOTICON_MAP: dict[str, str] = {
    "check.svg": "✅",
    "error.svg": "❌",
    "warning.svg": "⚠️",
    "information.svg": "ℹ️",
    "smile.svg": "😀",
    "sad.svg": "😢",
    "cheeky.svg": "😛",
    "laugh.svg": "😂",
    "wink.svg": "😉",
    "thumbs_up.svg": "👍",
    "thumbs_down.svg": "👎",
    "lightbulb_on.svg": "💡",
    "lightbulb.svg": "💡",
    "star_yellow.svg": "⭐",
    "star_red.svg": "⭐",
    "star_green.svg": "⭐",
    "star_blue.svg": "⭐",
    "heart.svg": "❤️",
    "broken_heart.svg": "💔",
    "question.svg": "❓",
    "forbidden.svg": "🚫",
    "add.svg": "➕",
    "binoculars.svg": "🔍",
}

EMOTICON_FALLBACK = "▪️"


class TableOverride:
    """테이블 HTML -> Markdown 변환 오버라이드.

    중첩 테이블은 HTML 유지, 이미지는 텍스트 링크로 대체 후 하단에 배치한다.
    """

    BLOCK_TAGS = frozenset({
        "p", "h1", "h2", "h3", "h4", "h5", "h6",
        "div", "ul", "ol", "blockquote", "pre",
    })

    def __init__(self, converter, el):
        self.converter = converter
        self.el = el

    def extract_images(self) -> list[str]:
        """이미지를 텍스트 링크로 대체하고, 하단 배치용 마크다운 목록을 반환한다."""
        extracted: list[str] = []
        for img in self.el.find_all("img"):
            src = img.get("data-image-src") or img.get("src") or ""
            alt = img.get("alt") or ""

            if "/images/icons/emoticons/" in src:
                filename = src.rsplit("/", 1)[-1]
                emoji = CONFLUENCE_EMOTICON_MAP.get(filename)
                if emoji is None:
                    print(f"  WARN: 미지원 이모티콘 '{filename}' → {EMOTICON_FALLBACK}")
                    emoji = EMOTICON_FALLBACK
                img.replace_with(emoji)
                continue

            raw_name = unquote(src.rsplit("/", 1)[-1]) if src else alt or "image"
            filename = raw_name.split("?")[0]
            img.replace_with(f"📎 {filename}")
            extracted.append(f"**📎 {filename}**\n\n![{alt}]({src})")
        return extracted

    def cell_to_text(self, cell: Tag) -> str:
        """단일 셀을 마크다운 텍스트로 변환한다."""
        block_children = [
            child for child in cell.children
            if isinstance(child, Tag) and child.name in self.BLOCK_TAGS
        ]
        if len(block_children) > 1:
            parts = []
            for child in block_children:
                md = self.converter.convert(str(child)).strip()
                md = re.sub(r"^#{1,6}\s+", "", md)
                md = md.replace("\n", "<br>")
                if md:
                    parts.append(md)
            result = "<br>".join(parts)
        else:
            inner_html = cell.decode_contents()
            result = self.converter.convert(inner_html).strip()
            result = re.sub(r"^#{1,6}\s+", "", result)
            result = re.sub(r"\n+", "<br>", result)
        result = result.replace("****", "**<br>**")
        return result

    @staticmethod
    def _display_width(text: str) -> int:
        """비례 폰트 근사 표시 폭을 반환한다. CJK/한글은 2, 나머지는 1."""
        import unicodedata
        w = 0
        for ch in text:
            ea = unicodedata.east_asian_width(ch)
            w += 2 if ea in ("W", "F") else 1
        return w

    def _inner_table_to_inline(self, table_tag: Tag) -> str:
        """내부 테이블을 [행] 형태의 정렬된 인라인 텍스트로 변환한다.

        Notion 테이블 셀은 중첩 테이블을 지원하지 않으므로,
        내부 테이블의 행/열 구조를 텍스트로 근사 표현한다.
        구분자로 │(U+2502)를 사용하여 마크다운 파이프 테이블과 충돌을 방지한다.
        각 열의 최대 폭에 맞춰 공백 패딩으로 정렬을 시도한다.
        """
        rows = table_tag.find_all("tr")
        if not rows:
            return ""
        cells_per_row = [
            [c.get_text(" ", strip=True).replace("|", "\u2502") for c in tr.find_all(["td", "th"])]
            for tr in rows
        ]
        cells_per_row = [r for r in cells_per_row if any(r)]
        if not cells_per_row:
            return ""

        max_cols = max(len(r) for r in cells_per_row)
        col_widths = [0] * max_cols
        for r in cells_per_row:
            for ci, cell in enumerate(r):
                col_widths[ci] = max(col_widths[ci], self._display_width(cell))

        lines = []
        for r in cells_per_row:
            padded = []
            for ci in range(max_cols):
                cell = r[ci] if ci < len(r) else ""
                pad = col_widths[ci] - self._display_width(cell)
                padded.append(cell + " " * max(pad, 0))
            lines.append("[ " + " \u2502 ".join(padded) + " ]")
        return "<br>".join(lines)

    def convert(self) -> str:
        """테이블 전체를 마크다운으로 변환한다."""
        for inner in self.el.find_all("table", recursive=True):
            if inner is self.el:
                continue
            inner.replace_with(self._inner_table_to_inline(inner))

        extracted_images = self.extract_images()

        rows = [
            cast("list[Tag]", tr.find_all(["td", "th"]))
            for tr in cast("list[Tag]", self.el.find_all("tr"))
            if tr
        ]
        if not rows:
            return ""

        padded_rows = _pad_with_content(rows)
        converted = [[self.cell_to_text(cell) for cell in row] for row in padded_rows]

        has_header = all(cell.name == "th" for cell in rows[0])
        if has_header:
            result = "\n\n" + tabulate(converted[1:], headers=converted[0], tablefmt="pipe") + "\n\n"
        else:
            result = "\n\n" + tabulate(converted, headers=[""] * len(converted[0]), tablefmt="pipe") + "\n\n"

        if extracted_images:
            result += "\n\n".join(extracted_images) + "\n\n"

        return result


def _convert_table(self, el, text, parent_tags):
    return TableOverride(self, el).convert()


# ============================================================
# Tabs 매크로 오버라이드 (ui-tabs / ui-tab)
# ============================================================

def _convert_tabs(self, el, text, parent_tags):
    """ui-tabs 컨테이너 → 각 탭을 details/summary 블록으로 변환.

    전체 테이블 콘텐츠 대신 탭 제목과 플레이스홀더만 생성한다.
    실제 하위 페이지 이름은 export_page() 후처리에서 Confluence API로 주입한다.
    """
    parts = []
    for tab in el.find_all("div", {"data-macro-name": "ui-tab"}, recursive=False):
        title = tab.get("data-name", "Tab")
        parts.append(
            f"\n<details>\n<summary>{title}</summary>\n\n"
            f"<!-- TAB_CHILDREN:{title} -->\n\n</details>\n\n"
        )
    return "\n".join(parts)


# ============================================================
# tabs-group / tab-pane 매크로 오버라이드
# ============================================================

def _convert_tabs_group(self, el, text, parent_tags):
    """tabs-group 컨테이너 → 각 tab-pane을 details/summary 블록으로 변환.

    ui-tabs와 달리 실제 콘텐츠를 toggle 안에 포함한다.
    pane.decode_contents()로 내부 HTML을 새로 변환하여 재귀 방지.
    """
    tabs_menu = el.find("ul", class_="tabs-menu")
    tab_titles = []
    if tabs_menu:
        for li in tabs_menu.find_all("li", recursive=False):
            a_tag = li.find("a")
            title = a_tag.get_text(strip=True) if a_tag else li.get_text(strip=True)
            tab_titles.append(title or "Tab")

    panes = el.find_all("div", {"data-macro-name": "tab-pane"})
    parts = []
    for i, pane in enumerate(panes):
        title = pane.get("data-name") or (tab_titles[i] if i < len(tab_titles) else f"Tab {i+1}")
        raw_html = pane.decode_contents()
        content = self.convert(raw_html).strip()
        parts.append(
            f"\n<details>\n<summary>{title}</summary>\n\n"
            f"{content}\n\n</details>\n"
        )
    return "\n".join(parts)


def _noop(self, el, text, parent_tags):
    """상위 매크로에서 이미 처리된 하위 요소를 무시한다."""
    return ""


# ============================================================
# horizontal-nav 매크로 오버라이드
# ============================================================

def _convert_horizontal_nav_group(self, el, text, parent_tags):
    """horizontal-nav-group → 각 horizontal-nav-item을 토글로 변환.

    UL/LI에서 탭 라벨을 추출하고, 각 item의 콘텐츠를 details/summary로 감싼다.
    """
    nav_items = el.find_all("div", {"data-macro-name": "horizontal-nav-item"})
    if not nav_items:
        return text or ""

    tab_labels = []
    for a_tag in el.find_all("a", recursive=True):
        if a_tag.find_parent("div", {"data-macro-name": "horizontal-nav-item"}):
            continue
        label = a_tag.get_text(strip=True)
        if label:
            tab_labels.append(label)

    parts = []
    for i, item in enumerate(nav_items):
        title = tab_labels[i] if i < len(tab_labels) else f"Tab {i+1}"
        content = self.convert(item.decode_contents()).strip()
        if content:
            parts.append(
                f"\n<details>\n<summary>{title}</summary>\n\n"
                f"{content}\n\n</details>\n"
            )
    return "\n".join(parts)


def _convert_horizontal_nav_item(self, el, text, parent_tags):
    """horizontal-nav-group에서 일괄 처리하므로 개별 item은 무시."""
    return ""


# ============================================================
# ui-expand 매크로 오버라이드
# ============================================================

def _convert_ui_expand(self, el, text, parent_tags):
    """ui-expand (펼치기/접기) → details/summary 블록으로 변환.

    text 파라미터에 자식 요소의 변환 결과가 이미 포함되어 있다.
    self.process_tag(el)를 호출하면 convert_div → _convert_ui_expand 무한 재귀 발생.
    """
    title = el.get("data-title", "펼치기")
    content = text.strip() if text else ""
    return f"\n<details>\n<summary>{title}</summary>\n\n{content}\n\n</details>\n"


# ============================================================
# Page Properties (details) 매크로 오버라이드
# ============================================================

def _convert_page_properties(self, el, text, parent_tags):
    """details (Page Properties) 매크로 → 마크다운 테이블로 본문에 렌더링.

    원본 패키지는 YAML frontmatter로 추출하지만 sanitize_key()가
    한글 키를 지원하지 않아 데이터가 유실된다.
    내부 <table>은 이미 TableOverride가 처리했으므로 그 결과(text)를 통과시킨다.
    """
    return text.strip() if text else ""


_DIV_MACRO_OVERRIDES = {
    "ui-tabs": _convert_tabs,
    "tabs-group": _convert_tabs_group,
    "tab-pane": _noop,
    "horizontal-nav-group": _convert_horizontal_nav_group,
    "horizontal-nav-item": _convert_horizontal_nav_item,
    "ui-expand": _convert_ui_expand,
    "details": _convert_page_properties,
}

_KNOWN_PACKAGE_MACROS = frozenset({
    "panel", "info", "note", "tip", "warning",
    "details", "drawio", "plantuml", "scroll-ignore",
    "toc", "jira", "attachments",
})

unsupported_macros: list[dict] = []


def reset_unsupported_macros() -> None:
    """수집된 미지원 매크로 리스트를 초기화한다."""
    unsupported_macros.clear()


def _wrap_convert_div(original_fn):
    """원본 convert_div 를 래핑하여 커스텀 매크로 핸들러를 먼저 가로챈다.

    오버라이드 / 패키지 핸들러 모두에 없는 매크로는 미지원으로 기록한다.
    """
    def wrapper(self, el, text, parent_tags):
        if el.has_attr("data-macro-name"):
            macro_name = str(el["data-macro-name"])
            if macro_name in _DIV_MACRO_OVERRIDES:
                return _DIV_MACRO_OVERRIDES[macro_name](self, el, text, parent_tags)
            if macro_name not in _KNOWN_PACKAGE_MACROS:
                page_id = getattr(self, "_current_page_id", "unknown")
                print(f"  WARN: 미지원 매크로 '{macro_name}' (page: {page_id})")
                unsupported_macros.append({
                    "page_id": str(page_id),
                    "macro_name": macro_name,
                })
        return original_fn(self, el, text, parent_tags)
    return wrapper


# ============================================================
# columnLayout 오버라이드
# ============================================================

def _convert_column_layout(self, el, text, parent_tags):
    """다단 레이아웃 → 순차 배치. Notion은 다단 레이아웃을 지원하지 않는다."""
    cells = el.find_all("div", {"class": "cell"}, recursive=False)
    parts = []
    for cell in cells:
        inner = cell.find("div", class_="innerCell")
        target = inner if inner else cell
        md = self.process_tag(target, parent_tags).strip()
        if md:
            parts.append(md)
    return "\n\n---\n\n".join(parts)


# ============================================================
# 일괄 적용
# ============================================================

_RE_EMOTICON_IMG = re.compile(
    r"!\[[^\]]*\]\([^)]*?/images/icons/emoticons/([^/)]+?)\)",
)


def replace_emoticon_markdown(md: str) -> str:
    """마크다운 본문에서 Confluence 이모티콘 SVG 이미지 참조를 텍스트 이모지로 치환한다."""
    def _replacer(m: re.Match) -> str:
        filename = m.group(1)
        emoji = CONFLUENCE_EMOTICON_MAP.get(filename)
        if emoji is None:
            print(f"  WARN: 미지원 이모티콘 '{filename}' → {EMOTICON_FALLBACK}")
            emoji = EMOTICON_FALLBACK
        return emoji
    return _RE_EMOTICON_IMG.sub(_replacer, md)


def apply_overrides(converter_cls) -> None:
    """Converter 클래스에 모든 오버라이딩을 적용한다."""
    converter_cls.convert_table = _convert_table
    converter_cls.convert_div = _wrap_convert_div(converter_cls.convert_div)
    converter_cls.convert_column_layout = _convert_column_layout
