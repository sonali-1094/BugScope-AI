from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlsplit

from pydantic import ValidationError

from app.normalization.models import (
    ChangedFileRecord,
    CollectionRunRecord,
    CommitRecord,
    IssueRecord,
    NormalizedAnalysis,
    PullRequestRecord,
    RelationshipEvidence,
    RelationshipRecord,
    RepositoryRecord,
)

_REPOSITORY_PART = re.compile(r"^[A-Za-z0-9_.-]+$")
_COMMIT_SHA = re.compile(r"^[0-9a-fA-F]{40,64}$")


class NormalizationError(ValueError):
    """The response lacks the repository identity needed to scope records."""


def repository_key(value: Any) -> tuple[str, str, str] | None:
    """Return (stable lower-case key, owner, repo) for a GitHub full name."""
    if not isinstance(value, str):
        return None
    parts = value.strip().strip("/").split("/")
    if len(parts) != 2 or not all(_REPOSITORY_PART.fullmatch(part) for part in parts):
        return None
    owner, name = parts
    if owner in {".", ".."} or name in {".", ".."}:
        return None
    return f"{owner.casefold()}/{name.casefold()}", owner, name


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _source_url(value: Any, path: str, warnings: list[str]) -> str | None:
    text = _text(value)
    if text is None:
        return None
    try:
        parsed = urlsplit(text)
    except ValueError:
        parsed = None
    if parsed is None or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        warnings.append(f"{path}: ignored malformed source URL.")
        return None
    return text


def _utc_datetime(value: Any, path: str, warnings: list[str]) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        else:
            raise ValueError("timestamp must be a string or datetime")
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timestamp is missing a UTC offset")
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        warnings.append(f"{path}: ignored invalid or timezone-naive timestamp.")
        return None


def _optional_count(value: Any, path: str, warnings: list[str]) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        warnings.append(f"{path}: ignored invalid non-negative integer.")
        return None
    return value


def _optional_bool(value: Any, path: str, warnings: list[str]) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        warnings.append(f"{path}: ignored invalid boolean.")
        return None
    return value


