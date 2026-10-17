# This file extracts the github ISSUES

import requests

from app.core.logger import get_logger
from app.services.github.github_client import get_github_headers

logger = get_logger(__name__)

GITHUB_API_BASE_URL = "https://api.github.com"
REQUEST_TIMEOUT = (5, 60)
PER_PAGE = 20
MAX_PAGES = 5


class GitHubAPIError(Exception):
    """Raised when GitHub returns an unsuccessful API response."""

    def __init__(self, status_code: int, message: str, rate_limited: bool = False):
        self.status_code = status_code
        self.rate_limited = rate_limited
        super().__init__(message)


class GitHubNetworkError(Exception):
    """Raised when a network error prevents communication with GitHub."""


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

    if collection_status is not None:
        collection_status["limit_reached"] = False

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
            response = requests.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT,
                headers=get_github_headers(),
            )

        except requests.exceptions.Timeout as exc:
            logger.warning(
                "GitHub request timed out for %s/%s on page %s",
                owner,
                repo,
                page,
            )

            if bugs:
                logger.warning(
                    "Returning %s partially collected issues for %s/%s; "
                    "collection stopped at page %s",
                    len(bugs),
                    owner,
                    repo,
                    page,
                )
                break

            raise GitHubNetworkError(
                "GitHub took too long to respond. Please try again."
            ) from exc

        except requests.exceptions.RequestException as exc:
            logger.warning(
                "Network error for %s/%s on page %s: %s",
                owner,
                repo,
                page,
                exc,
                exc_info=True,
            )
            if bugs:
                logger.warning(
                    "Returning %s partially collected issue for %s%s",
                    len(bugs),
                    owner,
                    repo,
                )
                break

            raise GitHubNetworkError(
                "Unable to communicate with GitHub. Please try again."
            ) from exc

        if response.status_code != 200:
            logger.warning(
                "GitHub API returned HTTP %s for %s/%s",
                response.status_code,
                owner,
                repo,
            )

            raise GitHubAPIError(
                response.status_code,
                f"GitHub API request failed with status "
                f"{response.status_code}.",
                rate_limited=(
                    response.status_code == 429
                    or (
                        response.status_code == 403
                        and response.headers.get("X-RateLimit-Remaining") == "0"
                    )
                ),
            )

        try:
            issues = response.json()

        except ValueError as exc:
            logger.error(
                "GitHub returned invalid JSON for %s/%s",
                owner,
                repo,
            )
            raise GitHubAPIError(
                response.status_code,
                "GitHub returned an invalid JSON response.",
            ) from exc

        if not isinstance(issues, list):
            logger.error(
                "Unexpected GitHub response format for %s/%s",
                owner,
                repo,
            )
            raise GitHubAPIError(
                response.status_code,
                "GitHub returned an unexpected response format.",
            )

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

        # A short page indicates the final page.
        if len(issues) < PER_PAGE:
            break

        # A short page indicates the final page.
        if len(issues) < PER_PAGE:
            break

        # Warn if the configured page limit is reached.
        if page == MAX_PAGES:
            if collection_status is not None:
                collection_status["limit_reached"] = True
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