from __future__ import annotations

import argparse
from pathlib import Path

from .engine import analyze_repo
from .report import build_markdown_report


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
        "--include-tests",
        action="store_true",
        help="Include functions under test directories in scan scope.",
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
        include_tests=args.include_tests,
    )
    markdown = build_markdown_report(
        result=result,
        repo_path=args.repo,
        time_window_days=args.time_window_days,
        currency=args.currency,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

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
    print(f"Report written: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