def _valid_state(value: Any, path: str, warnings: list[str]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        warnings.append(f"{path}: ignored malformed state; expected 'open' or 'closed'.")
        return None
    if value not in {"open", "closed"}:
        warnings.append(f"{path}: ignored unsupported state.")
        return None
    return value


def _as_rows(value: Any, path: str, warnings: list[str], *, missing_is_warning: bool = True) -> list:
    if isinstance(value, list):
        return value
    if value is None and not missing_is_warning:
        return []
    warnings.append(f"{path}: expected a list; treated as empty.")
    return []


def _file_id(repository: str, source_type: str, source_id: str, path: str) -> str:
    return (
        f"{repository}#file:{source_type}:"
        f"{quote(source_id, safe='')}:{quote(path, safe='')}"
    )


def _relationship_id(repository: str, relation_type: str, source_id: str, target_id: str) -> str:
    return (
        f"{repository}#edge:{relation_type}:"
        f"{quote(source_id, safe='')}->{quote(target_id, safe='')}"
    )


class _Normalizer:
    def __init__(self, source: dict[str, Any]):
        self.source = source
        self.warnings: list[str] = []
        self.duplicates_merged = 0
        self.repo = self._repository()
        self.issues: dict[str, dict[str, Any]] = {}
        self.pull_requests: dict[str, dict[str, Any]] = {}
        self.commits: dict[str, dict[str, Any]] = {}
        self.changed_files: dict[str, dict[str, Any]] = {}
        self.relationships: dict[str, dict[str, Any]] = {}
        self._issue_by_key: set[str] = set()
        self._pull_by_number: dict[int, dict[str, Any]] = {}
        self._repository_validation: dict[str, bool] = {}

    @property
    def repository_key(self) -> str:
        return self.repo["repository_key"]

    def _record_repository_matches(self, raw: dict[str, Any], path: str) -> bool:
        """Reject an explicitly supplied repository that cannot be safely scoped."""
        if path in self._repository_validation:
            return self._repository_validation[path]
        if "repository" not in raw:
            self._repository_validation[path] = True
            return True
        parsed = repository_key(raw.get("repository"))
        if parsed is None:
            self.warnings.append(f"{path}: skipped record with malformed repository identity.")
            self._repository_validation[path] = False
            return False
        if parsed[0] != self.repository_key:
            self.warnings.append(
                f"{path}: skipped record for repository {parsed[1]}/{parsed[2]}; "
                f"analysis repository is {self.repo['full_name']}."
            )
            self._repository_validation[path] = False
            return False
        self._repository_validation[path] = True
        return True

    def _repository(self) -> dict[str, Any]:
        metadata = self.source.get("repository_details")
        metadata = metadata if isinstance(metadata, dict) else {}
        parsed = repository_key(metadata.get("full_name")) or repository_key(self.source.get("repository"))
        if parsed is None:
            raise NormalizationError("Analysis response must contain a valid owner/repository identifier.")

        key, owner, name = parsed
        canonical_url = _source_url(
            metadata.get("html_url") or self.source.get("repository_url"),
            "repository.source_url",
            self.warnings,
        )
        values = {
            "repository_key": key,
            "owner": owner,
            "name": name,
            "full_name": f"{owner}/{name}",
            "canonical_url": canonical_url,
            "description": _text(metadata.get("description")),
            "primary_language": _text(metadata.get("primary_language")),
            "visibility": _text(metadata.get("visibility")),
            "is_private": _optional_bool(metadata.get("is_private"), "repository.is_private", self.warnings),
            "default_branch": _text(metadata.get("default_branch")),
            "stars": _optional_count(metadata.get("stars"), "repository.stars", self.warnings),
            "forks": _optional_count(metadata.get("forks"), "repository.forks", self.warnings),
            "open_issues_count": _optional_count(
                metadata.get("open_issues_count"), "repository.open_issues_count", self.warnings
            ),
            "source_url": canonical_url,
        }
        return RepositoryRecord.model_validate(values).model_dump(mode="python")

    def _append_unique(self, bucket: dict[str, dict[str, Any]], record: dict[str, Any], kind: str) -> None:
        record_id = record["entity_id"]
        previous = bucket.get(record_id)
        if previous is None:
            bucket[record_id] = record
            return

        self.duplicates_merged += 1
        for field, value in record.items():
            old = previous.get(field)
            if old == value or value is None:
                continue
            if old is None:
                previous[field] = value
                continue
            if isinstance(old, list) and isinstance(value, list):
                for item in value:
                    if item not in old:
                        old.append(item)
                continue
            self.warnings.append(
                f"{kind} {record_id}: conflicting {field}; kept the first non-missing value."
            )

    def _add_issue(self, raw: Any, index: int) -> None:
        path = f"issues[{index}]"
        if not isinstance(raw, dict):
            self.warnings.append(f"{path}: skipped non-object record.")
            return
        number = raw.get("issue_number", raw.get("number"))
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            self.warnings.append(f"{path}: skipped record with invalid issue number.")
            return
        labels_value = raw.get("labels")
        labels: list[str] = []
        if isinstance(labels_value, list):
            for label in labels_value:
                if isinstance(label, str) and label.strip():
                    if label.strip() not in labels:
                        labels.append(label.strip())
        elif labels_value is not None:
            self.warnings.append(f"{path}.labels: ignored malformed labels.")
        entity_id = f"{self.repository_key}#issue:{number}"
        values = {
            "entity_id": entity_id,
            "repository_key": self.repository_key,
            "number": number,
            "title": _text(raw.get("title")),
            "body": _text(raw.get("description", raw.get("body"))),
            "state": _valid_state(raw.get("state"), f"{path}.state", self.warnings),
            "created_at": _utc_datetime(raw.get("created_at"), f"{path}.created_at", self.warnings),
            "closed_at": _utc_datetime(raw.get("closed_at"), f"{path}.closed_at", self.warnings),
            "labels": labels,
            "author": _text(raw.get("author")),
            "comments": _optional_count(raw.get("comments"), f"{path}.comments", self.warnings),
            "source_url": _source_url(raw.get("html_url"), f"{path}.html_url", self.warnings),
        }
        try:
            record = IssueRecord.model_validate(values).model_dump(mode="python")
        except ValidationError as exc:
            self.warnings.append(f"{path}: skipped invalid issue ({exc.errors()[0]['type']}).")
            return
        self._append_unique(self.issues, record, "issue")
        self._issue_by_key.add(entity_id)

    def _add_pull_request(self, raw: Any, index: int) -> None:
        path = f"pull_requests[{index}]"
        if not isinstance(raw, dict):
            self.warnings.append(f"{path}: skipped non-object record.")
            return
        if not self._record_repository_matches(raw, path):
            return
        number = raw.get("number")
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            self.warnings.append(f"{path}: skipped record with invalid pull-request number.")
            return
        entity_id = f"{self.repository_key}#pull:{number}"
        values = {
            "entity_id": entity_id,
            "repository_key": self.repository_key,
            "number": number,
            "title": _text(raw.get("title")),
            "body": _text(raw.get("description", raw.get("body"))),
            "state": _valid_state(raw.get("state"), f"{path}.state", self.warnings),
            "merged": _optional_bool(raw.get("merged"), f"{path}.merged", self.warnings),
            "merged_at": _utc_datetime(raw.get("merged_at"), f"{path}.merged_at", self.warnings),
            "created_at": _utc_datetime(raw.get("created_at"), f"{path}.created_at", self.warnings),
            "updated_at": _utc_datetime(raw.get("updated_at"), f"{path}.updated_at", self.warnings),
            "author": _text(raw.get("author")),
            "commits_count": _optional_count(raw.get("commits_count"), f"{path}.commits_count", self.warnings),
            "changed_files_count": _optional_count(
                raw.get("changed_files_count"), f"{path}.changed_files_count", self.warnings
            ),
            "source_url": _source_url(raw.get("html_url"), f"{path}.html_url", self.warnings),
        }
        try:
            record = PullRequestRecord.model_validate(values).model_dump(mode="python")
        except ValidationError as exc:
            self.warnings.append(f"{path}: skipped invalid pull request ({exc.errors()[0]['type']}).")
            return
        self._append_unique(self.pull_requests, record, "pull request")
        self._pull_by_number[number] = self.pull_requests[entity_id]

    def _add_commit(self, raw: Any, path: str, source_endpoint: str, source_url: Any = None) -> str | None:
        if not isinstance(raw, dict):
            self.warnings.append(f"{path}: skipped non-object commit.")
            return None
        if not self._record_repository_matches(raw, path):
            return None
        sha = raw.get("sha") or raw.get("commit_sha")
        if not isinstance(sha, str) or not _COMMIT_SHA.fullmatch(sha.strip()):
            self.warnings.append(f"{path}: skipped commit with invalid SHA.")
            return None
        sha = sha.casefold()
        entity_id = f"{self.repository_key}#commit:{sha}"
        endpoints = [source_endpoint]
        values = {
            "entity_id": entity_id,
            "repository_key": self.repository_key,
            "sha": sha,
            "message": _text(raw.get("message")),
            "author": _text(raw.get("author")),
            "authored_at": _utc_datetime(raw.get("date", raw.get("authored_at")), f"{path}.date", self.warnings),
            "source_endpoints": endpoints,
            "source_url": _source_url(source_url or raw.get("html_url"), f"{path}.html_url", self.warnings),
        }
        try:
            record = CommitRecord.model_validate(values).model_dump(mode="python")
        except ValidationError as exc:
            self.warnings.append(f"{path}: skipped invalid commit ({exc.errors()[0]['type']}).")
            return None
        self._append_unique(self.commits, record, "commit")
        return entity_id

    def _add_changed_file(
        self,
        raw: Any,
        *,
        source_type: str,
        source_id: str,
        source_endpoint: str,
        source_url: str | None,
        path: str,
    ) -> str | None:
        if isinstance(raw, str):
            raw = {"filename": raw}
        if not isinstance(raw, dict):
            self.warnings.append(f"{path}: skipped non-object changed-file record.")
            return None
        filename = _text(raw.get("filename", raw.get("path")))
        if filename is None:
            self.warnings.append(f"{path}: skipped changed-file record with no path.")
            return None
        entity_id = _file_id(self.repository_key, source_type, source_id, filename)
        values = {
            "entity_id": entity_id,
            "repository_key": self.repository_key,
            "source_entity_type": source_type,
            "source_entity_id": source_id,
            "path": filename,
            "status": _text(raw.get("status")),
            "additions": _optional_count(raw.get("additions"), f"{path}.additions", self.warnings),
            "deletions": _optional_count(raw.get("deletions"), f"{path}.deletions", self.warnings),
            "source_endpoint": source_endpoint,
            "source_url": source_url,
        }
        try:
            record = ChangedFileRecord.model_validate(values).model_dump(mode="python")
        except ValidationError as exc:
            self.warnings.append(f"{path}: skipped invalid changed-file record ({exc.errors()[0]['type']}).")
            return None
        self._append_unique(self.changed_files, record, "changed file")
        return entity_id

    def _add_relationship(
        self,
        *,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        target_repository_key: str,
        relation_type: str,
        evidence: dict[str, Any],
    ) -> None:
        entity_id = _relationship_id(self.repository_key, relation_type, source_id, target_id)
        evidence_model = RelationshipEvidence.model_validate(evidence).model_dump(mode="python")
        values = {
            "entity_id": entity_id,
            "repository_key": self.repository_key,
            "source_entity_type": source_type,
            "source_entity_id": source_id,
            "target_entity_type": target_type,
            "target_entity_id": target_id,
            "target_repository_key": target_repository_key,
            "relation_type": relation_type,
            "evidence": [evidence_model],
        }
        self._append_unique(self.relationships, values, "relationship")

    def _add_issue_reference(
        self,
        raw: Any,
        *,
        source_id: str | None,
        source_type: str,
        source_url: str | None,
        path: str,
    ) -> None:
        if not isinstance(raw, dict):
            self.warnings.append(f"{path}: skipped malformed issue reference.")
            return
        number = raw.get("issue_number")
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            self.warnings.append(f"{path}: skipped issue reference with invalid number.")
            return
        target_repo = repository_key(raw.get("repository"))
        target_repo_key = target_repo[0] if target_repo else self.repository_key
        if raw.get("repository") is not None and target_repo is None:
            self.warnings.append(f"{path}: ignored invalid referenced repository; used analysis repository context.")
        source_commit_sha = raw.get("source_commit_sha")
        if isinstance(source_commit_sha, str) and _COMMIT_SHA.fullmatch(source_commit_sha):
            source_id = f"{self.repository_key}#commit:{source_commit_sha.casefold()}"
            source_type = "commit"
        if source_id is None:
            self.warnings.append(f"{path}: skipped reference with no source record.")
            return
        target_id = f"{target_repo_key}#issue:{number}"
        text = _text(raw.get("evidence"))
        self._add_relationship(
            source_type=source_type,
            source_id=source_id,
            target_type="issue",
            target_id=target_id,
            target_repository_key=target_repo_key,
            relation_type="explicitly_references_issue",
            evidence={
                "kind": "explicit_text",
                "source_endpoint": f"github.{_text(raw.get('source')) or 'issue_reference'}",
                "source_url": source_url,
                "source_field": _text(raw.get("source")),
                "text": text,
                "source_commit_sha": source_commit_sha if isinstance(source_commit_sha, str) else None,
                "target_in_collection": _optional_bool(
                    raw.get("target_in_collected_issues"),
                    f"{path}.target_in_collected_issues",
                    self.warnings,
                ),
                "source_pull_request_merged": _optional_bool(
                    raw.get("source_pull_request_merged"),
                    f"{path}.source_pull_request_merged",
                    self.warnings,
                ),
            },
        )

    def _add_file_edge(
        self,
        *,
        source_type: str,
        source_id: str,
        file_id: str,
        relation_type: str,
        endpoint: str,
        source_url: str | None,
    ) -> None:
        self._add_relationship(
            source_type=source_type,
            source_id=source_id,
            target_type="changed_file",
            target_id=file_id,
            target_repository_key=self.repository_key,
            relation_type=relation_type,
            evidence={
                "kind": "github_api",
                "source_endpoint": endpoint,
                "source_url": source_url,
            },
        )

    def run(self) -> NormalizedAnalysis:
        issue_rows = self.source.get("issues")
        if not isinstance(issue_rows, list):
            issue_rows = self.source.get("bugs")
        for index, raw in enumerate(_as_rows(issue_rows, "issues", self.warnings)):
            self._add_issue(raw, index)

        for index, raw in enumerate(_as_rows(self.source.get("pull_requests"), "pull_requests", self.warnings)):
            self._add_pull_request(raw, index)

        commit_rows = _as_rows(self.source.get("commits"), "commits", self.warnings)
        for index, raw in enumerate(commit_rows):
            self._add_commit(raw, f"commits[{index}]", "github.repository_commits")

        relationship_rows = _as_rows(self.source.get("relationships"), "relationships", self.warnings)
        for index, relationship in enumerate(relationship_rows):
            if not isinstance(relationship, dict):
                self.warnings.append(f"relationships[{index}]: skipped non-object record.")
                continue
            if not self._record_repository_matches(relationship, f"relationships[{index}]"):
                continue
            pr_number = relationship.get("pull_request_number")
            if (
                isinstance(pr_number, bool)
                or not isinstance(pr_number, int)
                or pr_number <= 0
                or pr_number not in self._pull_by_number
            ):
                continue
            commits = _as_rows(relationship.get("commits"), f"relationships[{index}].commits", self.warnings, missing_is_warning=False)
            for commit_index, raw_commit in enumerate(commits):
                self._add_commit(
                    raw_commit,
                    f"relationships[{index}].commits[{commit_index}]",
                    "github.pull_request_commits",
                    source_url=None,
                )

        # Changed-file observations and confirmed PR/commit membership edges.
        for index, raw_commit in enumerate(commit_rows):
            if not isinstance(raw_commit, dict):
                continue
            if not self._record_repository_matches(raw_commit, f"commits[{index}]"):
                continue
            sha = raw_commit.get("sha")
            if not isinstance(sha, str) or not _COMMIT_SHA.fullmatch(sha):
                continue
            source_id = f"{self.repository_key}#commit:{sha.casefold()}"
            source_url = _source_url(raw_commit.get("html_url"), f"commits[{index}].html_url", self.warnings)
            files = _as_rows(raw_commit.get("changed_files"), f"commits[{index}].changed_files", self.warnings, missing_is_warning=False)
            for file_index, raw_file in enumerate(files):
                file_id = self._add_changed_file(
                    raw_file,
                    source_type="commit",
                    source_id=source_id,
                    source_endpoint="github.commit_details_files",
                    source_url=source_url,
                    path=f"commits[{index}].changed_files[{file_index}]",
                )
                if file_id:
                    self._add_file_edge(
                        source_type="commit",
                        source_id=source_id,
                        file_id=file_id,
                        relation_type="commit_changes_file",
                        endpoint="github.commit_details_files",
                        source_url=source_url,
                    )
            for ref_index, raw_ref in enumerate(_as_rows(raw_commit.get("issue_references"), f"commits[{index}].issue_references", self.warnings, missing_is_warning=False)):
                self._add_issue_reference(
                    raw_ref,
                    source_id=source_id,
                    source_type="commit",
                    source_url=source_url,
                    path=f"commits[{index}].issue_references[{ref_index}]",
                )

        for index, raw_relationship in enumerate(relationship_rows):
            if not isinstance(raw_relationship, dict):
                continue
            if not self._record_repository_matches(raw_relationship, f"relationships[{index}]"):
                continue
            pr_number = raw_relationship.get("pull_request_number")
            if isinstance(pr_number, bool) or not isinstance(pr_number, int) or pr_number <= 0:
                self.warnings.append(f"relationships[{index}]: skipped record with invalid PR number.")
                continue
            pull_id = f"{self.repository_key}#pull:{pr_number}"
            if pr_number not in self._pull_by_number:
                self.warnings.append(f"relationships[{index}]: PR #{pr_number} has no matching pull_requests record.")
                continue
            pull_source_url = self._pull_by_number.get(pr_number, {}).get("source_url")

            for commit_index, raw_commit in enumerate(_as_rows(raw_relationship.get("commits"), f"relationships[{index}].commits", self.warnings, missing_is_warning=False)):
                if not isinstance(raw_commit, dict):
                    continue
                if not self._record_repository_matches(
                    raw_commit, f"relationships[{index}].commits[{commit_index}]"
                ):
                    continue
                sha = raw_commit.get("commit_sha") or raw_commit.get("sha")
                if not isinstance(sha, str) or not _COMMIT_SHA.fullmatch(sha):
                    self.warnings.append(f"relationships[{index}].commits[{commit_index}]: skipped invalid commit SHA.")
                    continue
                sha = sha.casefold()
                commit_id = f"{self.repository_key}#commit:{sha}"
                self._add_relationship(
                    source_type="pull_request",
                    source_id=pull_id,
                    target_type="commit",
                    target_id=commit_id,
                    target_repository_key=self.repository_key,
                    relation_type="pull_request_contains_commit",
                    evidence={
                        "kind": "github_api",
                        "source_endpoint": "github.pull_request_commits",
                        "source_url": pull_source_url,
                    },
                )
                for file_index, raw_file in enumerate(_as_rows(raw_commit.get("changed_files"), f"relationships[{index}].commits[{commit_index}].changed_files", self.warnings, missing_is_warning=False)):
                    file_id = self._add_changed_file(
                        raw_file,
                        source_type="commit",
                        source_id=commit_id,
                        source_endpoint="github.commit_details_files",
                        source_url=None,
                        path=f"relationships[{index}].commits[{commit_index}].changed_files[{file_index}]",
                    )
                    if file_id:
                        self._add_file_edge(
                            source_type="commit",
                            source_id=commit_id,
                            file_id=file_id,
                            relation_type="commit_changes_file",
                            endpoint="github.commit_details_files",
                            source_url=None,
                        )

            detail_rows = raw_relationship.get("changed_file_details")
            if not isinstance(detail_rows, list):
                detail_rows = raw_relationship.get("changed_files")
            for file_index, raw_file in enumerate(_as_rows(detail_rows, f"relationships[{index}].changed_files", self.warnings, missing_is_warning=False)):
                file_id = self._add_changed_file(
                    raw_file,
                    source_type="pull_request",
                    source_id=pull_id,
                    source_endpoint="github.pull_request_files",
                    source_url=pull_source_url,
                    path=f"relationships[{index}].changed_files[{file_index}]",
                )
                if file_id:
                    self._add_file_edge(
                        source_type="pull_request",
                        source_id=pull_id,
                        file_id=file_id,
                        relation_type="pull_request_changes_file",
                        endpoint="github.pull_request_files",
                        source_url=pull_source_url,
                    )

            for ref_index, raw_ref in enumerate(_as_rows(raw_relationship.get("issue_references"), f"relationships[{index}].issue_references", self.warnings, missing_is_warning=False)):
                if not isinstance(raw_ref, dict):
                    self.warnings.append(f"relationships[{index}].issue_references[{ref_index}]: skipped malformed reference.")
                    continue
                ref_source = raw_ref.get("source")
                if ref_source == "commit_message":
                    source_sha = raw_ref.get("source_commit_sha")
                    source_id = (
                        f"{self.repository_key}#commit:{source_sha.casefold()}"
                        if isinstance(source_sha, str) and _COMMIT_SHA.fullmatch(source_sha)
                        else None
                    )
                    source_type = "commit"
                else:
                    source_id = pull_id
                    source_type = "pull_request"
                self._add_issue_reference(
                    raw_ref,
                    source_id=source_id,
                    source_type=source_type,
                    source_url=pull_source_url,
                    path=f"relationships[{index}].issue_references[{ref_index}]",
                )

        collection = self.source.get("collection")
        collection = collection if isinstance(collection, dict) else None
        if self.source.get("collection") is not None and collection is None:
            self.warnings.append("collection: ignored malformed stage metadata.")
        raw_counts = self.source.get("counts")
        counts: dict[str, int] | None = None
        if isinstance(raw_counts, dict):
            counts = {}
            for name, value in raw_counts.items():
                if isinstance(name, str) and isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    counts[name] = value
                else:
                    self.warnings.append(f"counts.{name}: ignored invalid count.")
        elif raw_counts is not None:
            self.warnings.append("counts: ignored malformed count metadata.")

        source_status = self.source.get("status")
        if source_status is not None and (
            not isinstance(source_status, str) or source_status not in {"complete", "partial"}
        ):
            self.warnings.append("status: ignored malformed or unsupported collection status.")
            source_status = None
        warnings = self.source.get("warnings")
        if warnings is not None and not isinstance(warnings, list):
            self.warnings.append("warnings: ignored malformed collector warnings.")
            warnings = None
        empty_results = self.source.get("empty_results")
        if empty_results is not None and not isinstance(empty_results, list):
            self.warnings.append("empty_results: ignored malformed empty-stage list.")
            empty_results = None
        failed = self.source.get("failed_pull_requests")
        if failed is not None and not isinstance(failed, list):
            self.warnings.append("failed_pull_requests: ignored malformed failure list.")
            failed = None
        skipped = self.source.get("skipped_pull_requests")
        if isinstance(skipped, bool) or (skipped is not None and (not isinstance(skipped, int) or skipped < 0)):
            self.warnings.append("skipped_pull_requests: ignored invalid count.")
            skipped = None

        run = CollectionRunRecord.model_validate({
            "run_id": str(uuid.uuid4()),
            "repository_key": self.repository_key,
            "status": source_status,
            "counts": counts,
            "stages": collection,
            "warnings": warnings,
            "empty_results": empty_results,
            "failed_pull_requests": failed,
            "skipped_pull_requests": skipped,
        })

        return NormalizedAnalysis(
            repository=RepositoryRecord.model_validate(self.repo),
            issues=[IssueRecord.model_validate(row) for row in self.issues.values()],
            pull_requests=[PullRequestRecord.model_validate(row) for row in self.pull_requests.values()],
            commits=[CommitRecord.model_validate(row) for row in self.commits.values()],
            changed_files=[ChangedFileRecord.model_validate(row) for row in self.changed_files.values()],
            relationships=[RelationshipRecord.model_validate(row) for row in self.relationships.values()],
            collection_run=run,
            normalization_warnings=self.warnings,
            duplicate_records_merged=self.duplicates_merged,
        )


def normalize_analysis(analysis: Any) -> NormalizedAnalysis:
    """Convert one existing /api/repositories/analyze response to normalized records.

    The function is pure: it performs no GitHub requests, database writes, or
    mutation of the input mapping. Use ``model_dump(mode="json")`` to hand the
    validated result to a future persistence or Phase 4 adapter.
    """
    if not isinstance(analysis, dict):
        raise NormalizationError("Analysis response must be an object.")
    return _Normalizer(analysis).run()
