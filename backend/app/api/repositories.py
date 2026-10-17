import re
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException

from app.core.logger import get_logger
from app.schemas.repository import RepositoryRequest
from app.services.github.issue_service import (
    GitHubAPIError,
    GitHubNetworkError,
    get_repository_issues,
)
from app.services.github.github_service import get_repository_details
from app.services.github.pull_request_service import get_repository_pull_requests
from app.services.github.relationship_service import collect_pull_request_relationships

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/repositories",
    tags=["Repositories"]
)

@router.post("/analyze")
def analyze_repository(request: RepositoryRequest):
    parsed_url = urlsplit(str(request.repository_url))
    path_parts = [part for part in parsed_url.path.split("/") if part]
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != "github.com"
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.query
        or parsed_url.fragment
        or len(path_parts) != 2
    ):
        raise HTTPException(
            status_code=400,
            detail="Enter a repository URL such as https://github.com/owner/repository.",
        )

    owner, repo = path_parts
    if repo.endswith(".git"):
        repo = repo[:-4]
    if (
        not re.fullmatch(r"[A-Za-z0-9-]+", owner)
        or not re.fullmatch(r"[A-Za-z0-9._-]+", repo)
        or repo in {".", ".."}
    ):
        raise HTTPException(
            status_code=400,
            detail="The URL does not contain a valid GitHub owner and repository.",
        )

    try:
        issues = get_repository_issues(owner, repo)
    except GitHubAPIError as exc:
        if exc.rate_limited:
            status_code = 429
            message = "GitHub API rate limit reached. Configure GITHUB_TOKEN and retry later."
        elif exc.status_code == 404:
            status_code = 404
            message = "Repository not found or not accessible to this GitHub account."
        elif exc.status_code in (401, 403):
            status_code = exc.status_code
            message = "GitHub denied access. Check repository permissions and GITHUB_TOKEN."
        else:
            status_code = 502
            message = "GitHub could not complete issue collection."
        logger.warning("Issue collection failed for %s/%s: HTTP %s", owner, repo, exc.status_code)
        raise HTTPException(
            status_code=status_code,
            detail=message,
        ) from exc
    except GitHubNetworkError as exc:
        raise HTTPException(
            status_code=503,
            detail="Unable to reach GitHub. Check the network and try again.",
        ) from exc

    warnings = []
    try:
        repository_details = get_repository_details(owner, repo)
    except (RuntimeError, ValueError) as exc:
        logger.warning("Repository metadata unavailable for %s/%s: %s", owner, repo, exc)
        repository_details = {
            "full_name": f"{owner}/{repo}",
            "description": None,
            "html_url": f"https://github.com/{owner}/{repo}",
        }
        warnings.append("Repository metadata could not be collected.")

    try:
        pull_requests = get_repository_pull_requests(owner, repo)
    except (RuntimeError, ValueError) as exc:
        logger.warning("Pull-request collection failed for %s/%s: %s", owner, repo, exc)
        pull_requests = []
        warnings.append("Pull requests could not be collected; issue results are available.")

    try:
        relationship_result = collect_pull_request_relationships(
            owner,
            repo,
            pull_requests=pull_requests,
        )
    except (RuntimeError, ValueError) as exc:
        logger.warning(
            "Relationship collection failed for %s/%s: %s",
            owner,
            repo,
            exc,
        )

        relationship_result = {
            "relationships": [],
            "failed_pull_requests": [],
            "skipped_pull_requests": len(pull_requests),
        }

        warnings.append(
            "Commit and changed-file relationship analysis failed. "
            "Issue and pull-request results may still be available."
        )
    failed_relationships = relationship_result["failed_pull_requests"]
    skipped_relationships = relationship_result["skipped_pull_requests"]
    if failed_relationships:
        warnings.append(
            f"Commit and file relationships could not be collected for "
            f"{len(failed_relationships)} pull request(s)."
        )
    if skipped_relationships:
        warnings.append(
            f"Relationship collection was limited; {skipped_relationships} pull request(s) were skipped."
        )

    status = "partial" if warnings else "complete"
    counts = {
        "issues": len(issues),
        "pull_requests": len(pull_requests),
        "relationships": len(relationship_result["relationships"]),
        "failed_relationships": len(failed_relationships),
        "skipped_relationships": skipped_relationships,
    }
    logger.info("Analysis collection %s for %s/%s", status, owner, repo)

    return {
        "repository": f"{owner}/{repo}",
        "repository_url": repository_details.get(
            "html_url",
            f"https://github.com/{owner}/{repo}",
        ),
        "repository_details": repository_details,
        "status": status,
        "warnings": warnings,
        "counts": counts,
        "issues": issues,
        "pull_requests": pull_requests,
        "relationships": relationship_result["relationships"],
        "failed_pull_requests": failed_relationships,
        "skipped_pull_requests": skipped_relationships,
        # Retained for clients of the original issues-only endpoint.
        "total_bugs": len(issues),
        "bugs": issues,
    }