from app.core.logger import get_logger
from app.services.github.github_client import GITHUB_API_BASE_URL, describe_github_error, github_get

logger = get_logger(__name__)
PER_PAGE = 100
MAX_PAGES = 5
MAX_FILE_PAGES = 10


def get_repository_pull_requests(owner: str, repo: str, collection_status: dict | None = None) -> list[dict]:
    """Retrieve open and closed pull requests across all result pages."""
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("Repository owner is required.")
    if not isinstance(repo, str) or not repo.strip():
        raise ValueError("Repository name is required.")

    owner = owner.strip()
    repo = repo.strip()
    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/pulls"
    pull_requests = []
    page = 1
    status = collection_status if collection_status is not None else {}
    status.update({"limit_reached": False, "partial": False, "failed_page": None, "error": None})

    while page <= MAX_PAGES:
        try:
            response = github_get(
                url,
                params={
                    "state": "all",
                    "per_page": PER_PAGE,
                    "page": page,
                    "sort": "created",
                    "direction": "desc",
                },
                timeout=(5, 60),
            )
        except RuntimeError as exc:
            if pull_requests:
                status["partial"] = True
                status["failed_page"] = page
                status["error"] = describe_github_error(exc)
                logger.warning("Partial pull-request collection for %s/%s at page %s: %s", owner, repo, page, exc)
                break
            raise

        try:
            data = response.json()
        except ValueError as exc:
            if pull_requests:
                status["partial"] = True
                status["failed_page"] = page
                status["error"] = "GitHub returned invalid JSON."
                break
            raise RuntimeError("GitHub returned an invalid pull-request response.") from exc
        if not isinstance(data, list):
            if pull_requests:
                status["partial"] = True
                status["failed_page"] = page
                status["error"] = "GitHub returned an unexpected pull-request response."
                break
            raise RuntimeError("GitHub returned an unexpected pull-request response.")

        for pull_request in data:
            if not isinstance(pull_request, dict):
                continue
            user = pull_request.get("user")
            pull_requests.append({
                "repository": f"{owner}/{repo}",
                "number": pull_request.get("number"),
                "title": pull_request.get("title"),
                "description": pull_request.get("body"),
                "state": pull_request.get("state"),
                "merged": pull_request.get("merged_at") is not None,
                "merged_at": pull_request.get("merged_at"),
                "created_at": pull_request.get("created_at"),
                "updated_at": pull_request.get("updated_at"),
                "author": user.get("login") if isinstance(user, dict) else None,
                "commits_count": pull_request.get("commits"),
                "changed_files_count": pull_request.get("changed_files"),
                "html_url": pull_request.get("html_url"),
            })

        if len(data) < PER_PAGE:
            break
        if page == MAX_PAGES:
            status["limit_reached"] = True
            break
        page += 1

    logger.info("Collected %s pull requests for %s/%s", len(pull_requests), owner, repo)
    return pull_requests


def get_pull_request_files(owner: str, repo: str, pull_number: int, collection_status: dict | None = None) -> list[dict]:
    """Retrieve files changed by a pull request across all result pages."""
    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/pulls/{pull_number}/files"
    files = []
    page = 1
    status = collection_status if collection_status is not None else {}
    status.update({"limit_reached": False, "partial": False, "failed_page": None})

    while True:
        try:
            response = github_get(url, params={"per_page": PER_PAGE, "page": page}, timeout=(5, 60))
        except RuntimeError:
            if files:
                status["partial"] = True
                status["failed_page"] = page
                return files
            raise

        try:
            data = response.json()
        except ValueError as exc:
            if files:
                status["partial"] = True
                status["failed_page"] = page
                return files
            raise RuntimeError("GitHub returned an invalid changed-file response.") from exc
        if not isinstance(data, list):
            if files:
                status["partial"] = True
                status["failed_page"] = page
                return files
            raise RuntimeError("GitHub returned an unexpected changed-file response.")

        for file_info in data:
            if not isinstance(file_info, dict):
                continue
            filename = file_info.get("filename")
            if not isinstance(filename, str) or not filename.strip():
                continue
            files.append({
                "filename": filename,
                "status": file_info.get("status"),
                "additions": file_info.get("additions", 0),
                "deletions": file_info.get("deletions", 0),
            })

        if len(data) < PER_PAGE:
            return files
        if page == MAX_FILE_PAGES:
            status["limit_reached"] = True
            return files
        page += 1


def get_pull_request(owner: str, repo: str, pull_number: int) -> dict:
    """Retrieve details of one GitHub pull request."""
    if not owner or not repo:
        raise ValueError("Repository owner and name are required.")
    if pull_number < 1:
        raise ValueError("Pull request number must be positive.")

    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/pulls/{pull_number}"
    response = github_get(url, timeout=(5, 60))

    try:
        pull_request = response.json()
        return {
            "number": pull_request["number"],
            "title": pull_request["title"],
            "state": pull_request["state"],
            "merged": pull_request.get("merged_at") is not None,
            "merged_at": pull_request.get("merged_at"),
            "created_at": pull_request["created_at"],
            "author": pull_request["user"]["login"],
            "html_url": pull_request.get("html_url"),
        }
    except (ValueError, KeyError, TypeError) as exc:
        logger.error("Invalid GitHub PR response for %s/%s#%s", owner, repo, pull_number)
        raise RuntimeError("GitHub returned an invalid pull-request response.") from exc
