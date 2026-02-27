"""GET /health - 서버 상태 확인."""

from fastapi import APIRouter

from graphrag.web.config import BEDROCK_MODEL_ID, NEO4J_DB
from graphrag.web.services.rag_service import async_driver

router = APIRouter()


@router.get("/health")
async def health_check():
    try:
        async with async_driver.session(database=NEO4J_DB) as session:
            await session.run("RETURN 1")
        return {"status": "healthy", "neo4j": "connected", "llm": BEDROCK_MODEL_ID}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
