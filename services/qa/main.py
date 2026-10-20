# main.py — qa-service: 저장된 보고서 본문을 근거로 질문에 답한다 (rag_server/main.py·utils.py에서 분리).
import os
import time
from typing import Optional

from fastapi import HTTPException, status
from openai import OpenAIError
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from myanalyst_common import observability
from myanalyst_common.llm import get_openai_client
from myanalyst_common.web import create_app

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

app = create_app(title="MyAnalyst QA Service", service="qa")


class QuestionRequest(BaseModel):
    report: str = Field(..., description="기업 분석 보고서 내용")
    question: str = Field(..., description="보고서에 대한 질문")


class QuestionResponse(BaseModel):
    answer: str = Field(..., description="보고서 내용을 바탕으로 생성된 질문 답변")
    question: Optional[str] = Field(None, description="사용자의 질문")


def answer_question_about_report(question: str, report_content: str) -> str:
    """
    기업 분석 보고서 내용을 바탕으로 사용자 질문에 대한 답변을 생성합니다.
    """
    print(f"보고서 기반 질문 응답 생성 시작: 질문 = '{question}'")

    # API 호출 최적화 - 보고서가 너무 길면 중요 부분만 추출하여 사용
    if len(report_content) > 12000:
        print(f"보고서가 너무 깁니다 ({len(report_content)}자). 응답 생성을 위해 적절히 자릅니다.")
        # 앞부분(목차와 요약 포함)과 뒷부분을 균형있게 유지
        report_for_query = report_content[:7000] + "\n\n...[중간 내용 생략]...\n\n" + report_content[-5000:]
    else:
        report_for_query = report_content

    # 질문 응답을 위한 프롬프트 구성
    prompt = f"""
당신은 기업 분석 보고서를 바탕으로 질문에 답변하는 전문가입니다.
다음은 기업 분석 보고서 내용입니다:

{report_for_query}

위 보고서를 바탕으로 다음 질문에 답변해 주세요:

[질문]
{question}

[답변 지침]
1. 보고서 내용을 바탕으로 기업의 상황, 실적, 전망 등에 대해 객관적으로 답변하세요.
2. 보고서에 포함된 정보를 최대한 활용하여 답변하세요. 필요한 경우 외부 지식을 사용할 수 있습니다.
3. 답변은 친절하고 명확하게 작성해주세요. 답변의 분량에 제한은 없습니다.
4. 보고서의 내용과 반대되는 내용을 주장하거나 당신의 개인적인 의견을 포함하지 마세요.
"""

    try:
        client = get_openai_client()
        with observability.time_llm_call(LLM_MODEL, "answer_question") as usage:
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": "당신은 기업 분석 보고서를 바탕으로 질문에 정확하게 답변하는 전문가입니다. 오직 보고서에 포함된 정보만을 사용하여 답변하세요."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,  # 응답의 일관성을 위해 낮은 온도 사용
            )
            observability.record_usage(usage, response)

        return response.choices[0].message.content.strip()

    except OpenAIError as oai_err:
        print(f"OpenAI API Error: {oai_err}")
        return f"질문에 대한 답변을 생성하는 중 오류가 발생했습니다: {oai_err}"


@app.post("/questions", response_model=QuestionResponse, status_code=status.HTTP_200_OK,
          summary="기업 분석 보고서 내용에 대한 질문 답변")
async def answer_report_question(request: QuestionRequest):
    print(f"질문 답변 API 호출: 질문 길이 = {len(request.question)}자, 보고서 길이 = {len(request.report)}자")
    start_time = time.time()

    # 보고서가 너무 짧거나 비어있는 경우 체크
    if len(request.report.strip()) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="유효한 보고서 내용이 제공되지 않았습니다. 보고서는 최소 100자 이상이어야 합니다."
        )
    # 질문이 너무 짧거나 비어있는 경우 체크
    if len(request.question.strip()) < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="유효한 질문이 제공되지 않았습니다. 질문은 최소 5자 이상이어야 합니다."
        )

    try:
        answer = await run_in_threadpool(answer_question_about_report, request.question, request.report)
    except Exception as e:
        print(f"질문 답변 생성 중 예상치 못한 오류 발생: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"질문 처리 중 내부 오류가 발생했습니다: {str(e)}"
        )

    print(f"질문 답변 생성 완료: 소요 시간 = {time.time() - start_time:.2f}초")
    return QuestionResponse(answer=answer, question=request.question)
