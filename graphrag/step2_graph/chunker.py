"""텍스트 청킹.

섹션 구조 기반 하이브리드 청킹(H2 그룹핑 + heading_path 컨텍스트 주입)과
플레인 텍스트용 recursive 청킹을 제공한다.
"""

from __future__ import annotations

import re

SEPARATORS = ["\n\n", "\n", ". ", "。", ", ", " "]

_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_HASHTAG_RE = re.compile(r"(?:^|\s)#([가-힣a-zA-Z]\S*)", re.MULTILINE)
_BRACKET_RE = re.compile(r"\[([^\[\]]{1,80})\]")
_BULLET_RE = re.compile(r"^(- )+", re.MULTILINE)
_NUMBERED_RE = re.compile(r"^(\d+\.\s)+", re.MULTILINE)
_HEADING_HASH_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"\s*```[^\n]*", re.MULTILINE)
_TODO_RE = re.compile(r"^- \[[ x]\]\s*", re.MULTILINE)

MIN_CONTENT_SIZE = 200
MIN_OUTPUT_CHUNK_SIZE = 100
GROUP_HEADING_LEVEL = 2


class TextChunker:
    """텍스트 청킹 엔진.

    섹션 기반 하이브리드 청킹과 recursive 청킹을 제공한다.
    chunk_size, overlap, min_chunk_size를 인스턴스 속성으로 관리한다.
    """

    def __init__(
        self,
        chunk_size: int = 2000,
        overlap: int = 200,
        min_chunk_size: int = 1000,
    ):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_chunk_size = min_chunk_size

    def clean_text(self, text: str) -> str:
        """청크 텍스트에서 잔여 Notion 마크업 기호를 정리한다.

        ContentParser에서 1차 제거하지만, 기존 JSON 호환 및 방어적 코딩을 위해
        chunker 단계에서도 2차 정리를 수행한다.
        """
        text = _MULTI_NEWLINE_RE.sub("\n\n", text)
        text = _CODE_FENCE_RE.sub("", text)
        text = self._clean_pipe_tables(text)
        text = _HEADING_HASH_RE.sub("", text)
        text = _TODO_RE.sub("", text)
        text = _BULLET_RE.sub("", text)
        text = _NUMBERED_RE.sub("", text)
        text = _HASHTAG_RE.sub("", text)
        text = _BRACKET_RE.sub(r"\1", text)
        text = _MULTI_NEWLINE_RE.sub("\n\n", text)
        return text.strip()

    def recursive_chunk(
        self,
        text: str,
        chunk_size: int | None = None,
        overlap: int | None = None,
        separators: list[str] | None = None,
    ) -> list[str]:
        """텍스트를 재귀적으로 분할한다.

        구분자 우선순위: 문단 > 줄바꿈 > 마침표 > 쉼표 > 공백.
        각 청크는 chunk_size 이하로 분할되며, overlap만큼 앞 청크와 겹친다.
        """
        cs = chunk_size if chunk_size is not None else self.chunk_size
        ov = overlap if overlap is not None else self.overlap

        if not text or not text.strip():
            return []

        if len(text) <= cs:
            return [text.strip()]

        if separators is None:
            separators = SEPARATORS

        for sep in separators:
            if sep in text:
                parts = text.split(sep)
                chunks: list[str] = []
                current = ""

                for part in parts:
                    candidate = f"{current}{sep}{part}" if current else part

                    if len(candidate) <= cs:
                        current = candidate
                    else:
                        if current:
                            chunks.append(current.strip())
                        current = part

                if current:
                    chunks.append(current.strip())

                # 오버랩: 앞 청크의 마지막 ov글자를 다음 청크 앞에 붙여
                # 청크 경계에서 문맥이 끊기는 것을 방지한다.
                if ov > 0 and len(chunks) > 1:
                    overlapped: list[str] = [chunks[0]]
                    for i in range(1, len(chunks)):
                        prev = chunks[i - 1]
                        overlap_text = prev[-ov:] if len(prev) > ov else prev
                        overlapped.append(f"{overlap_text} {chunks[i]}".strip())
                    chunks = overlapped

                return [c for c in chunks if c]

        chunks = []
        for i in range(0, len(text), cs - ov):
            chunk = text[i : i + cs]
            if chunk.strip():
                chunks.append(chunk.strip())
        return chunks

    def chunk_sections(
        self,
        sections: list[dict],
        page_title: str,
    ) -> list[dict]:
        """H2 그룹핑 기반 청킹.

        1단계: 같은 H2 아래의 H3+ 섹션들을 하나의 그룹으로 병합
        2단계: 그룹이 chunk_size 이하면 그대로 1청크, 초과하면 recursive 분할
        3단계: 인접한 소형 그룹을 min_chunk_size까지 병합
        """
        non_empty = [s for s in sections if s.get("text", "").strip()]
        if not non_empty:
            return []

        groups = self._group_sections_by_heading(sections)
        if not groups:
            return []

        chunks: list[dict] = []
        buf_texts: list[str] = []
        buf_paths: list[list[str]] = []
        buf_types: list[str] = []

        # 클로저: 외부 변수 buf_texts, buf_paths, buf_types, chunks를 캡처하여
        # 현재 버퍼에 쌓인 텍스트를 하나의 청크(또는 recursive 분할)로 확정한다.
        def _flush():
            if not buf_texts:
                return
            merged_text = "\n\n".join(buf_texts)
            all_paths = [p for p in buf_paths if p]
            heading_path = all_paths[0] if all_paths else []

            context_prefix = ""
            if all_paths:
                unique_labels = []
                for p in all_paths:
                    label = " > ".join(p)
                    if label not in unique_labels:
                        unique_labels.append(label)
                context_prefix = " > ".join(unique_labels) + "\n"

            content_type = buf_types[0] if buf_types else "text"
            full_text = context_prefix + merged_text

            if len(full_text) <= self.chunk_size:
                chunks.append({
                    "text": self.clean_text(full_text),
                    "heading_path": heading_path,
                    "content_type": content_type,
                    "page_title": page_title,
                })
            else:
                effective_size = max(self.chunk_size - len(context_prefix), MIN_CONTENT_SIZE)
                sub_chunks = self.recursive_chunk(
                    merged_text, chunk_size=effective_size, overlap=self.overlap,
                )
                for sc in sub_chunks:
                    chunks.append({
                        "text": self.clean_text(context_prefix + sc),
                        "heading_path": heading_path,
                        "content_type": content_type,
                        "page_title": page_title,
                    })

            buf_texts.clear()
            buf_paths.clear()
            buf_types.clear()

        for group in groups:
            text = group["text"]
            heading_path = group.get("heading_path", [])
            content_type = group.get("content_type", "text")

            current_len = sum(len(t) for t in buf_texts)
            new_len = current_len + len(text)

            if current_len > 0 and new_len > self.chunk_size:
                _flush()

            buf_texts.append(text)
            buf_paths.append(heading_path)
            buf_types.append(content_type)

            if sum(len(t) for t in buf_texts) >= self.min_chunk_size:
                _flush()

        _flush()

        if len(chunks) > 1 and len(chunks[-1]["text"]) < self.min_chunk_size // 2:
            tail = chunks.pop()
            prev = chunks[-1]
            merged = prev["text"] + "\n\n" + tail["text"]
            if len(merged) <= self.chunk_size * 1.5:
                prev["text"] = merged
            else:
                chunks.append(tail)

        return [c for c in chunks if len(c.get("text", "")) >= MIN_OUTPUT_CHUNK_SIZE]

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _clean_pipe_tables(self, text: str) -> str:
        """파이프(|) 테이블 행을 평문으로 변환한다.

        멀티라인 셀을 포함한 다양한 파이프 패턴을 처리한다.
        """
        lines = text.split("\n")
        result: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped.startswith("|"):
                if stripped.endswith("|"):
                    result.append(stripped.rstrip("| ").rstrip())
                else:
                    result.append(line)
                continue
            inner = stripped.strip("|").strip()
            if not inner:
                continue
            cells = [c.strip() for c in inner.split("|") if c.strip()]
            if not cells:
                continue
            if len(cells) == 2:
                result.append(f"{cells[0]}: {cells[1]}")
            else:
                result.append(", ".join(cells))
        return "\n".join(result)

    def _group_sections_by_heading(
        self,
        sections: list[dict],
        level: int = GROUP_HEADING_LEVEL,
    ) -> list[dict]:
        """같은 상위 헤딩(level 이하) 아래의 하위 섹션들을 하나의 그룹으로 병합한다.

        H2 기준이면 H2 하나 + 그 아래 H3들이 하나의 그룹이 된다.
        하위 헤딩 텍스트는 소제목으로 본문에 인라인 삽입하여 컨텍스트를 보존한다.
        """
        groups: list[dict] = []
        current_texts: list[str] = []
        current_path: list[str] = []
        current_types: list[str] = []

        # 클로저: current_texts, current_path, current_types를 캡처하여
        # 같은 H2 아래에 모인 하위 섹션들을 하나의 그룹으로 확정한다.
        def _flush_group():
            if not current_texts:
                return
            merged = "\n\n".join(t for t in current_texts if t)
            if not merged.strip():
                return
            type_set = set(current_types)
            if len(type_set) > 1:
                ctype = "mixed"
            else:
                ctype = current_types[0] if current_types else "text"
            groups.append({
                "text": merged,
                "heading_path": list(current_path),
                "content_type": ctype,
            })

        for sec in sections:
            sec_text = sec.get("text", "").strip()
            sec_path = sec.get("heading_path", [])
            sec_level = sec.get("heading_level", 0)
            sec_type = sec.get("content_type", "text")

            is_top_heading = 0 < sec_level <= level

            if is_top_heading and current_texts:
                _flush_group()
                current_texts.clear()
                current_path.clear()
                current_types.clear()

            if not current_path and sec_path:
                current_path = sec_path[:level] if len(sec_path) > level else list(sec_path)
            elif not current_path:
                current_path = []

            if sec_level > level and sec_path:
                sub_heading = sec_path[-1] if sec_path else ""
                if sub_heading:
                    current_texts.append(sub_heading)

            if sec_text:
                current_texts.append(sec_text)
                current_types.append(sec_type)

        _flush_group()
        return groups
