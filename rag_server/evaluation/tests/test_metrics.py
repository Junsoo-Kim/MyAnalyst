import unittest

from evaluation.metrics import ndcg_at_k, recall_at_k, reciprocal_rank, summarize


class RetrievalMetricsTests(unittest.TestCase):
    def setUp(self):
        self.results = [
            {"collection": "news_embeddings", "id": 4},
            {"collection": "celltrion_embeddings", "id": 2},
            {"collection": "news_embeddings", "id": 4},
            {"collection": "celltrion_embeddings", "id": 7},
        ]
        self.relevant = ["celltrion_embeddings:2", "celltrion_embeddings:7"]

    def test_recall_deduplicates_results(self):
        self.assertEqual(recall_at_k(self.results, self.relevant, 2), 0.5)
        self.assertEqual(recall_at_k(self.results, self.relevant, 3), 1.0)

    def test_mrr_and_ndcg(self):
        self.assertEqual(reciprocal_rank(self.results, self.relevant), 0.5)
        self.assertGreater(ndcg_at_k(self.results, self.relevant, 3), 0.0)
        self.assertLessEqual(ndcg_at_k(self.results, self.relevant, 3), 1.0)

    def test_summary_excludes_unlabeled_cases_from_quality_average(self):
        report = summarize([
            {"relevant_document_ids": self.relevant, "recall_at_k": 1.0, "mrr": 1.0, "ndcg_at_k": 1.0, "latency_ms": 10},
            {"relevant_document_ids": [], "recall_at_k": 0.0, "mrr": 0.0, "ndcg_at_k": 0.0, "latency_ms": 30},
        ], 10)
        self.assertEqual(report["labeled_query_count"], 1)
        self.assertEqual(report["recall_at_k"], 1.0)
        self.assertEqual(report["latency_ms"]["p50"], 20.0)


if __name__ == "__main__":
    unittest.main()
