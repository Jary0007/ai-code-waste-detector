from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import CodeEntity, RuntimeEvidence


def _coerce_record(value: Any) -> tuple[int | None, str | None] | None:
    if isinstance(value, int):
        return value, None
    if isinstance(value, float):
        return int(value), None
    if isinstance(value, dict):
        invocations_raw = value.get("invocations", value.get("count"))
        if invocations_raw is None:
            return None
        try:
            invocations = int(invocations_raw)
        except (TypeError, ValueError):
            return None
        last_invoked_at = value.get("last_invoked_at")
        if last_invoked_at is not None:
            last_invoked_at = str(last_invoked_at)
        return invocations, last_invoked_at
    return None


def load_runtime_index(runtime_path: str | Path | None) -> dict[str, tuple[int, str | None]]:
    if runtime_path is None:
        return {}

    content = Path(runtime_path).read_text(encoding="utf-8")
    data = json.loads(content)
    index: dict[str, tuple[int, str | None]] = {}

    if isinstance(data, dict):
        if isinstance(data.get("functions"), dict):
            for key, value in data["functions"].items():
                coerced = _coerce_record(value)
                if coerced is not None:
                    index[str(key)] = coerced
        else:
            for key, value in data.items():
                coerced = _coerce_record(value)
                if coerced is not None:
                    index[str(key)] = coerced
    elif isinstance(data, list):
        for row in data:
            if not isinstance(row, dict):
                continue
            name = row.get("name") or row.get("qualified_name") or row.get("function")
            if not name:
                continue
            coerced = _coerce_record(row)
            if coerced is not None:
                index[str(name)] = coerced

    return index


def map_runtime_evidence(
    entities: list[CodeEntity],
    runtime_index: dict[str, tuple[int, str | None]],
) -> dict[str, RuntimeEvidence]:
    mapped: dict[str, RuntimeEvidence] = {}
    runtime_available = bool(runtime_index)

    for entity in entities:
        record = runtime_index.get(entity.qualified_name)
        if record is None:
            record = runtime_index.get(entity.function_name)

        if record is not None:
            mapped[entity.entity_id] = RuntimeEvidence(
                entity_id=entity.entity_id,
                invocation_count=record[0],
                last_invoked_at=record[1],
                source="runtime-file",
            )
            continue

        mapped[entity.entity_id] = RuntimeEvidence(
            entity_id=entity.entity_id,
            invocation_count=None,
            last_invoked_at=None,
            source="runtime-unmapped" if runtime_available else "runtime-unavailable",
        )

    return mapped
