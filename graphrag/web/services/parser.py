"""응답 파싱, Cypher 캡처 유틸리티.

GraphRAG 응답에서 노드/엣지 ID를 추출하고, Text2Cypher 로그에서 Cypher를 캡처한다.
"""

from __future__ import annotations

import logging
import re


class CypherCaptureHandler(logging.Handler):
    """text2cypher 로거에서 생성된 Cypher 쿼리를 캡처한다."""

    def __init__(self):
        super().__init__()
        self.last_cypher = ""

    def emit(self, record):
        msg = record.getMessage()
        if "Cypher query:" in msg:
            parts = msg.split("Cypher query:", 1)
            if len(parts) > 1:
                self.last_cypher = parts[1].strip()

    def pop(self) -> str:
        q = self.last_cypher
        self.last_cypher = ""
        return q


cypher_capture = CypherCaptureHandler()
t2c_logger = logging.getLogger("neo4j_graphrag.retrievers.text2cypher")
t2c_logger.addHandler(cypher_capture)
t2c_logger.setLevel(logging.DEBUG)


def extract_nodes_from_answer(answer: str) -> tuple[list[str], list[str]]:
    """답변 텍스트에서 URL과 제목 패턴으로 노드를 추출한다."""
    nodes: list[str] = []
    edges: list[str] = []

    urls = re.findall(r"https?://\S+", answer)
    for url in urls:
        nodes.append(f"Page_{url}")

    page_ids = re.findall(r"page_id['\"]?\s*[:=]\s*['\"]?([a-f0-9-]{36})", answer)
    for pid in page_ids:
        nodes.append(f"Page_{pid}")

    if nodes:
        edges.append("HAS_CHUNK")

    return list(set(nodes)), list(set(edges))
