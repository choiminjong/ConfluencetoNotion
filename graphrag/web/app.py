"""FastAPI 진입점.

GraphRAG 웹 시각화 서버. Neo4j 그래프를 vis-network.js로 시각화하고
GraphRAG 질의를 처리한다.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from graphrag.web.config import BEDROCK_MODEL_ID, EMBEDDING_MODEL, NEO4J_DB, NEO4J_URI
from graphrag.web.routers import graph, health, query
from graphrag.web.services.rag_service import driver, initialize


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        initialize()
        print(f"LLM:       {BEDROCK_MODEL_ID}")
        print(f"Embedding: {EMBEDDING_MODEL}")
        print(f"Neo4j:     {NEO4J_URI} (db: {NEO4J_DB})")
        print("Retriever 초기화 완료")
    except Exception as e:
        print(f"Retriever 초기화 실패: {e}")
    yield
    driver.close()


app = FastAPI(title="Confluence GraphRAG", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.include_router(graph.router)
app.include_router(query.router)
app.include_router(health.router)


@app.get("/")
async def root():
    return FileResponse(os.path.join(static_dir, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("graphrag.web.app:app", host="0.0.0.0", port=8000)
