from app.core.logger import get_logger
from app.services.github.github_client import GITHUB_API_BASE_URL, github_get

logger = get_logger(__name__)

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
        response = github_get(url, timeout=REQUEST_TIMEOUT)
    except RuntimeError as exc:
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


def get_repository_commits(
    owner: str,
    repo: str,
    *,
    limit: int = 20,
    collection_status: dict | None = None,
) -> list[dict]:
    """Collect recent repository commits and their changed files, within a cap."""
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("Repository owner is required.")
    if not isinstance(repo, str) or not repo.strip():
        raise ValueError("Repository name is required.")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("Commit limit must be a positive integer.")

    owner, repo = owner.strip(), repo.strip()
    limit = min(limit, 99)
    status = collection_status if collection_status is not None else {}
    status.update({"limit_reached": False, "partial": False, "failed_file_details": 0})
    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/commits"
    try:
        response = github_get(url, params={"per_page": limit + 1, "page": 1}, timeout=(5, 60))
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("GitHub returned invalid repository commit data.") from exc
    if not isinstance(data, list):
        raise RuntimeError("GitHub returned an unexpected repository commit response.")

    selected = data[:limit]
    status["limit_reached"] = len(data) > limit
    commits = []
    for item in selected:
        if not isinstance(item, dict) or not isinstance(item.get("sha"), str):
            continue
        commit_data = item.get("commit") if isinstance(item.get("commit"), dict) else {}
        author = commit_data.get("author") if isinstance(commit_data.get("author"), dict) else {}
        user = item.get("author") if isinstance(item.get("author"), dict) else {}
        commit = {
            "repository": f"{owner}/{repo}",
            "sha": item["sha"],
            "message": commit_data.get("message"),
            "author": user.get("login") or author.get("name"),
            "date": author.get("date"),
            "html_url": item.get("html_url"),
            "changed_files": [],
        }
        try:
            details = get_commit_details(owner, repo, item["sha"])
            commit["changed_files"] = details["changed_files"]
            commit["author"] = details.get("author") or commit["author"]
            commit["date"] = details.get("date") or commit["date"]
        except (RuntimeError, ValueError) as exc:
            status["partial"] = True
            status["failed_file_details"] += 1
            logger.warning("Changed files unavailable for commit %s in %s/%s: %s", item["sha"][:8], owner, repo, exc)
        commits.append(commit)

    return commits
