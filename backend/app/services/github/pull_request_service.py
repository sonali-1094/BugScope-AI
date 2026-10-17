import requests

from app.core.logger import get_logger
from app.services.github.github_client import get_github_headers

logger = get_logger(__name__)
GITHUB_API_BASE_URL = "https://api.github.com"
REQUEST_TIMEOUT = (15, 60)
PER_PAGE = 20
MAX_PAGES =2


def get_repository_pull_requests(owner: str, repo: str) -> list[dict]:
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

    while page <= MAX_PAGES:
        try:
            response = requests.get(
                url,
                params={
                    "state": "all",
                    "per_page": PER_PAGE,
                    "page": page,
                    "sort": "created",
                    "direction": "asc",
                },
                timeout=REQUEST_TIMEOUT,
                headers=get_github_headers(),
            )
        except requests.exceptions.Timeout as exc:
            logger.warning("Pull-request collection timed out for %s/%s", owner, repo)
            raise RuntimeError("GitHub took too long to return pull requests.") from exc
        except requests.exceptions.RequestException as exc:
            logger.warning("Pull-request network error for %s/%s", owner, repo)
            raise RuntimeError("Unable to retrieve pull requests from GitHub.") from exc

        if response.status_code != 200:
            raise RuntimeError(
                f"GitHub pull-request collection failed with status {response.status_code}."
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError("GitHub returned an invalid pull-request response.") from exc
        if not isinstance(data, list):
            raise RuntimeError("GitHub returned an unexpected pull-request response.")

        for pull_request in data:
            if not isinstance(pull_request, dict):
                continue
            user = pull_request.get("user")
            pull_requests.append({
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
        page += 1

    logger.info("Collected %s pull requests for %s/%s", len(pull_requests), owner, repo)
    return pull_requests


def get_pull_request_files(owner: str, repo: str, pull_number: int) -> list[dict]:
    """Retrieve files changed by a pull request across all result pages."""
    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/pulls/{pull_number}/files"
    files = []
    page = 1

    while True:
        try:
            response = requests.get(
                url,
                params={"per_page": PER_PAGE, "page": page},
                timeout=REQUEST_TIMEOUT,
                headers=get_github_headers(),
            )
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                "Unable to retrieve changed files from GitHub."
            ) from exc

        if response.status_code != 200:
            raise RuntimeError(
                f"GitHub changed-file collection failed with status {response.status_code}."
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(
                "GitHub returned an invalid changed-file response."
            ) from exc
        if not isinstance(data, list):
            raise RuntimeError(
                "GitHub returned an unexpected changed-file response."
            )

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
        page += 1


def get_pull_request(owner: str, repo: str, pull_number: int) -> dict:
    """Retrieve details of one GitHub pull request."""
    if not owner or not repo:
        raise ValueError("Repository owner and name are required.")
    if pull_number < 1:
        raise ValueError("Pull request number must be positive.")

    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/pulls/{pull_number}"
    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers=get_github_headers(),
        )
    except requests.exceptions.Timeout as exc:
        raise RuntimeError("GitHub API request timed out.") from exc
    except requests.exceptions.RequestException as exc:
        raise RuntimeError("Unable to connect to GitHub.") from exc

    if response.status_code != 200:
        raise RuntimeError(f"GitHub pull-request request failed with status {response.status_code}.")

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