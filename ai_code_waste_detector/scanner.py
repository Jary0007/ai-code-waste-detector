from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path

from .models import CodeEntity

IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
}


def _module_name_from_path(relative_file_path: str) -> str:
    normalized = relative_file_path.replace("\\", "/")
    if normalized.endswith(".py"):
        normalized = normalized[:-3]
    parts = [part for part in normalized.split("/") if part]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _slice_source(source_text: str, lineno: int, end_lineno: int) -> str:
    lines = source_text.splitlines()
    start_index = max(lineno - 1, 0)
    end_index = min(end_lineno, len(lines))
    return "\n".join(lines[start_index:end_index])


class _FunctionCollector(ast.NodeVisitor):
    def __init__(self, file_path: str, module_name: str, source_text: str) -> None:
        self.file_path = file_path
        self.module_name = module_name
        self.source_text = source_text
        self.class_stack: list[str] = []
        self.entities: list[CodeEntity] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record_function(node)
        self.generic_visit(node)

    def _record_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified_parts: list[str] = []
        if self.module_name:
            qualified_parts.append(self.module_name)
        qualified_parts.extend(self.class_stack)
        qualified_parts.append(node.name)
        qualified_name = ".".join(qualified_parts)

        end_lineno = getattr(node, "end_lineno", node.lineno)
        source = ast.get_source_segment(self.source_text, node)
        if source is None:
            source = _slice_source(self.source_text, node.lineno, end_lineno)

        raw_key = f"{self.file_path}:{qualified_name}:{node.lineno}"
        entity_id = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:12]

        self.entities.append(
            CodeEntity(
                entity_id=entity_id,
                file_path=self.file_path,
                function_name=node.name,
                qualified_name=qualified_name,
                lineno=node.lineno,
                end_lineno=end_lineno,
                source=source,
            )
        )


def iter_python_files(repo_path: str | Path, include_tests: bool = False) -> list[Path]:
    root = Path(repo_path)
    discovered: list[Path] = []
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [directory for directory in dirs if directory not in IGNORED_DIRS]
        if not include_tests:
            dirs[:] = [directory for directory in dirs if directory != "tests"]
        current_path = Path(current_root)
        for filename in files:
            if filename.endswith(".py"):
                discovered.append(current_path / filename)
    return discovered


def extract_entities(repo_path: str | Path, include_tests: bool = False) -> list[CodeEntity]:
    root = Path(repo_path).resolve()
    entities: list[CodeEntity] = []

    for file_path in iter_python_files(root, include_tests=include_tests):
        relative = str(file_path.resolve().relative_to(root))
        source_text = file_path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(source_text)
        except SyntaxError:
            continue

        collector = _FunctionCollector(
            file_path=relative,
            module_name=_module_name_from_path(relative),
            source_text=source_text,
        )
        collector.visit(tree)
        entities.extend(collector.entities)

    entities.sort(key=lambda entity: (entity.file_path, entity.lineno))
    return entities
