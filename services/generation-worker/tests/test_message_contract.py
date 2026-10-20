import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import events

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"


def load(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def aliases(model) -> set:
    return {field.alias or name for name, field in model.model_fields.items()}


class GenerationMessageContractTests(unittest.TestCase):
    """Spring 생성 모듈과 주고받는 Kafka 메시지의 필드 이름이 contracts/*.json과 어긋나면 이 테스트가 잡는다.
    과거 HTTP 계약에서 evaluation/evaluations 불일치가 났던 것을 메시지 계약에서도 막기 위함이다
    (이전 test_openapi_contract.py가 FastAPI /reports 스키마로 하던 검증을 메시지 기준으로 옮겼다)."""

    def test_requested_message_from_spring_is_accepted(self):
        payload = load("generation.requested.v1.json")
        request = events.GenerationRequested.model_validate(payload)
        self.assertEqual(request.evaluations, "Use only supplied evidence")
        self.assertEqual(aliases(events.GenerationRequested), set(payload))

    def test_progressed_message_fields_match_contract(self):
        payload = load("generation.progressed.v1.json")
        self.assertEqual(aliases(events.GenerationProgressed), set(payload))
        message = events.GenerationProgressed.model_validate(payload)
        self.assertEqual(json.loads(message.to_json_bytes()), payload)

    def test_completed_message_fields_match_contract(self):
        payload = load("generation.completed.v1.json")
        self.assertEqual(aliases(events.GenerationCompleted), set(payload))
        message = events.GenerationCompleted.model_validate(payload)
        self.assertEqual(json.loads(message.to_json_bytes()), payload)

    def test_failed_message_fields_match_contract(self):
        payload = load("generation.failed.v1.json")
        self.assertEqual(aliases(events.GenerationFailed), set(payload))
        message = events.GenerationFailed.model_validate(payload)
        self.assertEqual(json.loads(message.to_json_bytes()), payload)

    def test_requested_without_required_fields_is_rejected(self):
        payload = load("generation.requested.v1.json")
        del payload["company"]
        with self.assertRaises(Exception):
            events.GenerationRequested.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
