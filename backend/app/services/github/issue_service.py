# This file extracts the github ISSUES

from app.core.logger import get_logger
from app.services.github.github_client import (
    GITHUB_API_BASE_URL,
    GitHubAPIError,
    GitHubNetworkError,
    describe_github_error,
    github_get,
)

logger = get_logger(__name__)

PER_PAGE = 100
MAX_PAGES = 5


def get_repository_issues(owner: str, repo: str, collection_status: dict | None = None) -> list[dict]:
    """
    Retrieve all accessible issues from a GitHub repository.

    Pull requests are excluded because GitHub also returns them
    through the Issues API.

    Results are collected across pages until no more issues remain.
    """

    # Validate inputs.
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("Repository owner is required.")

    if not isinstance(repo, str) or not repo.strip():
        raise ValueError("Repository name is required.")

    owner = owner.strip()
    repo = repo.strip()

    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/issues"

    bugs = []
    page = 1

    status = collection_status if collection_status is not None else {}
    status.update({"limit_reached": False, "partial": False, "failed_page": None, "error": None})

    logger.info(
        "Starting issue collection for %s/%s",
        owner,
        repo,
    )

    while page <= MAX_PAGES:
        params = {
            "state": "all",
            "per_page": PER_PAGE,
            "page": page,
        }

        logger.info(
            "Fetching issues for %s/%s, page %s",
            owner,
            repo,
            page,
        )

        try:
            response = github_get(url, params=params, timeout=(5, 60))
        except (GitHubNetworkError, GitHubAPIError) as exc:
            logger.warning(
                "GitHub request failed for %s/%s on page %s: %s",
                owner,
                repo,
                page,
                exc,
            )
            if bugs:
                status["partial"] = True
                status["failed_page"] = page
                status["error"] = describe_github_error(exc)
                break
            raise

        try:
            issues = response.json()

        except ValueError as exc:
            logger.error(
                "GitHub returned invalid JSON for %s/%s",
                owner,
                repo,
            )
            if bugs:
                status["partial"] = True
                status["failed_page"] = page
                status["error"] = "GitHub returned invalid JSON."
                break
            raise GitHubAPIError(response.status_code, "GitHub returned invalid JSON.") from exc

        if not isinstance(issues, list):
            logger.error(
                "Unexpected GitHub response format for %s/%s",
                owner,
                repo,
            )
            if bugs:
                status["partial"] = True
                status["failed_page"] = page
                status["error"] = "GitHub returned an unexpected issue response."
                break
            raise GitHubAPIError(response.status_code, "GitHub returned an unexpected issue response.")

        # An empty page means there are no more results.
        if not issues:
            break

        for issue in issues:

            if not isinstance(issue, dict):
                continue

            # The Issues API also returns pull requests.
            if "pull_request" in issue:
                continue

            issue_number = issue.get("number")
            title = issue.get("title")
            state = issue.get("state")
            created_at = issue.get("created_at")

            # Skip malformed issue records instead of crashing.
            if (
                not isinstance(issue_number, int)
                or not isinstance(title, str)
                or state not in ("open", "closed")
                or not created_at
            ):
                logger.warning(
                    "Skipping malformed issue in %s/%s",
                    owner,
                    repo,
                )
                continue

            labels = issue.get("labels") or []

            bugs.append(
                {
                    "issue_number": issue_number,
                    "title": title,
                    "description": issue.get("body"),
                    "state": state,
                    "created_at": created_at,
                    "closed_at": issue.get("closed_at"),
                    "labels": [
                        label.get("name")
                        for label in labels
                        if isinstance(label, dict)
                        and isinstance(label.get("name"), str)
                    ],
                    "html_url": issue.get("html_url"),
                    "author": (
                        issue.get("user", {}).get("login")
                        if isinstance(issue.get("user"), dict)
                        else None
                    ),
                    "comments": issue.get("comments", 0),
                }
            )

        logger.info(
            "Processed page %s for %s/%s; collected %s issues so far",
            page,
            owner,
            repo,
            len(bugs),
        )

        if len(issues) < PER_PAGE:
            break

        # Warn if the configured page limit is reached.
        if page == MAX_PAGES:
            status["limit_reached"] = True
            logger.warning(
                "Issue collection reached the configured page limit (%s) "
                "for %s/%s. More issues may exist.",
                MAX_PAGES,
                owner,
                repo,
            )
            break

        page += 1

    logger.info(
        "Completed issue collection for %s/%s: %s issues",
        owner,
        repo,
        len(bugs),
    )

    return bugs
