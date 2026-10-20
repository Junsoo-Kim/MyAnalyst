"""OpenAI-compatible stub (chat.completions + audio.transcriptions) for running the real pipeline without an API key.

Env:
  STUB_DELAY_SECONDS  delay per chat completion (default 0.2) - raise it to make a report take longer
  STUB_FAIL_FILE      if this file exists, every chat completion returns 500 (toggle failures without restart)
"""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DELAY = float(os.environ.get("STUB_DELAY_SECONDS", "0.2"))
FAIL_FILE = os.environ.get("STUB_FAIL_FILE", "")
CALLS = {"count": 0}


def completion(content: str, model: str) -> dict:
    return {
        "id": "chatcmpl-stub", "object": "chat.completion", "created": int(time.time()), "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }


def answer_for(messages) -> str:
    system = " ".join(m.get("content", "") for m in messages if m.get("role") == "system")
    user = " ".join(m.get("content", "") for m in messages if m.get("role") == "user")
    if "relevance grader" in system:
        return json.dumps({"relevant_indices": list(range(20))})
    if "grounding grader" in system:
        return json.dumps({"grounded": True, "feedback": ""})
    if "domain-specific terms" in system:
        return json.dumps({"terms": [
            {"term": "영업이익", "explanation": "매출에서 영업비용을 뺀 이익"},
            {"term": "PER", "explanation": "주가수익비율"},
            {"term": "이 용어는 스무 글자를 넘어서 사전 컬럼에 들어가지 않습니다", "explanation": "too long"},
        ]}, ensure_ascii=False)
    if "보고서를 바탕으로 질문" in system:
        return "스텁 답변: 보고서에 따르면 4분기 실적은 개선되었습니다."
    if "검색 키워드" in user or "키워드" in user[:400]:
        return "셀트리온 4분기 매출 영업이익 바이오시밀러"
    return "### 스텁 섹션\n\n컨텍스트를 바탕으로 생성된 스텁 본문입니다. 4분기 매출과 영업이익을 요약합니다."


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        if self.path.endswith("/audio/transcriptions"):
            return self._send(200, {"text": "셀트리온의 4분기 실적은 어땠나요?"})
        if self.path.endswith("/chat/completions"):
            CALLS["count"] += 1
            if FAIL_FILE and os.path.exists(FAIL_FILE):
                return self._send(500, {"error": {"message": "stub failure", "type": "server_error"}})
            time.sleep(DELAY)
            req = json.loads(raw)
            print(f"chat #{CALLS['count']} model={req.get('model')}", flush=True)
            return self._send(200, completion(answer_for(req.get("messages", [])), req.get("model", "stub")))
        return self._send(404, {"error": {"message": "not stubbed"}})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("STUB_PORT", "18001"))), Handler).serve_forever()
