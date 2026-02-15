from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .models import Finding

_TREND_KEYS = (
    "functions_scanned",
    "probable_ai_functions",
    "high_confidence_duplication_pairs",
    "runtime_zero_invocations",
    "probable_ai_zero_invocations",
    "estimated_annualized_avoidable_runtime_cost",
)


def _repo_key(repo_path: str | Path) -> str:
    return str(Path(repo_path).resolve()).lower()


def _connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _initialize_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_key TEXT NOT NULL,
            repo_path TEXT NOT NULL,
            scanned_at TEXT NOT NULL,
            functions_scanned INTEGER NOT NULL,
            probable_ai_functions INTEGER NOT NULL,
            high_confidence_duplication_pairs INTEGER NOT NULL,
            runtime_zero_invocations INTEGER NOT NULL,
            probable_ai_zero_invocations INTEGER NOT NULL,
            estimated_annualized_avoidable_runtime_cost REAL NOT NULL,
            ai_threshold REAL NOT NULL,
            dup_threshold REAL NOT NULL,
            min_dup_body_statements INTEGER NOT NULL,
            min_dup_signature_chars INTEGER NOT NULL,
            include_tests INTEGER NOT NULL,
            git_provenance_enabled INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS finding_counts (
            run_id INTEGER NOT NULL,
            finding_type TEXT NOT NULL,
            finding_count INTEGER NOT NULL,
            PRIMARY KEY (run_id, finding_type),
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_runs_repo_key_id ON runs(repo_key, id)"
    )
    _ensure_column(connection, "runs", "min_dup_signature_chars", "INTEGER NOT NULL DEFAULT 160")
    _ensure_column(connection, "runs", "git_provenance_enabled", "INTEGER NOT NULL DEFAULT 1")


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    columns = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    existing = {str(row["name"]) for row in columns}
    if column_name in existing:
        return
    connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _to_int(value: float | int | str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_float(value: float | int | str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def record_run(
    db_path: str | Path,
    repo_path: str | Path,
    summary: dict[str, float | int | str],
    findings: list[Finding],
    config: dict[str, float | int | bool],
) -> dict[str, object]:
    repo_key = _repo_key(repo_path)
    resolved_repo = str(Path(repo_path).resolve())
    scanned_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    connection = _connect(db_path)
    try:
        _initialize_schema(connection)
        cursor = connection.execute(
            """
            INSERT INTO runs (
                repo_key,
                repo_path,
                scanned_at,
                functions_scanned,
                probable_ai_functions,
                high_confidence_duplication_pairs,
                runtime_zero_invocations,
                probable_ai_zero_invocations,
                estimated_annualized_avoidable_runtime_cost,
                ai_threshold,
                dup_threshold,
                min_dup_body_statements,
                min_dup_signature_chars,
                include_tests,
                git_provenance_enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                repo_key,
                resolved_repo,
                scanned_at,
                _to_int(summary.get("functions_scanned", 0)),
                _to_int(summary.get("probable_ai_functions", 0)),
                _to_int(summary.get("high_confidence_duplication_pairs", 0)),
                _to_int(summary.get("runtime_zero_invocations", 0)),
                _to_int(summary.get("probable_ai_zero_invocations", 0)),
                _to_float(summary.get("estimated_annualized_avoidable_runtime_cost", 0.0)),
                float(config.get("ai_threshold", 0.65)),
                float(config.get("dup_threshold", 0.9)),
                int(config.get("min_dup_body_statements", 3)),
                int(config.get("min_dup_signature_chars", 160)),
                int(bool(config.get("include_tests", False))),
                int(bool(config.get("git_provenance_enabled", True))),
            ),
        )
        run_id = int(cursor.lastrowid)

        finding_counts = Counter(finding.finding_type for finding in findings)
        for finding_type, finding_count in finding_counts.items():
            connection.execute(
                """
                INSERT INTO finding_counts (run_id, finding_type, finding_count)
                VALUES (?, ?, ?)
                """,
                (run_id, finding_type, int(finding_count)),
            )

        previous_row = connection.execute(
            """
            SELECT
                id,
                scanned_at,
                functions_scanned,
                probable_ai_functions,
                high_confidence_duplication_pairs,
                runtime_zero_invocations,
                probable_ai_zero_invocations,
                estimated_annualized_avoidable_runtime_cost
            FROM runs
            WHERE repo_key = ? AND id < ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (repo_key, run_id),
        ).fetchone()
        connection.commit()
    finally:
        connection.close()

    trend: dict[str, float | int] | None = None
    previous_scanned_at: str | None = None
    previous_run_id: int | None = None
    if previous_row is not None:
        previous_run_id = int(previous_row["id"])
        previous_scanned_at = str(previous_row["scanned_at"])
        trend = {}
        for key in _TREND_KEYS:
            current_value = _to_float(summary.get(key, 0.0))
            previous_value = _to_float(previous_row[key])
            delta = current_value - previous_value
            if key != "estimated_annualized_avoidable_runtime_cost":
                trend[f"{key}_delta"] = int(delta)
            else:
                trend[f"{key}_delta"] = round(delta, 2)

    return {
        "run_id": run_id,
        "scanned_at": scanned_at,
        "previous_run_id": previous_run_id,
        "previous_scanned_at": previous_scanned_at,
        "trend": trend,
    }
