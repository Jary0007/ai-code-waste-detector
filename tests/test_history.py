from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_code_waste_detector.history import record_run
from ai_code_waste_detector.models import Finding


class HistoryTestCase(unittest.TestCase):
    def test_record_run_and_trend_delta(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.db"
            repo_path = Path(temp_dir) / "repo"
            repo_path.mkdir()

            summary_a = {
                "functions_scanned": 10,
                "probable_ai_functions": 3,
                "high_confidence_duplication_pairs": 2,
                "runtime_zero_invocations": 1,
                "probable_ai_zero_invocations": 1,
                "estimated_annualized_avoidable_runtime_cost": 12.5,
            }
            summary_b = {
                "functions_scanned": 12,
                "probable_ai_functions": 2,
                "high_confidence_duplication_pairs": 1,
                "runtime_zero_invocations": 0,
                "probable_ai_zero_invocations": 0,
                "estimated_annualized_avoidable_runtime_cost": 7.0,
            }
            config = {
                "ai_threshold": 0.65,
                "dup_threshold": 0.9,
                "min_dup_body_statements": 3,
                "min_dup_signature_chars": 160,
                "include_tests": False,
                "git_provenance_enabled": True,
            }

            first = record_run(
                db_path=db_path,
                repo_path=repo_path,
                summary=summary_a,
                findings=[Finding(finding_type="x", severity="low", title="a")],
                config=config,
            )
            second = record_run(
                db_path=db_path,
                repo_path=repo_path,
                summary=summary_b,
                findings=[Finding(finding_type="x", severity="low", title="a")],
                config=config,
            )

            self.assertIsNotNone(first["run_id"])
            self.assertIsNotNone(second["run_id"])
            self.assertIsNotNone(second["previous_run_id"])
            self.assertIsNotNone(second["trend"])
            trend = second["trend"]
            assert isinstance(trend, dict)
            self.assertEqual(trend["functions_scanned_delta"], 2)
            self.assertEqual(trend["probable_ai_functions_delta"], -1)
            self.assertEqual(
                trend["estimated_annualized_avoidable_runtime_cost_delta"],
                -5.5,
            )


if __name__ == "__main__":
    unittest.main()
