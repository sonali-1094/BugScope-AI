import requests

from app.core.logger import get_logger
from app.services.github.github_client import get_github_headers

logger = get_logger(__name__)

GITHUB_API_BASE_URL = "https://api.github.com"
REQUEST_TIMEOUT = (5, 20)


def get_commit_details(
    owner: str,
    repo: str,
    commit_sha: str
) -> dict:
    """
    Retrieve commit metadata and changed-file details.
    """

    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("Repository owner is required.")

    if not isinstance(repo, str) or not repo.strip():
        raise ValueError("Repository name is required.")

    if not isinstance(commit_sha, str) or not commit_sha.strip():
        raise ValueError("Commit SHA is required.")

    owner = owner.strip()
    repo = repo.strip()
    commit_sha = commit_sha.strip()

    url = (
        f"{GITHUB_API_BASE_URL}/repos/"
        f"{owner}/{repo}/commits/{commit_sha}"
    )

    logger.info(
        "Fetching commit %s for %s/%s",
        commit_sha[:8],
        owner,
        repo
    )

    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers=get_github_headers()
        )
        response.raise_for_status()

    except requests.exceptions.RequestException as exc:
        logger.error(
            "Unable to retrieve commit %s for %s/%s",
            commit_sha[:8],
            owner,
            repo
        )
        raise RuntimeError(
            "Unable to retrieve commit details from GitHub."
        ) from exc

    try:
        commit = response.json()

        commit_metadata = commit["commit"]
        author_data = commit_metadata.get("author") or {}

        changed_files = []

        for file_info in commit.get("files") or []:
            if not isinstance(file_info, dict):
                continue

            filename = file_info.get("filename")

            if not isinstance(filename, str) or not filename.strip():
                continue

            changed_files.append({
                "filename": filename,
                "status": file_info.get("status"),
                "additions": file_info.get("additions", 0),
                "deletions": file_info.get("deletions", 0)
            })

        result = {
            "sha": commit["sha"],
            "message": commit_metadata.get("message"),
            "author": author_data.get("name"),
            "date": author_data.get("date"),
            "changed_files": changed_files
        }

    except (ValueError, KeyError, TypeError) as exc:
        logger.error(
            "Invalid commit response for %s/%s, SHA %s",
            owner,
            repo,
            commit_sha[:8]
        )
        raise RuntimeError(
            "GitHub returned invalid commit details."
        ) from exc

    logger.info(
        "Retrieved commit %s with %s changed files",
        commit_sha[:8],
        len(changed_files)
    )

    return result