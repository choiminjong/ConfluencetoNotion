"""텍스트 청킹.

섹션 구조 기반 하이브리드 청킹(인접 소형 섹션 병합 + heading_path 컨텍스트 주입)과
플레인 텍스트용 recursive 청킹을 제공한다.
"""

from __future__ import annotations

SEPARATORS = ["\n\n", "\n", ". ", "。", ", ", " "]

MIN_CONTENT_SIZE = 200
DEFAULT_MIN_CHUNK_SIZE = 500


def recursive_chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 100,
    separators: list[str] | None = None,
) -> list[str]:
    """텍스트를 재귀적으로 분할한다.

    구분자 우선순위: 문단 > 줄바꿈 > 마침표 > 쉼표 > 공백.
    각 청크는 chunk_size 이하로 분할되며, overlap만큼 앞 청크와 겹친다.
    """
    if not text or not text.strip():
        return []

    if len(text) <= chunk_size:
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

                if len(candidate) <= chunk_size:
                    current = candidate
                else:
                    if current:
                        chunks.append(current.strip())
                    current = part

            if current:
                chunks.append(current.strip())

            if overlap > 0 and len(chunks) > 1:
                overlapped: list[str] = [chunks[0]]
                for i in range(1, len(chunks)):
                    prev = chunks[i - 1]
                    overlap_text = prev[-overlap:] if len(prev) > overlap else prev
                    overlapped.append(f"{overlap_text} {chunks[i]}".strip())
                chunks = overlapped

            return [c for c in chunks if c]

    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunk = text[i : i + chunk_size]
        if chunk.strip():
            chunks.append(chunk.strip())
    return chunks


def chunk_by_sections(
    sections: list[dict],
    page_title: str,
    chunk_size: int = 1000,
    overlap: int = 100,
    min_chunk_size: int = DEFAULT_MIN_CHUNK_SIZE,
) -> list[dict]:
    """섹션 구조 기반 하이브리드 청킹.

    인접한 소형 섹션을 min_chunk_size에 도달할 때까지 병합하여
    청크의 최소 품질을 보장한다. 병합된 청크에는 포함된 모든 섹션의
    heading_path가 보존된다.

    chunk_size보다 큰 단일 섹션은 recursive_chunk_text로 분할한다.
    """
    non_empty = [
        s for s in sections
        if s.get("text", "").strip()
    ]
    if not non_empty:
        return []

    buf_texts: list[str] = []
    buf_paths: list[list[str]] = []
    buf_types: list[str] = []
    chunks: list[dict] = []

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
            context_prefix = "[" + " | ".join(unique_labels) + "]\n"

        content_type = buf_types[0] if buf_types else "text"
        full_text = context_prefix + merged_text

        if len(full_text) <= chunk_size:
            chunks.append({
                "text": full_text,
                "heading_path": heading_path,
                "content_type": content_type,
                "page_title": page_title,
            })
        else:
            effective_size = max(chunk_size - len(context_prefix), MIN_CONTENT_SIZE)
            sub_chunks = recursive_chunk_text(
                merged_text, chunk_size=effective_size, overlap=overlap,
            )
            for sc in sub_chunks:
                chunks.append({
                    "text": context_prefix + sc,
                    "heading_path": heading_path,
                    "content_type": content_type,
                    "page_title": page_title,
                })

        buf_texts.clear()
        buf_paths.clear()
        buf_types.clear()

    for section in non_empty:
        text = section["text"].strip()
        heading_path = section.get("heading_path", [])
        content_type = section.get("content_type", "text")

        current_len = sum(len(t) for t in buf_texts)
        new_len = current_len + len(text)

        if current_len > 0 and new_len > chunk_size:
            _flush()

        buf_texts.append(text)
        buf_paths.append(heading_path)
        buf_types.append(content_type)

        if sum(len(t) for t in buf_texts) >= min_chunk_size:
            _flush()

    _flush()

    if len(chunks) > 1 and len(chunks[-1]["text"]) < min_chunk_size // 2:
        tail = chunks.pop()
        prev = chunks[-1]
        merged = prev["text"] + "\n\n" + tail["text"]
        if len(merged) <= chunk_size * 1.2:
            prev["text"] = merged
        else:
            chunks.append(tail)

    return chunks
