"""POST /query - GraphRAG 질의 처리."""

import asyncio
import logging
import re
import time
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from graphrag.web.services.parser import cypher_capture, extract_nodes_from_answer

router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    top_k: int = 3
    mode: str = "summary"


class QueryResponse(BaseModel):
    answer: str
    used_nodes: List[str]
    used_edges: List[str]
    retriever_used: str
    context: str = ""
    elapsed_sec: float = 0.0
    cypher_query: str = ""


def _run_search(active_rag, query_text: str):
    """동기 RAG 검색을 스레드 풀에서 실행하기 위한 래퍼."""
    return active_rag.search(query_text=query_text, return_context=True)


@router.post("/query", response_model=QueryResponse)
async def query_graphrag(req: QueryRequest):
    try:
        from graphrag.web.services.rag_service import (
            graphrag_list as gl,
            graphrag_summary as gs,
        )

        if gs is None or gl is None:
            raise HTTPException(status_code=500, detail="GraphRAG not initialized")

        active_rag = gs if req.mode == "summary" else gl
        query_with_k = f"{req.question} (상위 {req.top_k}개만 답변)"
        cypher_capture.pop()

        start = time.time()
        result = await asyncio.to_thread(_run_search, active_rag, query_with_k)
        elapsed = round(time.time() - start, 1)
        captured_cypher = cypher_capture.pop()

        logger.info("[Query] %s", req.question)
        logger.info("[Elapsed] %ss", elapsed)
        if captured_cypher:
            logger.info("[Cypher] %s", captured_cypher)

        used_nodes, used_edges = [], []
        retriever_used = "unknown"
        context_str = ""
        cypher_query = ""

        try:
            if hasattr(result, "retriever_result") and result.retriever_result:
                rr = result.retriever_result
                if hasattr(rr, "metadata") and rr.metadata:
                    cypher_query = rr.metadata.get("cypher", "")
                if hasattr(rr, "items") and rr.items:
                    for item in rr.items:
                        if hasattr(item, "metadata") and item.metadata:
                            if "tool" in item.metadata:
                                retriever_used = item.metadata["tool"]
                            if "cypher" in item.metadata and not cypher_query:
                                cypher_query = item.metadata["cypher"]
                        if hasattr(item, "content"):
                            context_str += str(item.content) + "\n\n"

            if not cypher_query and captured_cypher:
                cypher_query = captured_cypher
            if not cypher_query and context_str:
                m = re.search(
                    r"(MATCH\s.*?RETURN\s[^\n]+)", context_str,
                    re.IGNORECASE | re.DOTALL,
                )
                if m:
                    cypher_query = m.group(1).strip()

            answer_text = result.answer if hasattr(result, "answer") else str(result)
            used_nodes, used_edges = extract_nodes_from_answer(answer_text)

        except Exception as e:
            logger.warning("파싱 오류: %s", e)

        return QueryResponse(
            answer=result.answer if hasattr(result, "answer") else str(result),
            used_nodes=list(set(used_nodes)),
            used_edges=list(set(used_edges)),
            retriever_used=retriever_used,
            context=context_str[:1000] if context_str else "",
            elapsed_sec=elapsed,
            cypher_query=cypher_query,
        )
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"{e}\n{traceback.format_exc()}")
