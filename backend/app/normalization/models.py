from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class NormalizedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RepositoryRecord(NormalizedModel):
    repository_key: str
    owner: str
    name: str
    full_name: str
    canonical_url: str | None = None
    description: str | None = None
    primary_language: str | None = None
    visibility: str | None = None
    is_private: bool | None = None
    default_branch: str | None = None
    stars: int | None = Field(default=None, ge=0)
    forks: int | None = Field(default=None, ge=0)
    open_issues_count: int | None = Field(default=None, ge=0)
    source_system: Literal["github"] = "github"
    source_endpoint: str = "github.repository"
    source_url: str | None = None


class IssueRecord(NormalizedModel):
    entity_id: str
    repository_key: str
    number: int = Field(gt=0)
    title: str | None = None
    body: str | None = None
    state: Literal["open", "closed"] | None = None
    created_at: datetime | None = None
    closed_at: datetime | None = None
    labels: list[str] = Field(default_factory=list)
    author: str | None = None
    comments: int | None = Field(default=None, ge=0)
    source_system: Literal["github"] = "github"
    source_endpoint: str = "github.repository_issues"
    source_url: str | None = None


class PullRequestRecord(NormalizedModel):
    entity_id: str
    repository_key: str
    number: int = Field(gt=0)
    title: str | None = None
    body: str | None = None
    state: Literal["open", "closed"] | None = None
    merged: bool | None = None
    merged_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    author: str | None = None
    commits_count: int | None = Field(default=None, ge=0)
    changed_files_count: int | None = Field(default=None, ge=0)
    source_system: Literal["github"] = "github"
    source_endpoint: str = "github.pull_requests"
    source_url: str | None = None


class CommitRecord(NormalizedModel):
    entity_id: str
    repository_key: str
    sha: str = Field(pattern=r"^[0-9a-fA-F]{40,64}$")
    message: str | None = None
    author: str | None = None
    authored_at: datetime | None = None
    source_system: Literal["github"] = "github"
    source_endpoints: list[str] = Field(default_factory=list)
    source_url: str | None = None


class ChangedFileRecord(NormalizedModel):
    entity_id: str
    repository_key: str
    source_entity_type: Literal["commit", "pull_request"]
    source_entity_id: str
    path: str = Field(min_length=1)
    status: str | None = None
    additions: int | None = Field(default=None, ge=0)
    deletions: int | None = Field(default=None, ge=0)
    source_system: Literal["github"] = "github"
    source_endpoint: str
    source_url: str | None = None


class RelationshipEvidence(NormalizedModel):
    kind: Literal["github_api", "explicit_text", "inference"]
    source_endpoint: str
    source_url: str | None = None
    source_field: str | None = None
    text: str | None = None
    source_commit_sha: str | None = None
    target_in_collection: bool | None = None
    source_pull_request_merged: bool | None = None


class RelationshipRecord(NormalizedModel):
    entity_id: str
    repository_key: str
    source_entity_type: Literal["pull_request", "commit"]
    source_entity_id: str
    target_entity_type: Literal["commit", "changed_file", "issue"]
    target_entity_id: str
    target_repository_key: str
    relation_type: Literal[
        "pull_request_contains_commit",
        "pull_request_changes_file",
        "commit_changes_file",
        "explicitly_references_issue",
        "inferred_candidate",
    ]
    evidence: list[RelationshipEvidence] = Field(default_factory=list)


class CollectionRunRecord(NormalizedModel):
    # The current API has no run ID or collection timestamps. These stay None
    # until a source response actually provides them.
    run_id: str | None = None
    repository_key: str
    status: Literal["complete", "partial"] | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    stages: dict[str, dict[str, Any]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    empty_results: list[str] = Field(default_factory=list)
    failed_pull_requests: list[dict[str, Any]] = Field(default_factory=list)
    skipped_pull_requests: int = Field(default=0, ge=0)


class NormalizedAnalysis(NormalizedModel):
    repository: RepositoryRecord
    issues: list[IssueRecord] = Field(default_factory=list)
    pull_requests: list[PullRequestRecord] = Field(default_factory=list)
    commits: list[CommitRecord] = Field(default_factory=list)
    changed_files: list[ChangedFileRecord] = Field(default_factory=list)
    relationships: list[RelationshipRecord] = Field(default_factory=list)
    collection_run: CollectionRunRecord
    normalization_warnings: list[str] = Field(default_factory=list)
    duplicate_records_merged: int = Field(default=0, ge=0)
