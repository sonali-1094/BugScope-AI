import os

from app.core.logger import get_logger
from app.services.github.pull_request_service import (
    get_pull_request_files,
    get_repository_pull_requests,
)
import requests

logger = get_logger(__name__)


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

    if pull_request_files is not None:
        changed_files = {
            file_info["filename"]
            for file_info in pull_request_files
            if isinstance(file_info, dict)
            and isinstance(file_info.get("filename"), str)
            and file_info["filename"].strip()
        }

    result = {
        "pull_request_number": pr_number,
        "pull_request_title": pull_request.get("title"),
        "pull_request_state": pull_request.get("state"),
        "merged_at": pull_request.get("merged_at"),
        "commits": commit_relationships,
        "changed_files": sorted(changed_files)
    }

    logger.info(
        "Built relationship data for PR #%s: %s commits, %s unique files",
        pr_number,
        len(commit_relationships),
        len(changed_files)
    )

    return result

    # GitHub relationship retrival
def get_pull_request_commits(
        owner: str,
        repo: str,
        pull_number: int
    ) -> list[dict]:
    """
       Fetch commits associated with a GitHub pull request.
    """

    if not owner or not repo:
        raise ValueError("Repository owner and name are required.")

    if pull_number < 1:
        raise ValueError("Pull request number must be positive.")

    url = (
        f"https://api.github.com/repos/"
        f"{owner}/{repo}/pulls/{pull_number}/commits"
    )

    logger.info(
        "Fetching commits for PR #%s in %s/%s",
        pull_number,
        owner,
        repo
    )

    try:
        response = requests.get(
            url,
            params={"per_page": 100, "page": 1},
            timeout=(5, 20)
        )
        response.raise_for_status()

    except requests.exceptions.RequestException as exc:
        logger.error(
            "Unable to fetch commits for PR #%s in %s/%s",
            pull_number,
            owner,
            repo
        )
        raise RuntimeError(
            "Unable to retrieve pull-request commits from GitHub."
        ) from exc

    commits = response.json()

    if not isinstance(commits, list):
        raise RuntimeError("GitHub returned an invalid commit list.")

    return [
        {
            "sha": commit["sha"],
            "message": commit.get("commit", {}).get("message")
        }
        for commit in commits
        if isinstance(commit, dict) and commit.get("sha")
    ]

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

    url = (
        f"https://api.github.com/repos/"
        f"{owner}/{repo}/pulls/{pull_number}/commits"
    )

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
            response = requests.get(
                url,
                params={
                    "per_page": per_page,
                    "page": page
                },
                timeout=(5, 20),
                headers={
                    "Accept": "application/vnd.github+json"
                }
            )

        except requests.exceptions.RequestException as exc:
            logger.error(
                "Unable to retrieve commits for PR #%s in %s/%s",
                pull_number,
                owner,
                repo
            )
            raise RuntimeError(
                "Unable to retrieve pull-request commits from GitHub."
            ) from exc

        if response.status_code != 200:
            logger.error(
                "GitHub returned HTTP %s for PR #%s in %s/%s",
                response.status_code,
                pull_number,
                owner,
                repo
            )
            raise RuntimeError(
                f"GitHub commit collection failed with status "
                f"{response.status_code}."
            )

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
                "message": commit_data.get("message")
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
    pull_requests: list[dict] | None = None
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
        relationship_limit = max(
            1,
            int(os.getenv("BUGSCOPE_MAX_RELATIONSHIP_PRS", "10")),
        )
    except ValueError:
        relationship_limit = 25

    selected_pull_requests = pull_requests[:relationship_limit]
    skipped_pull_requests = len(pull_requests) - len(selected_pull_requests)
    relationships = []
    failed_pull_requests = []

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

            changed_files = get_pull_request_files(
                owner,
                repo,
                pull_number,
            )

            relationship = build_pull_request_relationship(
                pull_request,
                commit_references,
                changed_files,
            )

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

    return {
        "relationships": relationships,
        "failed_pull_requests": failed_pull_requests,
        "skipped_pull_requests": skipped_pull_requests,
    }