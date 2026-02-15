from __future__ import annotations

import ast
import hashlib
import os
import re
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

SUPPORTED_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx"}
SCRIPT_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}

_SCRIPT_FUNCTION_PATTERNS = [
    re.compile(
        r"^\s*function\s+(?P<name>[A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{",
        re.MULTILINE,
    ),
    re.compile(
        r"^\s*(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?function\s*\([^)]*\)\s*\{",
        re.MULTILINE,
    ),
    re.compile(
        r"^\s*(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{",
        re.MULTILINE,
    ),
    re.compile(
        r"^\s*(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?[A-Za-z_$][\w$]*\s*=>\s*\{",
        re.MULTILINE,
    ),
]


def _module_name_from_path(relative_file_path: str) -> str:
    normalized = relative_file_path.replace("\\", "/")
    stem, suffix = os.path.splitext(normalized)
    if suffix in SUPPORTED_EXTENSIONS:
        normalized = stem
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


def _build_entity(
    file_path: str,
    qualified_name: str,
    function_name: str,
    lineno: int,
    end_lineno: int,
    source: str,
) -> CodeEntity:
    raw_key = f"{file_path}:{qualified_name}:{lineno}"
    entity_id = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:12]
    return CodeEntity(
        entity_id=entity_id,
        file_path=file_path,
        function_name=function_name,
        qualified_name=qualified_name,
        lineno=lineno,
        end_lineno=end_lineno,
        source=source,
    )


def iter_source_files(repo_path: str | Path, include_tests: bool = False) -> list[Path]:
    root = Path(repo_path)
    discovered: list[Path] = []
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [directory for directory in dirs if directory not in IGNORED_DIRS]
        if not include_tests:
            dirs[:] = [directory for directory in dirs if directory != "tests"]
        current_path = Path(current_root)
        for filename in files:
            if Path(filename).suffix in SUPPORTED_EXTENSIONS:
                discovered.append(current_path / filename)
    return discovered


def _extract_python_entities(
    file_path: str,
    module_name: str,
    source_text: str,
) -> list[CodeEntity]:
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return []

    collector = _FunctionCollector(
        file_path=file_path,
        module_name=module_name,
        source_text=source_text,
    )
    collector.visit(tree)
    return collector.entities


def _find_matching_brace(source_text: str, open_index: int) -> int:
    depth = 0
    in_single = False
    in_double = False
    in_template = False
    in_line_comment = False
    in_block_comment = False
    index = open_index

    while index < len(source_text):
        char = source_text[index]
        next_char = source_text[index + 1] if index + 1 < len(source_text) else ""

        if in_line_comment:
            if char == "\n":
                in_line_comment = False
            index += 1
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                index += 2
                continue
            index += 1
            continue

        if in_single:
            if char == "\\":
                index += 2
                continue
            if char == "'":
                in_single = False
            index += 1
            continue

        if in_double:
            if char == "\\":
                index += 2
                continue
            if char == '"':
                in_double = False
            index += 1
            continue

        if in_template:
            if char == "\\":
                index += 2
                continue
            if char == "`":
                in_template = False
            index += 1
            continue

        if char == "/" and next_char == "/":
            in_line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            in_block_comment = True
            index += 2
            continue

        if char == "'":
            in_single = True
            index += 1
            continue
        if char == '"':
            in_double = True
            index += 1
            continue
        if char == "`":
            in_template = True
            index += 1
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index

        index += 1

    return -1


def _extract_script_entities(
    file_path: str,
    module_name: str,
    source_text: str,
) -> list[CodeEntity]:
    entities: list[CodeEntity] = []
    seen_positions: set[int] = set()

    for pattern in _SCRIPT_FUNCTION_PATTERNS:
        for match in pattern.finditer(source_text):
            start = match.start()
            if start in seen_positions:
                continue
            seen_positions.add(start)

            open_index = source_text.find("{", start, match.end())
            if open_index < 0:
                continue
            close_index = _find_matching_brace(source_text, open_index)
            if close_index < 0:
                continue

            name = match.group("name")
            qualified_name = ".".join(part for part in [module_name, name] if part)
            lineno = source_text.count("\n", 0, start) + 1
            end_lineno = source_text.count("\n", 0, close_index) + 1
            source = source_text[start : close_index + 1]

            entities.append(
                _build_entity(
                    file_path=file_path,
                    qualified_name=qualified_name,
                    function_name=name,
                    lineno=lineno,
                    end_lineno=end_lineno,
                    source=source,
                )
            )

    entities.sort(key=lambda entity: entity.lineno)
    return entities


def extract_entities(repo_path: str | Path, include_tests: bool = False) -> list[CodeEntity]:
    root = Path(repo_path).resolve()
    entities: list[CodeEntity] = []

    for file_path in iter_source_files(root, include_tests=include_tests):
        relative = str(file_path.resolve().relative_to(root))
        source_text = file_path.read_text(encoding="utf-8", errors="ignore")
        module_name = _module_name_from_path(relative)
        suffix = file_path.suffix

        if suffix == ".py":
            entities.extend(
                _extract_python_entities(
                    file_path=relative,
                    module_name=module_name,
                    source_text=source_text,
                )
            )
        elif suffix in SCRIPT_EXTENSIONS:
            entities.extend(
                _extract_script_entities(
                    file_path=relative,
                    module_name=module_name,
                    source_text=source_text,
                )
            )

    entities.sort(key=lambda entity: (entity.file_path, entity.lineno))
    return entities
