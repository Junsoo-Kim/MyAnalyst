import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


class ReportsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = main.app.openapi()

    def _request_schema(self, path: str, method: str = "post") -> dict:
        operation = self.schema["paths"][path][method]
        ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        component = ref.rsplit("/", 1)[-1]
        return self.schema["components"]["schemas"][component]

    def _response_schema(self, path: str, method: str = "post", status: str = "201") -> dict:
        operation = self.schema["paths"][path][method]
        ref = operation["responses"][status]["content"]["application/json"]["schema"]["$ref"]
        component = ref.rsplit("/", 1)[-1]
        return self.schema["components"]["schemas"][component]

    def test_reports_endpoint_is_documented(self):
        self.assertIn("/reports", self.schema["paths"])

    def test_report_request_field_names_match_what_spring_sends(self):
        """Spring의 ReportService.generateReportAndTerms가 실제로 보내는 필드 이름과
        FastAPI가 문서화한 요청 스키마가 어긋나면 이 테스트가 잡는다 — 과거
        evaluation/evaluations 계약 불일치가 재발하는 것을 막기 위함이다."""
        properties = set(self._request_schema("/reports")["properties"])
        expected = {
            "title", "company", "date", "chapter", "indicator",
            "evaluations", "generation_job_id",
        }
        self.assertEqual(expected, properties)

    def test_report_response_field_names_match_what_spring_expects(self):
        properties = set(self._response_schema("/reports")["properties"])
        expected = {"report", "generation_time_seconds", "domain_specific_terms"}
        self.assertEqual(expected, properties)


if __name__ == "__main__":
    unittest.main()
