import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hybrid_search


def opensearch_hit(collection, milvus_id, text, score):
    return {
        "_score": score,
        "_source": {"collection": collection, "milvus_id": milvus_id, "text": text},
    }


class SearchBm25Tests(unittest.TestCase):
    @patch("hybrid_search.build_bm25_index")
    @patch("hybrid_search.get_opensearch_client")
    def test_query_is_tokenized_and_sent_against_the_search_tokens_field(self, mock_client_fn, mock_build):
        mock_client = MagicMock()
        mock_client.search.return_value = {"hits": {"hits": []}}
        mock_client_fn.return_value = mock_client

        hybrid_search.search_bm25("셀트리온 실적", 10)

        mock_build.assert_called_once()
        _, kwargs = mock_client.search.call_args
        self.assertEqual(kwargs["index"], hybrid_search.config.OPENSEARCH_INDEX)
        self.assertEqual(kwargs["body"]["size"], 10)
        expected = " ".join(hybrid_search._tokenize("셀트리온 실적"))
        self.assertEqual(kwargs["body"]["query"]["match"]["search_tokens"]["query"], expected)

    @patch("hybrid_search.build_bm25_index")
    def test_empty_query_returns_no_results_without_calling_opensearch(self, mock_build):
        with patch("hybrid_search._tokenize", return_value=[]):
            self.assertEqual(hybrid_search.search_bm25("   ", 10), [])

    @patch("hybrid_search.build_bm25_index")
    @patch("hybrid_search.get_opensearch_client")
    def test_hits_are_converted_back_to_chunk_dicts(self, mock_client_fn, mock_build):
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "hits": {"hits": [opensearch_hit("news_embeddings", "42", "본문", 3.5)]}
        }
        mock_client_fn.return_value = mock_client

        results = hybrid_search.search_bm25("질의", 10)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["collection"], "news_embeddings")
        self.assertEqual(results[0]["id"], "42")
        self.assertEqual(results[0]["text"], "본문")
        self.assertEqual(results[0]["score"], 3.5)
        self.assertNotIn("milvus_id", results[0])


class BuildBm25IndexTests(unittest.TestCase):
    @patch("hybrid_search.get_opensearch_client")
    def test_skips_reindexing_when_documents_already_present(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client.indices.exists.return_value = True
        mock_client.count.return_value = {"count": 5}
        mock_client_fn.return_value = mock_client

        hybrid_search.build_bm25_index()

        mock_client.indices.create.assert_not_called()
        mock_client.indices.refresh.assert_not_called()

    @patch("hybrid_search.get_opensearch_client")
    def test_creates_the_index_when_missing(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client.indices.exists.return_value = False
        mock_client.count.return_value = {"count": 0}
        mock_client_fn.return_value = mock_client

        with patch("hybrid_search.utils.ensure_milvus_connection"), \
             patch("hybrid_search.utility.has_collection", return_value=False):
            hybrid_search.build_bm25_index()

        mock_client.indices.create.assert_called_once()


class ReciprocalRankFusionTests(unittest.TestCase):
    def test_items_present_in_both_lists_rank_above_single_list_items(self):
        dense = [{"collection": "a", "id": "1"}, {"collection": "a", "id": "2"}]
        sparse = [{"collection": "a", "id": "2"}, {"collection": "a", "id": "3"}]

        fused = hybrid_search.reciprocal_rank_fusion([dense, sparse])

        self.assertEqual((fused[0]["collection"], fused[0]["id"]), ("a", "2"))

    def test_score_field_is_added(self):
        fused = hybrid_search.reciprocal_rank_fusion([[{"collection": "a", "id": "1"}]])
        self.assertIn("rrf_score", fused[0])


if __name__ == "__main__":
    unittest.main()
