"""POST /query, /query/stream - GraphRAG 질의 처리.

2단계 대화형 UX:
  Step 1 (domain 미지정): 전체 검색 → 도메인 여러 개면 간략 요약 + 도메인 목록 반환
  Step 2 (domain 지정):   해당 도메인만 상세 답변 (SSE 스트리밍)
"""

import asyncio
import json
import logging
import queue as queue_mod
import re
import threading
import time
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    top_k: int = 3
    mode: str = "summary"
    domain: Optional[str] = None


class QueryResponse(BaseModel):
    answer: str
    used_nodes: List[str]
    used_edges: List[str]
    retriever_used: str
    domains: List[str] = []
    elapsed_sec: float = 0.0


_RE_QUOTED = re.compile(r"""['"]([^'"]+)['"]""")
_RE_UUID = re.compile(r"[a-f0-9-]{36}")


def _extract_field(content: str, field: str) -> list[str]:
    """content 문자열에서 field='value' 또는 field: 'value' 형태의 값을 추출한다."""
    pattern = re.compile(
        rf"""{field}['\"]?\s*[:=]\s*['"]([^'"]+)['"]""", re.IGNORECASE
    )
    results = []
    for m in pattern.finditer(content):
        v = m.group(1).strip()
        if v and v.lower() != "none":
            results.append(v)
    return results


def _extract_from_items(items, domain_filter=None):
    """retriever items에서 도메인, page_id, page_title, context를 추출한다."""
    domains = []
    page_ids = []
    page_entries = []
    context_parts = []

    for item in items:
        content = str(item.content) if hasattr(item, "content") else ""

        if domain_filter and domain_filter.lower() not in content.lower():
            continue

        context_parts.append(content)

        item_domains = _extract_field(content, "domain_name")
        item_titles = _extract_field(content, "page_title")
        domains.extend(item_domains)

        entry_domain = item_domains[0] if item_domains else ""
        entry_title = item_titles[0] if item_titles else ""
        if entry_title:
            page_entries.append({"title": entry_title, "domain": entry_domain})

        pid_match = re.search(r"page_id\s*[:=]\s*['\"]?([^'\"}\s,>]+)", content)
        if pid_match:
            for m in _RE_UUID.finditer(pid_match.group(1)):
                page_ids.append(m.group(0))

    return (
        list(dict.fromkeys(domains)),
        list(dict.fromkeys(page_ids)),
        page_entries,
        "\n\n".join(context_parts),
    )


_LIST_KEYWORDS = re.compile(
    r"(목록|리스트|list|문서.*찾|찾아|알려줘|어떤.*문서|몇.*개|나열)", re.IGNORECASE
)


def _auto_detect_mode(question: str) -> str:
    """질문을 분석하여 list/summary 모드를 자동 선택한다."""
    if _LIST_KEYWORDS.search(question):
        return "list"
    return "summary"


def _build_prompt(template, context, question):
    """프롬프트 템플릿에 context와 question을 채운다."""
    return template.template.replace("{context}", context).replace(
        "{query_text}", question
    )


