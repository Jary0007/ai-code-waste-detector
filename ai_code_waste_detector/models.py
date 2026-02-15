from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class CodeEntity:
    entity_id: str
    file_path: str
    function_name: str
    qualified_name: str
    lineno: int
    end_lineno: int
    source: str


@dataclass(frozen=True)
class AIProvenanceSignal:
    entity_id: str
    ai_probability: float
    confidence: str
    signals: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GitProvenanceEvidence:
    entity_id: str
    available: bool
    blame_commit_count: Optional[int] = None
    blame_author_count: Optional[int] = None
    line_commit_concentration: Optional[float] = None
    last_commit_age_days: Optional[int] = None
    file_commit_count: Optional[int] = None
    file_author_count: Optional[int] = None


@dataclass(frozen=True)
class DuplicationPair:
    entity_a: str
    entity_b: str
    semantic_overlap: float
    confidence: str


@dataclass(frozen=True)
class RuntimeEvidence:
    entity_id: str
    invocation_count: Optional[int]
    last_invoked_at: Optional[str]
    source: str


@dataclass(frozen=True)
class Finding:
    finding_type: str
    severity: str
    title: str
    entity_ids: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    estimated_annual_cost: Optional[float] = None


@dataclass
class AnalysisResult:
    entities: list[CodeEntity]
    ai_signals: list[AIProvenanceSignal]
    git_evidence: dict[str, GitProvenanceEvidence]
    duplication_pairs: list[DuplicationPair]
    runtime_evidence: dict[str, RuntimeEvidence]
    findings: list[Finding]
    summary: dict[str, float | int | str]
