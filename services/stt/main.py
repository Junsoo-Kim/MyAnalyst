# main.py — stt-service: 음성 질문을 텍스트로 바꾼다 (rag_server/main.py·utils.py에서 분리).
# 답변 생성은 하지 않는다. BE 채팅 모듈이 이 결과를 qa-service에 다시 보낸다.
import os
import tempfile

from fastapi import File, HTTPException, UploadFile, status
from openai import OpenAIError
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from myanalyst_common import observability
from myanalyst_common.llm import get_openai_client
from myanalyst_common.web import create_app

STT_MODEL = os.getenv("STT_MODEL", "whisper-1")
SUPPORTED_EXTENSIONS = ['mp3', 'wav', 'm4a', 'mp4', 'mpeg', 'mpga', 'webm']

app = create_app(title="MyAnalyst STT Service", service="stt")


class TranscriptionResponse(BaseModel):
    text: str


def transcribe_audio(audio_content: bytes) -> str:
    """
    OpenAI의 Whisper API를 사용하여 오디오 파일을 텍스트로 변환합니다.
    """
    # 임시 파일로 오디오 저장
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_audio:
        temp_audio.write(audio_content)
        temp_audio_path = temp_audio.name

    try:
        client = get_openai_client()
        with observability.time_llm_call(STT_MODEL, "transcribe"), open(temp_audio_path, "rb") as audio_file:
            response = client.audio.transcriptions.create(
                model=STT_MODEL,
                file=audio_file,
                language="ko"  # 한국어로 설정
            )
        return response.text
    finally:
        try:
            os.unlink(temp_audio_path)
        except OSError as e:
            print(f"임시 파일 삭제 실패: {e}")


@app.post("/transcriptions", response_model=TranscriptionResponse, summary="음성 파일을 한국어 텍스트로 변환")
async def create_transcription(
    audio_file: UploadFile = File(..., description="질문 음성이 담긴 오디오 파일 (mp3, wav, m4a 지원)")
):
    # 파일 확장자 확인
    file_extension = (audio_file.filename or "").split('.')[-1].lower()
    if file_extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"지원되지 않는 오디오 파일 형식입니다. 지원되는 형식: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    # 오디오 파일 읽기
    audio_content = await audio_file.read()
    if not audio_content or len(audio_content) < 100:  # 최소 크기 체크
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="오디오 파일이 비어있거나 너무 작습니다.")

    try:
        text = await run_in_threadpool(transcribe_audio, audio_content)
    except OpenAIError as oai_err:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"음성 변환 중 오류가 발생했습니다: {oai_err}")

    if not text or len(text.strip()) < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="음성으로부터 텍스트를 추출할 수 없거나 질문이 너무 짧습니다."
        )
    return TranscriptionResponse(text=text)
