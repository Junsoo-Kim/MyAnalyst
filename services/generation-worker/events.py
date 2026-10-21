# events.py — Kafka 메시지 계약. JSON 필드는 Spring 쪽 레코드와 같은 camelCase를 쓴다.
# 예시 메시지는 저장소 루트의 contracts/*.json 이고, generation-service와 워커의 계약 테스트가 둘 다 이 파일을 읽는다.
from typing import List, Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

EVENT_VERSION = "1"

GENERATION_REQUESTED = "generation.requested"
GENERATION_PROGRESSED = "generation.progressed"
GENERATION_COMPLETED = "generation.completed"
GENERATION_FAILED = "generation.failed"
DLT_SUFFIX = ".DLT"

# 워커가 발행하는 토픽(발행자가 소유하고 생성한다). generation.requested는 generation-service가 소유한다.
OWNED_TOPICS = [GENERATION_PROGRESSED, GENERATION_COMPLETED, GENERATION_FAILED]


class _Message(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    def to_json_bytes(self) -> bytes:
        return self.model_dump_json(by_alias=True).encode("utf-8")


class GenerationRequested(_Message):
    """generation-service → 워커. 워커는 generation-service DB를 보지 않으므로 생성에 필요한 입력을 모두 싣는다."""
    job_id: str
    attempt: int
    trace_id: Optional[str] = None
    title: str
    chapter: Optional[str] = ""
    indicator: Optional[str] = "none"
    evaluations: Optional[str] = ""
    company: str
    date: str


class GenerationProgressed(_Message):
    """STARTED는 이 시도를 시작했다는 신호이자 generation-service lease의 시작점이고, 이후 섹션 진행은 heartbeat 역할도 한다."""
    job_id: str
    attempt: int
    stage: str
    progress: int
    message: str


class ReportTermMessage(_Message):
    term: str
    explanation: str


class GenerationCompleted(_Message):
    job_id: str
    attempt: int
    report: str
    terms: List[ReportTermMessage]
    generation_time_seconds: float


class GenerationFailed(_Message):
    job_id: str
    attempt: int
    error: str
    retryable: bool = True
