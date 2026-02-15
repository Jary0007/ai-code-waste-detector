from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .models import AnalysisResult, CodeEntity


def _currency(value: float, currency: str) -> str:
    return f"{currency} {value:,.2f}"


def _entity_reference(entity_by_id: dict[str, CodeEntity], entity_id: str) -> str:
    entity = entity_by_id.get(entity_id)
    if entity is None:
        return entity_id
    return f"{entity.file_path}:{entity.lineno}"


def build_markdown_report(
    result: AnalysisResult,
    repo_path: str | Path,
    time_window_days: int,
    currency: str = "USD",
    history_context: dict[str, object] | None = None,
) -> str:
    entity_by_id = {entity.entity_id: entity for entity in result.entities}
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    summary = result.summary
    estimated_cost = float(summary["estimated_annualized_avoidable_runtime_cost"])
    if estimated_cost > 0:
        cost_text = _currency(estimated_cost, currency)
    else:
        cost_text = "Not calculated (set --cost-per-invocation to enable)"

    lines: list[str] = []
    lines.append("# Software Intelligence Waste Diagnostic")
    lines.append("")
    lines.append("## Scope")
    lines.append(f"- Repository: `{Path(repo_path).resolve()}`")
    lines.append(f"- Generated at: `{generated_at}`")
    lines.append(f"- Runtime window: `{time_window_days}` days")
    lines.append("")

    lines.append("## Executive Truth Summary")
    lines.append(
        f"- Functions scanned: **{int(summary['functions_scanned'])}**"
    )
    lines.append(
        f"- Probable AI-generated functions: **{int(summary['probable_ai_functions'])}**"
    )
    lines.append(
        f"- High-confidence duplicate pairs: **{int(summary['high_confidence_duplication_pairs'])}**"
    )
    lines.append(
        f"- Probable AI functions with zero runtime invocations: **{int(summary['probable_ai_zero_invocations'])}**"
    )
    lines.append(
        f"- Git provenance coverage: **{int(summary['git_evidence_available'])}**"
    )
    lines.append(f"- Estimated annualized avoidable runtime cost: **{cost_text}**")
    lines.append("")

    trend = history_context.get("trend") if history_context else None
    previous_scanned_at = (
        str(history_context["previous_scanned_at"])
        if history_context and history_context.get("previous_scanned_at")
        else None
    )
    if trend and previous_scanned_at:
        lines.append("## Trend vs Previous Run")
        lines.append(f"- Previous run: `{previous_scanned_at}`")
        lines.append(
            f"- Functions scanned delta: **{int(trend['functions_scanned_delta']):+d}**"
        )
        lines.append(
            f"- Probable AI functions delta: **{int(trend['probable_ai_functions_delta']):+d}**"
        )
        lines.append(
            "- High-confidence duplicate pairs delta: "
            f"**{int(trend['high_confidence_duplication_pairs_delta']):+d}**"
        )
        lines.append(
            f"- Runtime zero-invocation delta: **{int(trend['runtime_zero_invocations_delta']):+d}**"
        )
        lines.append(
            "- Estimated annualized avoidable runtime cost delta: "
            f"**{_currency(float(trend['estimated_annualized_avoidable_runtime_cost_delta']), currency)}**"
        )
        lines.append("")

    lines.append("## Waste Taxonomy Mapping")
    lines.append("| Category | Instances | Economic signal |")
    lines.append("| --- | ---: | --- |")
    lines.append(
        f"| Structural duplication | {int(summary['high_confidence_duplication_pairs'])} | Consolidation may reduce repeated execution and maintenance. |"
    )
    lines.append(
        f"| Runtime unused paths | {int(summary['runtime_zero_invocations'])} | Unused paths carry maintenance burden without runtime value. |"
    )
    lines.append(
        f"| Probable AI + runtime unused | {int(summary['probable_ai_zero_invocations'])} | Candidate area for delete/consolidate review. |"
    )
    lines.append(
        f"| Runtime ambiguity | {int(summary['runtime_unknown'])} | No decision without mapped runtime evidence. |"
    )
    lines.append("")

    lines.append("## Evidence Snapshots")
    if not result.findings:
        lines.append("- No high-confidence findings met report thresholds.")
    else:
        for index, finding in enumerate(result.findings[:20], start=1):
            lines.append(f"{index}. **{finding.title}**")
            lines.append(f"   - Type: `{finding.finding_type}`")
            lines.append(f"   - Severity: `{finding.severity}`")
            if finding.entity_ids:
                refs = ", ".join(
                    f"`{_entity_reference(entity_by_id, entity_id)}`"
                    for entity_id in finding.entity_ids
                )
                lines.append(f"   - Entities: {refs}")
            if finding.evidence:
                evidence_text = "; ".join(finding.evidence)
                lines.append(f"   - Evidence: {evidence_text}")
            if finding.estimated_annual_cost is not None:
                lines.append(
                    f"   - Estimated annual cost: {_currency(finding.estimated_annual_cost, currency)}"
                )
    lines.append("")

    lines.append("## Method Constraints")
    lines.append("- Diagnostic only: no code mutation, no auto-refactor.")
    lines.append("- AI provenance is heuristic probability, not authorship proof.")
    lines.append("- Runtime mapping is best-effort; ambiguous mappings stay unresolved.")

    return "\n".join(lines) + "\n"