@router.post("/query", response_model=QueryResponse)
async def query_graphrag(req: QueryRequest):
    """1회 retrieval + 1회 LLM 호출로 답변을 생성한다."""
    try:
        from graphrag.step5_web.services.rag_service import (
            llm_instance,
            retriever as vec_retriever,
        )

        if vec_retriever is None or llm_instance is None:
            raise HTTPException(status_code=500, detail="GraphRAG not initialized")

        from graphrag.step4_rag.rag_pipeline import (
            PROMPT_DOMAIN_OVERVIEW,
            PROMPT_LIST,
            PROMPT_SUMMARY,
        )

        query_with_k = f"{req.question} (상위 {req.top_k}개만 답변)"
        if req.domain:
            query_with_k = (
                f"{req.question} (도메인: {req.domain}, 상위 {req.top_k}개만 답변)"
            )

        start = time.time()

        retrieval_result = await asyncio.to_thread(
            vec_retriever.search, query_text=query_with_k, top_k=req.top_k
        )

        items = retrieval_result.items if hasattr(retrieval_result, "items") else []
        domains, page_ids, page_entries, context_str = _extract_from_items(
            items, domain_filter=req.domain
        )

        auto_mode = _auto_detect_mode(req.question)
        if not req.domain and len(domains) > 1:
            prompt_tpl = PROMPT_DOMAIN_OVERVIEW
        elif auto_mode == "list":
            prompt_tpl = PROMPT_LIST
        else:
            prompt_tpl = PROMPT_SUMMARY

        prompt = _build_prompt(prompt_tpl, context_str, req.question)

        llm_result = await asyncio.to_thread(llm_instance.invoke, prompt)
        answer_text = llm_result.content if hasattr(llm_result, "content") else str(llm_result)

        elapsed = round(time.time() - start, 1)
        logger.info("[Query] %s (domain=%s, top_k=%d, mode=%s, elapsed=%ss)", req.question, req.domain, req.top_k, auto_mode, elapsed)

        used_nodes = [f"Page_{pid}" for pid in page_ids]
        used_edges = ["HAS_CHUNK"] if used_nodes else []

        return QueryResponse(
            answer=answer_text,
            used_nodes=list(set(used_nodes)),
            used_edges=list(set(used_edges)),
            retriever_used="vector_cypher",
            domains=domains,
            elapsed_sec=elapsed,
        )
    except Exception as e:
        import traceback

        logger.error("Query failed: %s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"{e}\n{traceback.format_exc()}")


@router.post("/query/stream")
async def query_graphrag_stream(req: QueryRequest):
    """모든 쿼리를 SSE 스트리밍으로 처리한다."""
    from graphrag.step5_web.services.rag_service import (
        llm_instance,
        retriever as vec_retriever,
    )

    if vec_retriever is None or llm_instance is None:
        raise HTTPException(status_code=500, detail="GraphRAG not initialized")

    from graphrag.step4_rag.rag_pipeline import (
        PROMPT_DOMAIN_OVERVIEW,
        PROMPT_LIST,
        PROMPT_SUMMARY,
    )

    query_with_k = f"{req.question} (상위 {req.top_k}개만 답변)"
    if req.domain:
        query_with_k = (
            f"{req.question} (도메인: {req.domain}, 상위 {req.top_k}개만 답변)"
        )

    start = time.time()

    retrieval_result = await asyncio.to_thread(
        vec_retriever.search, query_text=query_with_k, top_k=req.top_k
    )

    items = retrieval_result.items if hasattr(retrieval_result, "items") else []
    domains, page_ids, page_entries, context_str = _extract_from_items(
        items, domain_filter=req.domain
    )

    auto_mode = _auto_detect_mode(req.question)
    if not req.domain and len(domains) > 1:
        prompt_tpl = PROMPT_DOMAIN_OVERVIEW
    elif auto_mode == "list":
        prompt_tpl = PROMPT_LIST
    else:
        prompt_tpl = PROMPT_SUMMARY

    prompt = _build_prompt(prompt_tpl, context_str, req.question)

    used_nodes = [f"Page_{pid}" for pid in dict.fromkeys(page_ids)]
    used_edges = ["HAS_CHUNK"] if used_nodes else []
    retrieval_sec = round(time.time() - start, 1)

    logger.info(
        "[Stream] retrieval done in %.2fs (question=%s, domain=%s, domains=%s, entries=%s, mode=%s)",
        retrieval_sec, req.question, req.domain, domains, page_entries, auto_mode,
    )

    async def event_generator():
        q = queue_mod.Queue()
        first_token_time = [None]

        def _produce():
            try:
                for token in llm_instance.invoke_stream(prompt):
                    if first_token_time[0] is None:
                        first_token_time[0] = time.time()
                    q.put(("token", token))
            except Exception as e:
                q.put(("error", str(e)))
            q.put(("done", None))

        thread = threading.Thread(target=_produce, daemon=True)
        thread.start()

        while True:
            while q.empty():
                await asyncio.sleep(0.02)
            event_type, data = q.get_nowait()
            if event_type == "token":
                yield f"data: {json.dumps({'type': 'token', 'content': data}, ensure_ascii=False)}\n\n"
            elif event_type == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': data}, ensure_ascii=False)}\n\n"
                break
            elif event_type == "done":
                elapsed = round(time.time() - start, 1)
                first_token_sec = round(first_token_time[0] - start, 1) if first_token_time[0] else 0
                llm_sec = round(elapsed - retrieval_sec, 1)
                logger.info(
                    "[Stream] total=%.1fs (retrieval=%.1fs, first_token=%.1fs, llm=%.1fs)",
                    elapsed, retrieval_sec, first_token_sec, llm_sec,
                )
                yield f"data: {json.dumps({'type': 'done', 'used_nodes': used_nodes, 'used_edges': used_edges, 'domains': domains, 'page_entries': page_entries, 'mode': auto_mode, 'elapsed_sec': elapsed, 'retrieval_sec': retrieval_sec, 'first_token_sec': first_token_sec, 'llm_sec': llm_sec}, ensure_ascii=False)}\n\n"
                break

        thread.join(timeout=10)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
