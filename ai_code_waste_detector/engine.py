from __future__ import annotations

from pathlib import Path

from .duplication import detect_duplication_pairs
from .models import AnalysisResult, Finding
from .provenance import detect_ai_signals
from .runtime import load_runtime_index, map_runtime_evidence
from .scanner import extract_entities


def analyze_repo(
    repo_path: str | Path,
    runtime_path: str | Path | None = None,
    time_window_days: int = 90,
    cost_per_invocation: float = 0.0,
    ai_threshold: float = 0.65,
    duplication_threshold: float = 0.9,
    min_duplicate_body_statements: int = 3,
    include_tests: bool = False,
) -> AnalysisResult:
    entities = extract_entities(repo_path, include_tests=include_tests)
    ai_signals = detect_ai_signals(entities, threshold=ai_threshold)
    duplication_pairs = detect_duplication_pairs(
        entities,
        high_threshold=duplication_threshold,
        min_body_statements=min_duplicate_body_statements,
    )

    runtime_index = load_runtime_index(runtime_path)
    runtime_evidence = map_runtime_evidence(entities, runtime_index)

    ai_by_entity = {signal.entity_id: signal for signal in ai_signals}
    duplicate_members = {
        member for pair in duplication_pairs for member in (pair.entity_a, pair.entity_b)
    }

    findings: list[Finding] = []
    annualized_cost_total = 0.0

    probable_ai_zero_invocations = 0
    runtime_zero_invocations = 0
    runtime_unknown = 0

    for entity in entities:
        runtime = runtime_evidence[entity.entity_id]
        signal = ai_by_entity.get(entity.entity_id)

        if runtime.invocation_count == 0:
            runtime_zero_invocations += 1
            if signal is not None:
                probable_ai_zero_invocations += 1
                findings.append(
                    Finding(
                        finding_type="runtime_unused_review",
                        severity="low",
                        title="Probable AI-generated function with zero runtime usage",
                        entity_ids=[entity.entity_id],
                        evidence=[
                            f"ai_probability={signal.ai_probability}",
                            "runtime_invocations=0",
                            f"confidence={signal.confidence}",
                        ],
                    )
                )

        if runtime.invocation_count is None:
            runtime_unknown += 1

        if (
            signal is not None
            and signal.confidence == "high"
            and runtime.invocation_count == 0
            and entity.entity_id in duplicate_members
        ):
            findings.append(
                Finding(
                    finding_type="delete_candidate_review",
                    severity="low",
                    title="High-confidence delete candidate (human review required)",
                    entity_ids=[entity.entity_id],
                    evidence=[
                        f"ai_probability={signal.ai_probability}",
                        "runtime_invocations=0",
                        "high_semantic_overlap=true",
                    ],
                )
            )

    for pair in duplication_pairs:
        runtime_a = runtime_evidence[pair.entity_a]
        runtime_b = runtime_evidence[pair.entity_b]

        if (
            runtime_a.invocation_count is not None
            and runtime_b.invocation_count is not None
            and runtime_a.invocation_count > 0
            and runtime_b.invocation_count > 0
        ):
            estimated_annual_cost = None
            if cost_per_invocation > 0:
                duplicate_invocations = min(
                    runtime_a.invocation_count, runtime_b.invocation_count
                )
                annualization_factor = 365.0 / max(time_window_days, 1)
                estimated_annual_cost = round(
                    duplicate_invocations * cost_per_invocation * annualization_factor, 2
                )
                annualized_cost_total += estimated_annual_cost

            findings.append(
                Finding(
                    finding_type="consolidation_candidate_review",
                    severity="medium",
                    title="High-overlap active duplicate logic (human review required)",
                    entity_ids=[pair.entity_a, pair.entity_b],
                    evidence=[
                        f"semantic_overlap={pair.semantic_overlap}",
                        f"invocations_a={runtime_a.invocation_count}",
                        f"invocations_b={runtime_b.invocation_count}",
                    ],
                    estimated_annual_cost=estimated_annual_cost,
                )
            )

    high_confidence_ai = sum(1 for signal in ai_signals if signal.confidence == "high")

    summary: dict[str, float | int | str] = {
        "functions_scanned": len(entities),
        "probable_ai_functions": len(ai_signals),
        "high_confidence_ai_functions": high_confidence_ai,
        "high_confidence_duplication_pairs": len(duplication_pairs),
        "runtime_zero_invocations": runtime_zero_invocations,
        "runtime_unknown": runtime_unknown,
        "probable_ai_zero_invocations": probable_ai_zero_invocations,
        "estimated_annualized_avoidable_runtime_cost": round(annualized_cost_total, 2),
    }

    return AnalysisResult(
        entities=entities,
        ai_signals=ai_signals,
        duplication_pairs=duplication_pairs,
        runtime_evidence=runtime_evidence,
        findings=findings,
        summary=summary,
    )
