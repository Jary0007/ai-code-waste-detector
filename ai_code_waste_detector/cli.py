from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import analyze_repo
from .history import record_run
from .report import build_json_report, build_markdown_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only diagnostic analyzer for AI code waste signals."
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Repository path to analyze (default: current directory).",
    )
    parser.add_argument(
        "--runtime",
        default=None,
        help="Optional runtime evidence JSON file.",
    )
    parser.add_argument(
        "--time-window-days",
        type=int,
        default=90,
        help="Runtime evidence time window in days (default: 90).",
    )
    parser.add_argument(
        "--cost-per-invocation",
        type=float,
        default=0.0,
        help="Optional cost per invocation for annualized signal estimation.",
    )
    parser.add_argument(
        "--ai-threshold",
        type=float,
        default=0.65,
        help="Minimum AI probability to emit a provenance signal (default: 0.65).",
    )
    parser.add_argument(
        "--dup-threshold",
        type=float,
        default=0.9,
        help="High-confidence duplication threshold (default: 0.9).",
    )
    parser.add_argument(
        "--min-dup-body-statements",
        type=int,
        default=3,
        help="Minimum function body statements to evaluate duplication (default: 3).",
    )
    parser.add_argument(
        "--min-dup-signature-chars",
        type=int,
        default=160,
        help="Minimum normalized signature length for duplication matching (default: 160).",
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help="Include functions under test directories in scan scope.",
    )
    parser.add_argument(
        "--disable-git-provenance",
        action="store_true",
        help="Disable git-history provenance signals in AI probability scoring.",
    )
    parser.add_argument(
        "--history-db",
        default=".waste_detector/history.db",
        help="SQLite database path for run history (default: .waste_detector/history.db).",
    )
    parser.add_argument(
        "--disable-history",
        action="store_true",
        help="Disable writing run history/trend data.",
    )
    parser.add_argument(
        "--currency",
        default="USD",
        help="Currency label for cost output (default: USD).",
    )
    parser.add_argument(
        "--output",
        default="reports/diagnostic.md",
        help="Markdown output path (default: reports/diagnostic.md).",
    )
    parser.add_argument(
        "--json-output",
        default="reports/diagnostic.json",
        help="JSON output path (default: reports/diagnostic.json).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    result = analyze_repo(
        repo_path=args.repo,
        runtime_path=args.runtime,
        time_window_days=args.time_window_days,
        cost_per_invocation=args.cost_per_invocation,
        ai_threshold=args.ai_threshold,
        duplication_threshold=args.dup_threshold,
        min_duplicate_body_statements=args.min_dup_body_statements,
        min_duplicate_signature_chars=args.min_dup_signature_chars,
        include_tests=args.include_tests,
        git_provenance_enabled=not args.disable_git_provenance,
    )

    history_context = None
    if not args.disable_history:
        history_context = record_run(
            db_path=args.history_db,
            repo_path=args.repo,
            summary=result.summary,
            findings=result.findings,
            config={
                "ai_threshold": args.ai_threshold,
                "dup_threshold": args.dup_threshold,
                "min_dup_body_statements": args.min_dup_body_statements,
                "min_dup_signature_chars": args.min_dup_signature_chars,
                "include_tests": args.include_tests,
                "git_provenance_enabled": not args.disable_git_provenance,
            },
        )

    markdown = build_markdown_report(
        result=result,
        repo_path=args.repo,
        time_window_days=args.time_window_days,
        currency=args.currency,
        history_context=history_context,
    )
    json_payload = build_json_report(
        result=result,
        repo_path=args.repo,
        time_window_days=args.time_window_days,
        history_context=history_context,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    json_output_path = Path(args.json_output)
    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    json_output_path.write_text(
        json.dumps(json_payload, indent=2, sort_keys=False),
        encoding="utf-8",
    )

    summary = result.summary
    print(f"Functions scanned: {summary['functions_scanned']}")
    print(f"Probable AI functions: {summary['probable_ai_functions']}")
    print(
        "High-confidence duplicate pairs: "
        f"{summary['high_confidence_duplication_pairs']}"
    )
    print(
        "Probable AI + zero invocations: "
        f"{summary['probable_ai_zero_invocations']}"
    )
    print(f"Git evidence coverage: {summary['git_evidence_available']}")
    if history_context is not None:
        print(f"History run id: {history_context['run_id']}")
    print(f"Report written: {output_path.resolve()}")
    print(f"JSON report written: {json_output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
