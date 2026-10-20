import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

import crawling


def autocomplete_response(items):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"items": items}
    return response


class ResolveStockCodeTests(unittest.TestCase):
    @patch("crawling.requests.get")
    def test_exact_name_match_is_preferred(self, mock_get):
        mock_get.return_value = autocomplete_response([
            {"name": "RISE 삼성전자SK하이닉스채권혼합50", "code": "0162Z0"},
            {"name": "삼성전자", "code": "005930"},
        ])
        self.assertEqual(crawling.resolve_stock_code("삼성전자"), "005930")

    @patch("crawling.requests.get")
    def test_first_item_used_when_no_exact_match(self, mock_get):
        mock_get.return_value = autocomplete_response([
            {"name": "셀트리온제약", "code": "068760"},
        ])
        self.assertEqual(crawling.resolve_stock_code("셀트리온제약헬스케어"), "068760")

    @patch("crawling.requests.get")
    def test_no_results_raises_404(self, mock_get):
        mock_get.return_value = autocomplete_response([])
        with self.assertRaises(HTTPException) as ctx:
            crawling.resolve_stock_code("존재하지않는가상회사12345")
        self.assertEqual(ctx.exception.status_code, 404)

    @patch("crawling.requests.get")
    def test_request_failure_raises_503(self, mock_get):
        mock_get.side_effect = crawling.requests.exceptions.ConnectionError("boom")
        with self.assertRaises(HTTPException) as ctx:
            crawling.resolve_stock_code("셀트리온")
        self.assertEqual(ctx.exception.status_code, 503)

    @patch("crawling.requests.get")
    def test_query_is_forwarded_to_naver_autocomplete(self, mock_get):
        mock_get.return_value = autocomplete_response([{"name": "셀트리온", "code": "068270"}])
        crawling.resolve_stock_code("셀트리온")
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], "https://ac.stock.naver.com/ac")
        self.assertEqual(kwargs["params"]["q"], "셀트리온")


class GetStockDataWithSearchTests(unittest.TestCase):
    @patch("crawling.requests.get")
    def test_uses_resolved_code_for_detail_page(self, mock_get):
        search_response = autocomplete_response([{"name": "셀트리온", "code": "068270"}])
        detail_response = MagicMock()
        detail_response.raise_for_status = MagicMock()
        detail_response.text = "<html><body></body></html>"
        mock_get.side_effect = [search_response, detail_response]

        info = crawling.get_stock_data_with_search("셀트리온")

        self.assertEqual(info.stock_code, "068270")
        detail_call_url = mock_get.call_args_list[1].args[0]
        self.assertIn("code=068270", detail_call_url)


if __name__ == "__main__":
    unittest.main()
