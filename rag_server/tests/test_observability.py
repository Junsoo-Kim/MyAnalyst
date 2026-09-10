import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import observability


def sample_value(metric, suffix, **labels):
    for family in metric.collect():
        for sample in family.samples:
            if sample.name.endswith(suffix) and sample.labels == labels:
                return sample.value
    return None


class TraceIdTests(unittest.TestCase):
    def test_default_trace_id_is_placeholder(self):
        self.assertEqual(observability.get_trace_id(), "-")

    def test_set_and_get_round_trip(self):
        observability.set_trace_id("abc-123")
        self.assertEqual(observability.get_trace_id(), "abc-123")
        observability.set_trace_id("-")


class TimeStageTests(unittest.TestCase):
    def test_records_histogram_observation(self):
        before = sample_value(observability.STAGE_DURATION, "_count", stage="unit-test-stage") or 0
        with observability.time_stage("unit-test-stage"):
            pass
        after = sample_value(observability.STAGE_DURATION, "_count", stage="unit-test-stage")
        self.assertEqual(after, before + 1)

    def test_propagates_exceptions_from_the_wrapped_block(self):
        with self.assertRaises(ValueError):
            with observability.time_stage("failing-stage"):
                raise ValueError("boom")


class TimeMilvusSearchTests(unittest.TestCase):
    def test_records_duration_per_collection(self):
        before = sample_value(
            observability.MILVUS_SEARCH_DURATION, "_count", collection="unit_test_collection"
        ) or 0
        with observability.time_milvus_search("unit_test_collection"):
            pass
        after = sample_value(
            observability.MILVUS_SEARCH_DURATION, "_count", collection="unit_test_collection"
        )
        self.assertEqual(after, before + 1)


class TimeLlmCallTests(unittest.TestCase):
    def test_records_token_usage(self):
        before = sample_value(
            observability.LLM_TOKENS_TOTAL, "_total",
            model="gpt-4o-mini", purpose="unit-test", direction="input",
        ) or 0

        with observability.time_llm_call("gpt-4o-mini", "unit-test") as usage:
            usage["prompt_tokens"] = 10
            usage["completion_tokens"] = 5

        after = sample_value(
            observability.LLM_TOKENS_TOTAL, "_total",
            model="gpt-4o-mini", purpose="unit-test", direction="input",
        )
        self.assertEqual(after, before + 10)

    def test_missing_usage_does_not_increment_token_counters(self):
        before = sample_value(
            observability.LLM_TOKENS_TOTAL, "_total",
            model="gpt-4o-mini", purpose="unit-test-no-usage", direction="output",
        ) or 0

        with observability.time_llm_call("gpt-4o-mini", "unit-test-no-usage"):
            pass

        after = sample_value(
            observability.LLM_TOKENS_TOTAL, "_total",
            model="gpt-4o-mini", purpose="unit-test-no-usage", direction="output",
        ) or 0
        self.assertEqual(after, before)


class RecordUsageTests(unittest.TestCase):
    def test_extracts_prompt_and_completion_tokens(self):
        response = MagicMock()
        response.usage.prompt_tokens = 42
        response.usage.completion_tokens = 7
        usage = {}
        observability.record_usage(usage, response)
        self.assertEqual(usage, {"prompt_tokens": 42, "completion_tokens": 7})

    def test_missing_usage_attribute_leaves_dict_empty(self):
        response = MagicMock(spec=[])
        usage = {}
        observability.record_usage(usage, response)
        self.assertEqual(usage, {})


if __name__ == "__main__":
    unittest.main()
