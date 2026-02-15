from __future__ import annotations

import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import CodeEntity, GitProvenanceEvidence

_BLAME_HEADER_RE = re.compile(r"^[0-9a-f]{40}\s+\d+\s+\d+(?:\s+\d+)?$")


@dataclass(frozen=True)
class _FileGitHistory:
    commit_count: int
    author_count: int


def _run_git(repo_root: Path, args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return None

    if completed.returncode != 0:
        return None
    return completed.stdout


def _is_git_repo(repo_root: Path) -> bool:
    output = _run_git(repo_root, ["rev-parse", "--is-inside-work-tree"])
    if output is None:
        return False
    return output.strip().lower() == "true"


def _load_file_history(repo_root: Path, file_path: str) -> _FileGitHistory:
    output = _run_git(
        repo_root,
        ["log", "--follow", "--format=%H|%an", "--", file_path],
    )
    if output is None or not output.strip():
        return _FileGitHistory(commit_count=0, author_count=0)

    commits: set[str] = set()
    authors: set[str] = set()
    for line in output.splitlines():
        parts = line.split("|", 1)
        if len(parts) != 2:
            continue
        commit_hash, author_name = parts
        if commit_hash:
            commits.add(commit_hash)
        if author_name:
            authors.add(author_name)
    return _FileGitHistory(commit_count=len(commits), author_count=len(authors))


def _load_blame_metrics(
    repo_root: Path,
    file_path: str,
    start_line: int,
    end_line: int,
) -> tuple[int, int, float, int] | None:
    output = _run_git(
        repo_root,
        [
            "blame",
            "--line-porcelain",
            "-L",
            f"{start_line},{end_line}",
            "--",
            file_path,
        ],
    )
    if output is None or not output.strip():
        return None

    line_commits: list[str] = []
    line_authors: list[str] = []
    line_times: list[int] = []

    current_commit: str | None = None
    current_author: str | None = None
    current_author_time: int | None = None

    for raw_line in output.splitlines():
        line = raw_line.rstrip("\n")
        if _BLAME_HEADER_RE.match(line):
            current_commit = line.split(" ", 1)[0]
            current_author = None
            current_author_time = None
            continue

        if line.startswith("author "):
            current_author = line.removeprefix("author ").strip()
            continue

        if line.startswith("author-time "):
            value = line.removeprefix("author-time ").strip()
            try:
                current_author_time = int(value)
            except ValueError:
                current_author_time = None
            continue

        if line.startswith("\t"):
            if current_commit is not None:
                line_commits.append(current_commit)
            if current_author is not None:
                line_authors.append(current_author)
            if current_author_time is not None:
                line_times.append(current_author_time)

    if not line_commits:
        return None

    commit_counter = Counter(line_commits)
    dominant_commit_lines = max(commit_counter.values())
    concentration = dominant_commit_lines / len(line_commits)
    last_author_time = max(line_times) if line_times else 0
    now_epoch = int(datetime.now(timezone.utc).timestamp())
    age_days = max((now_epoch - last_author_time) // 86_400, 0) if last_author_time else 0
    return (
        len(set(line_commits)),
        len(set(line_authors)),
        round(concentration, 3),
        age_days,
    )


def collect_git_evidence(
    repo_root: str | Path,
    entities: list[CodeEntity],
) -> dict[str, GitProvenanceEvidence]:
    root = Path(repo_root).resolve()
    if not _is_git_repo(root):
        return {}

    by_file: dict[str, list[CodeEntity]] = {}
    for entity in entities:
        by_file.setdefault(entity.file_path, []).append(entity)

    evidence: dict[str, GitProvenanceEvidence] = {}

    for file_path, file_entities in by_file.items():
        file_history = _load_file_history(root, file_path)

        for entity in file_entities:
            blame_metrics = _load_blame_metrics(
                root,
                file_path,
                entity.lineno,
                entity.end_lineno,
            )
            if blame_metrics is None:
                evidence[entity.entity_id] = GitProvenanceEvidence(
                    entity_id=entity.entity_id,
                    available=False,
                    file_commit_count=file_history.commit_count,
                    file_author_count=file_history.author_count,
                )
                continue

            commit_count, author_count, concentration, age_days = blame_metrics
            evidence[entity.entity_id] = GitProvenanceEvidence(
                entity_id=entity.entity_id,
                available=True,
                blame_commit_count=commit_count,
                blame_author_count=author_count,
                line_commit_concentration=concentration,
                last_commit_age_days=age_days,
                file_commit_count=file_history.commit_count,
                file_author_count=file_history.author_count,
            )

    return evidence
