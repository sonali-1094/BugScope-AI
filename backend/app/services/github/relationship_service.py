import os
import re

from app.core.logger import get_logger
from app.services.github.github_client import GITHUB_API_BASE_URL, github_get
from app.services.github.pull_request_service import (
    get_pull_request_files,
    get_repository_pull_requests,
)
logger = get_logger(__name__)

CLOSING_REFERENCE = re.compile(
    r"\b(fixes?|closes?|resolves?)\s+"
    r"((?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#\d+)\b",
    re.IGNORECASE,
)


def extract_issue_references(text: str | None, repository: str, source: str, sha: str | None = None) -> list[dict]:
    """Extract explicit GitHub closing references; bare issue numbers are ignored."""
    if not isinstance(text, str):
        return []
    references = []
    for match in CLOSING_REFERENCE.finditer(text):
        raw_target = match.group(2)
        if "/" in raw_target:
            target_repository, issue_number = raw_target.rsplit("#", 1)
        else:
            target_repository, issue_number = repository, raw_target[1:]
        reference = {
            "repository": target_repository,
            "issue_number": int(issue_number),
            "relationship": "explicit_closing_reference",
            "source": source,
            "evidence": match.group(0),
        }
        if sha:
            reference["source_commit_sha"] = sha
        references.append(reference)
    return references


def build_pull_request_relationship(
    pull_request: dict,
    commits: list[dict],
    pull_request_files: list[dict] | None = None,
) -> dict:
    """
    Build a structured relationship between a pull request,
    its commits, and the files changed in those commits.

    The caller must supply commits that actually belong
    to the specified pull request.
    """

    if not isinstance(pull_request, dict):
        raise ValueError("pull_request must be a dictionary")

    if not isinstance(commits, list):
        raise ValueError("commits must be a list")

    pr_number = pull_request.get("number")

    if not isinstance(pr_number, int) or isinstance(pr_number, bool):
        raise ValueError("Pull request must have a valid number")

    commit_relationships = []
    changed_files = set()
    repository = pull_request.get("repository")
    issue_references = []

    for commit in commits:
        if not isinstance(commit, dict):
            continue

        sha = commit.get("sha")

        if not isinstance(sha, str) or not sha.strip():
            continue

        files = commit.get("changed_files", commit.get("files", []))

        if not isinstance(files, list):
            files = []

        commit_files = []

        for file_info in files:
            if not isinstance(file_info, dict):
                continue

            filename = file_info.get("filename")

            if not isinstance(filename, str) or not filename.strip():
                continue

            commit_files.append({
                "filename": filename,
                "status": file_info.get("status"),
                "additions": file_info.get("additions", 0),
                "deletions": file_info.get("deletions", 0)
            })

            changed_files.add(filename)

        commit_relationships.append({
            "commit_sha": sha,
            "message": commit.get("message"),
            "author": commit.get("author"),
            "date": commit.get("date"),
            "changed_files": commit_files
        })
        if isinstance(repository, str):
            issue_references.extend(
                extract_issue_references(
                    commit.get("message"), repository, "commit_message", sha
                )
            )

    if pull_request_files is not None:
        changed_files = {
            file_info["filename"]
            for file_info in pull_request_files
            if isinstance(file_info, dict)
            and isinstance(file_info.get("filename"), str)
            and file_info["filename"].strip()
        }

    description = pull_request.get("description")
    if isinstance(repository, str):
        issue_references.extend(
            extract_issue_references(description, repository, "pull_request_description")
        )

    result = {
        "pull_request_number": pr_number,
        "repository": repository,
        "pull_request_title": pull_request.get("title"),
        "pull_request_state": pull_request.get("state"),
        "merged_at": pull_request.get("merged_at"),
        "commits": commit_relationships,
        "changed_files": sorted(changed_files)
    }
    result["issue_references"] = issue_references

    logger.info(
        "Built relationship data for PR #%s: %s commits, %s unique files",
        pr_number,
        len(commit_relationships),
        len(changed_files)
    )

    return result

