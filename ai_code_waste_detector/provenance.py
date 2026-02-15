from __future__ import annotations

import ast

from .models import AIProvenanceSignal, CodeEntity

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


def _score_entity(entity: CodeEntity, threshold: float) -> AIProvenanceSignal | None:
    function_node = _first_function_node(entity.source)
    if function_node is None:
        return None

    score = 0.0
    signals: list[str] = []

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

    score = min(round(score, 2), 0.99)
    if score < threshold:
        return None

    confidence = "high" if score >= 0.8 else "medium"
    return AIProvenanceSignal(
        entity_id=entity.entity_id,
        ai_probability=score,
        confidence=confidence,
        signals=signals,
    )


def detect_ai_signals(
    entities: list[CodeEntity], threshold: float = 0.65
) -> list[AIProvenanceSignal]:
    output: list[AIProvenanceSignal] = []
    for entity in entities:
        signal = _score_entity(entity, threshold=threshold)
        if signal is not None:
            output.append(signal)
    return output
