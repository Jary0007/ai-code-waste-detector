from __future__ import annotations

import unittest
from pathlib import Path

from ai_code_waste_detector.engine import analyze_repo


class EngineTestCase(unittest.TestCase):
    def test_analysis_detects_core_signals(self) -> None:
        fixtures_dir = Path(__file__).parent / "fixtures"
        runtime_file = fixtures_dir / "runtime.json"

        result = analyze_repo(
            repo_path=fixtures_dir,
            runtime_path=runtime_file,
            time_window_days=90,
            cost_per_invocation=0.0005,
            git_provenance_enabled=False,
        )

        self.assertGreaterEqual(result.summary["functions_scanned"], 3)
        self.assertGreaterEqual(result.summary["probable_ai_functions"], 1)
        self.assertGreaterEqual(result.summary["high_confidence_duplication_pairs"], 1)
        self.assertEqual(result.summary["runtime_zero_invocations"], 1)
        self.assertEqual(result.summary["git_evidence_available"], 0)

        consolidation_findings = [
            finding
            for finding in result.findings
            if finding.finding_type == "consolidation_candidate_review"
        ]
        self.assertGreaterEqual(len(consolidation_findings), 1)


if __name__ == "__main__":
    unittest.main()
