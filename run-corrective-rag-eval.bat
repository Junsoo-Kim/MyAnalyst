@echo off
setlocal

where docker >nul 2>nul
if errorlevel 1 (
    echo [오류] docker 명령을 찾을 수 없습니다. Docker Desktop이 설치/실행 중인지 확인하세요.
    exit /b 1
)

if not exist ".env" (
    echo [오류] .env 파일이 없습니다. .env.example을 복사해서 .env를 만들고
    echo         OPENAI_API_KEY에 실제 키를 넣으세요.
    exit /b 1
)

echo ============================================================
echo   Milvus + knowledge 서비스 기동 중... (최초 실행 시 몇 분 걸릴 수 있음)
echo ============================================================
docker compose up -d --build --wait etcd minio milvus opensearch knowledge
if errorlevel 1 (
    echo [오류] 컨테이너 기동 실패. "docker compose logs knowledge"로 확인하세요.
    exit /b 1
)

echo.
echo   평가용 임시 컬렉션 준비 (검색 저장소는 knowledge가 소유)...
docker compose exec knowledge python -m evals.eval_collection setup
if errorlevel 1 exit /b 1

echo.
echo ============================================================
echo   Corrective RAG 환각 비율 평가 실행 중... (generation-worker 이미지)
echo   (OpenAI API를 실제로 호출합니다 - 진행 여부를 다음 화면에서 확인합니다)
echo ============================================================
docker compose run --rm -it generation-worker python -m evals.corrective_rag_hallucination_eval

echo.
docker compose exec knowledge python -m evals.eval_collection cleanup

endlocal
