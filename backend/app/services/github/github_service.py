# Repositry METADATA Collector
import requests

from app.core.logger import get_logger
from app.services.github.github_client import get_github_headers

logger = get_logger(__name__)

GITHUB_API_BASE_URL = "https://api.github.com"
REQUEST_TIMEOUT = (5, 20)


def get_repository_details(owner: str, repo: str) -> dict:
    """
    Retrieve metadata for an accessible GitHub repository.

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.

    Returns:
        A dictionary containing repository metadata.

    Raises:
        ValueError: If the owner or repository name is invalid.
        RuntimeError: If GitHub cannot provide the repository data.
    """

    # Validate input
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("Repository owner is required.")

    if not isinstance(repo, str) or not repo.strip():
        raise ValueError("Repository name is required.")

    owner = owner.strip()
    repo = repo.strip()

    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}"

    logger.info(
        "Fetching repository metadata for %s/%s",
        owner,
        repo
    )

    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers=get_github_headers()
        )

        if response.status_code == 404:
            raise RuntimeError(
                "Repository not found or not accessible."
            )

        if response.status_code == 403:
            raise RuntimeError(
                "GitHub denied the request. Check API rate limits "
                "or repository permissions."
            )

        response.raise_for_status()

        data = response.json()

    except requests.exceptions.RequestException as exc:
        logger.error(
            "GitHub request failed for %s/%s",
            owner,
            repo
        )
        raise RuntimeError(
            "Unable to retrieve repository metadata from GitHub."
        ) from exc

    except ValueError as exc:
        logger.error(
            "GitHub returned invalid JSON for %s/%s",
            owner,
            repo
        )
        raise RuntimeError(
            "GitHub returned an invalid repository response."
        ) from exc

    if not isinstance(data, dict) or "full_name" not in data:
        raise RuntimeError(
            "GitHub returned an invalid repository response."
        )

    repository = {
        "repository_name": data.get("name"),
        "full_name": data.get("full_name"),
        "owner": data.get("owner", {}).get("login"),
        "description": data.get("description"),
        "primary_language": data.get("language"),
        "visibility": data.get("visibility"),
        "is_private": data.get("private"),
        "default_branch": data.get("default_branch"),
        "stars": data.get("stargazers_count"),
        "forks": data.get("forks_count"),
        "open_issues_count": data.get("open_issues_count"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "html_url": data.get("html_url")
    }

    logger.info(
        "Successfully retrieved metadata for %s",
        repository["full_name"]
    )

    return repository