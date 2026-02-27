"""환경변수, 설정값 로드."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

BEDROCK_MODEL_ID = os.getenv(
    "BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
)
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

EMBEDDING_MODEL = os.getenv(
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002"
)
EMBEDDING_DIMENSION = 1536

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j")
NEO4J_AUTH = (NEO4J_USERNAME, NEO4J_PASSWORD)
NEO4J_DB = os.getenv("NEO4J_DB", "neo4j")

INDEX_NAME = "content_vector_index"
