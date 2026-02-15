from __future__ import annotations

import unittest
from pathlib import Path

from ai_code_waste_detector.engine import analyze_repo
from ai_code_waste_detector.report import build_json_report


class ReportJsonTestCase(unittest.TestCase):
    def test_json_report_has_expected_sections(self) -> None:
        fixtures_dir = Path(__file__).parent / "fixtures"
        runtime_file = fixtures_dir / "runtime.json"

        result = analyze_repo(
            repo_path=fixtures_dir,
            runtime_path=runtime_file,
            git_provenance_enabled=False,
        )
        payload = build_json_report(
            result=result,
            repo_path=fixtures_dir,
            time_window_days=90,
            history_context=None,
        )

        self.assertIn("meta", payload)
        self.assertIn("summary", payload)
        self.assertIn("entities", payload)
        self.assertIn("findings", payload)
        self.assertIn("runtime_evidence", payload)
        self.assertIn("git_evidence", payload)
        self.assertIsInstance(payload["entities"], list)
        self.assertIsInstance(payload["findings"], list)
        self.assertEqual(payload["trend"], None)


if __name__ == "__main__":
    unittest.main()
