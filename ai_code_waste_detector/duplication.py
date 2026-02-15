from __future__ import annotations

import ast
import copy
from difflib import SequenceMatcher

from .models import CodeEntity, DuplicationPair


class _CanonicalizeTransformer(ast.NodeTransformer):
    def visit_arg(self, node: ast.arg) -> ast.arg:
        node.arg = "arg"
        return node

    def visit_Name(self, node: ast.Name) -> ast.Name:
        node.id = "var"
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.Attribute:
        self.generic_visit(node)
        node.attr = "attr"
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        if isinstance(node.value, str):
            return ast.copy_location(ast.Constant(value="STR"), node)
        if isinstance(node.value, (int, float, complex)):
            return ast.copy_location(ast.Constant(value=0), node)
        return node


def _first_function_node(source: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    try:
        module = ast.parse(source)
    except SyntaxError:
        return None

    for statement in module.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return statement
    return None


def _normalized_signature(
    entity: CodeEntity, min_body_statements: int
) -> str | None:
    function_node = _first_function_node(entity.source)
    if function_node is None:
        return None
    if len(function_node.body) < min_body_statements:
        return None

    canonical = copy.deepcopy(function_node)
    transformed = _CanonicalizeTransformer().visit(canonical)
    ast.fix_missing_locations(transformed)
    return ast.dump(transformed, include_attributes=False)


def detect_duplication_pairs(
    entities: list[CodeEntity],
    high_threshold: float = 0.9,
    medium_threshold: float = 0.75,
    include_medium: bool = False,
    min_body_statements: int = 3,
) -> list[DuplicationPair]:
    signatures: dict[str, str] = {}
    for entity in entities:
        signature = _normalized_signature(
            entity, min_body_statements=min_body_statements
        )
        if signature:
            signatures[entity.entity_id] = signature

    results: list[DuplicationPair] = []
    entity_ids = list(signatures.keys())
    for index_a in range(len(entity_ids)):
        for index_b in range(index_a + 1, len(entity_ids)):
            entity_a = entity_ids[index_a]
            entity_b = entity_ids[index_b]
            ratio = SequenceMatcher(
                None, signatures[entity_a], signatures[entity_b]
            ).ratio()

            confidence = None
            if ratio >= high_threshold:
                confidence = "high"
            elif include_medium and ratio >= medium_threshold:
                confidence = "medium"

            if confidence is not None:
                results.append(
                    DuplicationPair(
                        entity_a=entity_a,
                        entity_b=entity_b,
                        semantic_overlap=round(ratio, 3),
                        confidence=confidence,
                    )
                )

    results.sort(key=lambda item: item.semantic_overlap, reverse=True)
    return results
