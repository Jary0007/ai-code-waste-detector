from __future__ import annotations

import unittest
from pathlib import Path

from ai_code_waste_detector.engine import analyze_repo


class JsSupportTestCase(unittest.TestCase):
    def test_js_entities_and_signals(self) -> None:
        fixtures_dir = Path(__file__).parent / "fixtures_js"
        runtime_file = fixtures_dir / "runtime.json"

        result = analyze_repo(
            repo_path=fixtures_dir,
            runtime_path=runtime_file,
            time_window_days=90,
            cost_per_invocation=0.0005,
            include_tests=True,
            git_provenance_enabled=False,
        )

        self.assertGreaterEqual(result.summary["functions_scanned"], 3)
        self.assertGreaterEqual(result.summary["probable_ai_functions"], 1)
        self.assertGreaterEqual(result.summary["high_confidence_duplication_pairs"], 1)

        # Ensure runtime mapping works with qualified names for script files.
        self.assertEqual(result.summary["runtime_zero_invocations"], 1)
        self.assertEqual(result.summary["git_evidence_available"], 0)


if __name__ == "__main__":
    unittest.main()