def get_pull_request_commits(
    owner: str,
    repo: str,
    pull_number: int
) -> list[dict]:
    """
    Retrieve commit references associated with a GitHub pull request.
    """

    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("Repository owner is required.")

    if not isinstance(repo, str) or not repo.strip():
        raise ValueError("Repository name is required.")

    if (
        not isinstance(pull_number, int)
        or isinstance(pull_number, bool)
        or pull_number < 1
    ):
        raise ValueError("Pull request number must be positive.")

    owner = owner.strip()
    repo = repo.strip()

    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/pulls/{pull_number}/commits"

    commits = []
    page = 1
    per_page = 100

    logger.info(
        "Fetching commits for PR #%s in %s/%s",
        pull_number,
        owner,
        repo
    )

    while True:
        try:
            response = github_get(
                url,
                params={
                    "per_page": per_page,
                    "page": page
                },
                timeout=(5, 60),
            )
        except RuntimeError as exc:
            logger.error(
                "Unable to retrieve commits for PR #%s in %s/%s",
                pull_number,
                owner,
                repo
            )
            raise RuntimeError(
                "Unable to retrieve pull-request commits from GitHub."
            ) from exc

        try:
            data = response.json()

        except ValueError as exc:
            raise RuntimeError(
                "GitHub returned invalid commit data."
            ) from exc

        if not isinstance(data, list):
            raise RuntimeError(
                "GitHub returned an unexpected commit response."
            )

        if not data:
            break

        for commit in data:
            if not isinstance(commit, dict):
                continue

            sha = commit.get("sha")
            commit_data = commit.get("commit")

            if not isinstance(sha, str) or not isinstance(commit_data, dict):
                continue

            commits.append({
                "sha": sha,
                "message": commit_data.get("message"),
                "author": (commit_data.get("author") or {}).get("name"),
                "date": (commit_data.get("author") or {}).get("date"),
            })

        if len(data) < per_page:
            break

        page += 1

    logger.info(
        "Retrieved %s commits for PR #%s in %s/%s",
        len(commits),
        pull_number,
        owner,
        repo
    )
    return commits

def collect_pull_request_relationships(
    owner: str,
    repo: str,
    pull_requests: list[dict] | None = None,
    collection_status: dict | None = None,
) -> dict:
    """
    Collect commit and changed-file relationships for pull requests.

    Reuses pull-request metadata when it is supplied by the caller.
    """

    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("Repository owner is required.")

    if not isinstance(repo, str) or not repo.strip():
        raise ValueError("Repository name is required.")

    owner = owner.strip()
    repo = repo.strip()

    logger.info(
        "Starting relationship collection for %s/%s",
        owner,
        repo
    )

    if pull_requests is None:
        pull_requests = get_repository_pull_requests(owner, repo)

    if not isinstance(pull_requests, list):
        raise ValueError("Pull requests must be provided as a list.")

    try:
        relationship_limit = max(1, int(os.getenv("BUGSCOPE_MAX_RELATIONSHIP_PRS", "10")))
    except ValueError:
        relationship_limit = 10

    selected_pull_requests = pull_requests[:relationship_limit]
    skipped_pull_requests = len(pull_requests) - len(selected_pull_requests)
    relationships = []
    failed_pull_requests = []
    files_truncated = 0
    partial_file_requests = 0

    for pull_request in selected_pull_requests:
        if not isinstance(pull_request, dict):
            continue

        pull_number = pull_request.get("number")

        if (
            not isinstance(pull_number, int)
            or isinstance(pull_number, bool)
            or pull_number < 1
        ):
            logger.warning(
                "Skipping pull request with invalid number in %s/%s",
                owner,
                repo
            )
            continue

        try:
            commit_references = get_pull_request_commits(
                owner,
                repo,
                pull_number
            )

            file_status = {}
            changed_files = get_pull_request_files(
                owner,
                repo,
                pull_number,
                collection_status=file_status,
            )
            if file_status.get("limit_reached"):
                files_truncated += 1
            if file_status.get("partial"):
                partial_file_requests += 1

            relationship = build_pull_request_relationship(pull_request, commit_references, changed_files)
            relationship["repository"] = f"{owner}/{repo}"
            for issue_reference in relationship["issue_references"]:
                if issue_reference["repository"].casefold() == f"{owner}/{repo}".casefold():
                    issue_reference["source_pull_request_merged"] = bool(pull_request.get("merged"))

            relationships.append(relationship)

        except (RuntimeError, ValueError) as exc:
            logger.warning(
                "Unable to collect relationships for PR #%s: %s",
                pull_number,
                exc
            )

            failed_pull_requests.append({
                "pull_request_number": pull_number,
                "error": str(exc)
            })

    logger.info(
        "Relationship collection finished for %s/%s: "
        "%s successful, %s failed, %s skipped",
        owner,
        repo,
        len(relationships),
        len(failed_pull_requests),
        skipped_pull_requests,
    )

    if collection_status is not None:
        collection_status.update({
            "limit_reached": skipped_pull_requests > 0,
            "partial": bool(failed_pull_requests or files_truncated or partial_file_requests),
            "files_truncated": files_truncated,
            "partial_file_requests": partial_file_requests,
        })
    return {
        "relationships": relationships,
        "failed_pull_requests": failed_pull_requests,
        "skipped_pull_requests": skipped_pull_requests,
    }
