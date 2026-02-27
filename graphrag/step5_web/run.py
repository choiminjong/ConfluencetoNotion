"""Phase 2 STEP 6: GraphRAG 웹 시각화 서버 실행.

FastAPI + vis-network.js 기반 웹 UI를 시작한다.

사용법:
    python -m graphrag.web.run

접속:
    http://localhost:8000
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn


def main():
    uvicorn.run("graphrag.web.app:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
