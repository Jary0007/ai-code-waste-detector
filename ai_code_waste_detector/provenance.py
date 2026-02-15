from __future__ import annotations

import ast
import re

from .models import AIProvenanceSignal, CodeEntity, GitProvenanceEvidence

GENERIC_VARIABLE_NAMES = {
    "data",
    "input",
    "output",
    "result",
    "value",
    "item",
    "obj",
    "response",
    "request",
    "temp",
    "payload",
}

_SCRIPT_DECLARATION_RE = re.compile(
    r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)
_SCRIPT_STRING_RE = re.compile(
    r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`',
    re.MULTILINE | re.DOTALL,
)
_SCRIPT_COMMENT_RE = re.compile(
    r"//.*?$|/\*.*?\*/",
    re.MULTILINE | re.DOTALL,
)


def _first_function_node(source: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    try:
        module = ast.parse(source)
    except SyntaxError:
        return None

    for statement in module.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return statement
    return None


def _statement_count(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    return len(function_node.body)


def _guard_clause_count(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    guard_count = 0
    for statement in function_node.body[:6]:
        if not isinstance(statement, ast.If):
            break
        if len(statement.body) != 1:
            break
        if isinstance(statement.body[0], (ast.Return, ast.Raise)):
            guard_count += 1
    return guard_count


def _variable_name_ratio(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> float:
    variable_names: list[str] = []
    for node in ast.walk(function_node):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            variable_names.append(node.id.lower())

    if not variable_names:
        return 0.0

    generic_count = sum(1 for name in variable_names if name in GENERIC_VARIABLE_NAMES)
    return generic_count / len(variable_names)


def _defensive_density(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> float:
    total_statements = max(_statement_count(function_node), 1)
    if_count = sum(1 for node in ast.walk(function_node) if isinstance(node, ast.If))
    return if_count / total_statements


def _repetitive_error_messages(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    error_like: list[str] = []
    for node in ast.walk(function_node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            lowered = node.value.lower()
            if "error" in lowered or "invalid" in lowered or "fail" in lowered:
                error_like.append(lowered)
    return len(error_like) >= 2 and len(set(error_like)) <= (len(error_like) // 2 + 1)


def _generic_return_pattern(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if not function_node.body:
        return False
    last_statement = function_node.body[-1]
    if not isinstance(last_statement, ast.Return):
        return False
    if not isinstance(last_statement.value, ast.Name):
        return False
    return last_statement.value.id.lower() in GENERIC_VARIABLE_NAMES


def _apply_git_adjustments(
    score: float,
    signals: list[str],
    git_evidence: GitProvenanceEvidence | None,
) -> float:
    if git_evidence is None or not git_evidence.available:
        return score

    concentration = git_evidence.line_commit_concentration or 0.0
    blame_commit_count = git_evidence.blame_commit_count or 0
    blame_author_count = git_evidence.blame_author_count or 0
    last_age_days = git_evidence.last_commit_age_days or 0
    file_commit_count = git_evidence.file_commit_count or 0
    file_author_count = git_evidence.file_author_count or 0

    if concentration >= 0.85 and blame_commit_count <= 2:
        score += 0.1
        signals.append("single-source commit concentration")
    if last_age_days <= 45 and blame_commit_count <= 3:
        score += 0.05
        signals.append("recent introduction window")
    if file_author_count <= 1 and file_commit_count <= 3:
        score += 0.05
        signals.append("low-author diversity file")

    if blame_commit_count >= 6:
        score -= 0.1
    if blame_author_count >= 3:
        score -= 0.1
    if last_age_days >= 365:
        score -= 0.05

    return score


def _score_entity(
    entity: CodeEntity,
    threshold: float,
    git_evidence: GitProvenanceEvidence | None,
) -> AIProvenanceSignal | None:
    function_node = _first_function_node(entity.source)
    score = 0.0
    signals: list[str] = []

    if function_node is not None:
        guard_count = _guard_clause_count(function_node)
        if guard_count >= 3:
            score += 0.25
            signals.append("uniform guard clauses")

        variable_ratio = _variable_name_ratio(function_node)
        if variable_ratio >= 0.6:
            score += 0.2
            signals.append("generic variable naming")

        defensive_density = _defensive_density(function_node)
        if defensive_density >= 0.4 and _statement_count(function_node) >= 4:
            score += 0.2
            signals.append("high defensive branch density")

        if _repetitive_error_messages(function_node):
            score += 0.15
            signals.append("repetitive error messaging")

        if _generic_return_pattern(function_node):
            score += 0.15
            signals.append("generic return pipeline")

        if _statement_count(function_node) >= 12 and not any(
            isinstance(node, (ast.For, ast.While, ast.Try)) for node in ast.walk(function_node)
        ):
            score += 0.1
            signals.append("long boilerplate flow")
    else:
        guard_count = _script_guard_clause_count(entity.source)
        if guard_count >= 3:
            score += 0.25
            signals.append("uniform guard clauses")

        variable_ratio = _script_variable_name_ratio(entity.source)
        if variable_ratio >= 0.6:
            score += 0.2
            signals.append("generic variable naming")

        statement_count = _script_statement_count(entity.source)
        defensive_density = _script_defensive_density(entity.source, statement_count)
        if defensive_density >= 0.35 and statement_count >= 4:
            score += 0.2
            signals.append("high defensive branch density")

        if _script_repetitive_error_messages(entity.source):
            score += 0.15
            signals.append("repetitive error messaging")

        if _script_generic_return_pattern(entity.source):
            score += 0.15
            signals.append("generic return pipeline")

        if statement_count >= 12 and not re.search(r"\b(for|while)\b", entity.source):
            score += 0.1
            signals.append("long boilerplate flow")

    score = _apply_git_adjustments(score, signals, git_evidence)
    score = min(max(round(score, 2), 0.0), 0.99)
    if score < threshold:
        return None

    confidence = "high" if score >= 0.8 else "medium"
    return AIProvenanceSignal(
        entity_id=entity.entity_id,
        ai_probability=score,
        confidence=confidence,
        signals=signals,
    )


def _strip_script_comments(source: str) -> str:
    return _SCRIPT_COMMENT_RE.sub("", source)


def _script_statement_count(source: str) -> int:
    cleaned = _strip_script_comments(source)
    count = cleaned.count(";")
    count += len(re.findall(r"\b(if|for|while|return|throw|switch|catch)\b", cleaned))
    return max(count, 1)


def _script_guard_clause_count(source: str) -> int:
    cleaned = _strip_script_comments(source)
    guard_matches = re.findall(
        r"\bif\s*\([^)]*\)\s*\{[^{}]*\b(?:return|throw)\b[^{}]*\}",
        cleaned,
        flags=re.DOTALL,
    )
    return len(guard_matches)


def _script_variable_name_ratio(source: str) -> float:
    names = [name.lower() for name in _SCRIPT_DECLARATION_RE.findall(source)]
    if not names:
        return 0.0
    generic_count = sum(1 for name in names if name in GENERIC_VARIABLE_NAMES)
    return generic_count / len(names)


def _script_defensive_density(source: str, statement_count: int) -> float:
    if_count = len(re.findall(r"\bif\s*\(", source))
    return if_count / max(statement_count, 1)


def _script_repetitive_error_messages(source: str) -> bool:
    strings: list[str] = []
    for match in _SCRIPT_STRING_RE.findall(source):
        value = match[1:-1].lower()
        if "error" in value or "invalid" in value or "fail" in value:
            strings.append(value)
    return len(strings) >= 2 and len(set(strings)) <= (len(strings) // 2 + 1)


def _script_generic_return_pattern(source: str) -> bool:
    matches = re.findall(r"\breturn\s+([A-Za-z_$][\w$]*)\s*;", source)
    if not matches:
        return False
    return matches[-1].lower() in GENERIC_VARIABLE_NAMES


def detect_ai_signals(
    entities: list[CodeEntity],
    threshold: float = 0.65,
    git_evidence_by_entity: dict[str, GitProvenanceEvidence] | None = None,
) -> list[AIProvenanceSignal]:
    output: list[AIProvenanceSignal] = []
    for entity in entities:
        git_evidence = None
        if git_evidence_by_entity is not None:
            git_evidence = git_evidence_by_entity.get(entity.entity_id)

        signal = _score_entity(
            entity,
            threshold=threshold,
            git_evidence=git_evidence,
        )
        if signal is not None:
            output.append(signal)
    return output
