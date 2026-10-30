import unittest
from unittest.mock import patch

from app.scanner import reference_entry_count, reference_groups, reference_scan_symbols, run_scan


class ReferenceUniverseTests(unittest.TestCase):
    def test_preserves_exact_sixteen_by_ten_mapping(self):
        groups = reference_groups()

        self.assertEqual(len(groups), 16)
        self.assertEqual([len(group["stocks"]) for group in groups], [10] * 16)
        self.assertEqual(reference_entry_count(), 160)
        self.assertEqual(len({stock[0] for group in groups for stock in group["stocks"]}), 148)
        self.assertEqual(len(reference_scan_symbols()), 147)

        oil_and_gas = next(group for group in groups if group["id"] == "oil-gas")
        self.assertEqual([stock[0] for stock in oil_and_gas["stocks"]].count("BPCL"), 2)
        realty = next(group for group in groups if group["id"] == "realty")
        self.assertEqual([stock[0] for stock in realty["stocks"]].count("LODHA"), 2)

    def test_scan_candidates_are_deduplicated_and_exclude_known_suspension(self):
        symbols = reference_scan_symbols()

        self.assertEqual(len(symbols), len(set(symbols)))
        self.assertNotIn("NSE:TV18BRDCST", symbols)
        self.assertIn("NSE:TMPV", symbols)
        self.assertIn("NSE:EMBDL", symbols)

    def test_reference_scan_validates_symbols_before_quoting_and_keeps_match_logic(self):
        symbols = reference_scan_symbols()
        valid_symbols = [symbol for symbol in symbols if symbol != "NSE:SPICEJET"]
        instrument_details = [
            {"symbol": symbol, "is_equity": symbol != "NSE:SPICEJET"}
            for symbol in symbols
        ]
        quote_payload = {
            "data": [
                {
                    "requested": "NSE:HDFCBANK",
                    "symbol": "HDFCBANK",
                    "exchange": "NSE",
                    "open": 100.0,
                    "prev_close": 100.0,
                    "ltp": 101.0,
                    "change_pct": 1.0,
                },
                {
                    "requested": "NSE:BPCL",
                    "symbol": "BPCL",
                    "exchange": "NSE",
                    "open": 90.05,
                    "prev_close": 90.0,
                    "ltp": 91.0,
                    "change_pct": 1.1,
                },
            ],
            "meta": {"route": "test"},
        }

        with (
            patch("app.scanner.stock_names", return_value=instrument_details),
            patch("app.scanner.live_quotes", return_value=quote_payload) as quote_request,
        ):
            result = run_scan(symbols, universe="reference")

        quote_request.assert_called_once_with(valid_symbols)
        self.assertEqual(result["reference_entry_count"], 160)
        self.assertEqual(result["checked_count"], len(valid_symbols))
        self.assertEqual(result["unavailable_symbols"], ["NSE:SPICEJET"])
        self.assertEqual(result["instrument_status"]["NSE:SPICEJET"], "unavailable")
        self.assertEqual([row["status"] for row in result["rows"]], ["MATCH", "NEAR"])


if __name__ == "__main__":
    unittest.main()
