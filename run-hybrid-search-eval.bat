@echo off
setlocal

where docker >nul 2>nul
if errorlevel 1 (
    echo [오류] docker 명령을 찾을 수 없습니다. Docker Desktop이 설치/실행 중인지 확인하세요.
    exit /b 1
)

if not exist ".env" (
    echo [오류] .env 파일이 없습니다. .env.example을 복사해서 .env를 만드세요.
    echo         ^(이 평가 자체는 OpenAI API를 쓰지 않지만, docker-compose.yml이 OPENAI_API_KEY를 요구합니다^)
    exit /b 1
)

echo ============================================================
echo   Milvus + RAG 서버 기동 중... (최초 실행 시 몇 분 걸릴 수 있음)
echo ============================================================
docker compose up -d --build --wait etcd minio milvus rag-server
if errorlevel 1 (
    echo [오류] 컨테이너 기동 실패. "docker compose logs rag-server"로 확인하세요.
    exit /b 1
)

echo.
echo ============================================================
echo   하이브리드 검색 Recall@K 평가 실행 중...
echo ============================================================
docker compose exec rag-server python -m evals.hybrid_search_recall_eval

endlocal
