"""Recursive 텍스트 청킹.

긴 텍스트를 의미 단위(문단, 문장, 단어)로 나누어 지정된 크기의 청크로 분할한다.
"""

from __future__ import annotations

SEPARATORS = ["\n\n", "\n", ". ", "。", ", ", " "]


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
