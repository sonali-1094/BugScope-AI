import re
import os
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException

from app.core.logger import get_logger
from app.schemas.repository import RepositoryRequest
from app.services.github.issue_service import (
    GitHubAPIError,
    GitHubNetworkError,
    get_repository_issues,
)
from app.services.github.github_client import describe_github_error
from app.services.github.commit_service import get_repository_commits
from app.services.github.github_service import get_repository_details
from app.services.github.pull_request_service import get_repository_pull_requests
from app.services.github.relationship_service import (
    collect_pull_request_relationships,
    extract_issue_references,
)

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

    collection = {}
    warnings = []
    try:
        issue_status = {}
        issues = get_repository_issues(owner, repo, collection_status=issue_status)
    except GitHubAPIError as exc:
        if exc.rate_limited:
            status_code = 429
            message = "GitHub API rate limit reached. Configure GITHUB_TOKEN and retry later."
        elif exc.invalid_token:
            status_code = 401
            message = "GitHub rejected the configured GITHUB_TOKEN. Check the token without sharing it."
        elif exc.status_code == 404:
            status_code = 404
            message = "Repository not found or not accessible to this GitHub account."
        elif exc.status_code == 403:
            status_code = 403
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

    if issue_status.get("partial"):
        warnings.append(f"Issue collection stopped after page {issue_status['failed_page']}; returned results are partial ({issue_status.get('error') or 'request failed'}).")
    if issue_status.get("limit_reached"):
        warnings.append("Issue collection reached its page limit; more issues may exist.")
    collection["issues"] = {
        "status": "partial" if issue_status.get("partial") or issue_status.get("limit_reached") else "complete",
        "returned": len(issues),
        "limit_reached": issue_status.get("limit_reached", False),
    }

    try:
        repository_details = get_repository_details(owner, repo)
        collection["repository_metadata"] = {"status": "complete", "returned": 1}
    except (RuntimeError, ValueError) as exc:
        logger.warning("Repository metadata unavailable for %s/%s: %s", owner, repo, exc)
        repository_details = {
            "full_name": f"{owner}/{repo}",
            "description": None,
            "html_url": f"https://github.com/{owner}/{repo}",
        }
        collection["repository_metadata"] = {"status": "failed", "returned": 0}
        warnings.append("Repository metadata could not be collected.")

    pull_request_status = {}
    try:
        pull_requests = get_repository_pull_requests(owner, repo, collection_status=pull_request_status)
        if pull_request_status.get("partial"):
            warnings.append(f"Pull-request collection stopped after page {pull_request_status['failed_page']}; returned results are partial ({pull_request_status.get('error') or 'request failed'}).")
        if pull_request_status.get("limit_reached"):
            warnings.append("Pull-request collection reached its page limit; more pull requests may exist.")
        collection["pull_requests"] = {
            "status": "partial" if pull_request_status.get("partial") or pull_request_status.get("limit_reached") else "complete",
            "returned": len(pull_requests),
            "limit_reached": pull_request_status.get("limit_reached", False),
        }
    except (RuntimeError, ValueError) as exc:
        logger.warning("Pull-request collection failed for %s/%s: %s", owner, repo, exc)
        pull_requests = []
        collection["pull_requests"] = {"status": "failed", "returned": 0}
        warnings.append(f"Pull requests could not be collected: {describe_github_error(exc)}")

    try:
        commit_limit = max(1, min(99, int(os.getenv("BUGSCOPE_MAX_REPOSITORY_COMMITS", "20"))))
    except ValueError:
        commit_limit = 20
    commit_status = {}
    try:
        commits = get_repository_commits(owner, repo, limit=commit_limit, collection_status=commit_status)
        issue_numbers = {issue["issue_number"] for issue in issues if isinstance(issue.get("issue_number"), int)}
        for commit in commits:
            commit["issue_references"] = extract_issue_references(
                commit.get("message"), f"{owner}/{repo}", "commit_message", commit.get("sha")
            )
            for reference in commit["issue_references"]:
                if reference["repository"].casefold() == f"{owner}/{repo}".casefold():
                    reference["target_in_collected_issues"] = reference["issue_number"] in issue_numbers
        if commit_status.get("limit_reached"):
            warnings.append(f"Repository commit collection reached its configured limit ({commit_limit}); more commits may exist.")
        if commit_status.get("partial"):
            warnings.append(f"Changed-file details failed for {commit_status['failed_file_details']} commit(s).")
        collection["commits"] = {
            "status": "partial" if commit_status.get("partial") or commit_status.get("limit_reached") else "complete",
            "returned": len(commits),
            "limit_reached": commit_status.get("limit_reached", False),
            "failed_file_details": commit_status.get("failed_file_details", 0),
        }
    except (RuntimeError, ValueError) as exc:
        logger.warning("Repository commit collection failed for %s/%s: %s", owner, repo, exc)
        commits = []
        collection["commits"] = {"status": "failed", "returned": 0}
        warnings.append(f"Repository commits could not be collected: {describe_github_error(exc)}")

    relationship_status = {}
    if collection["pull_requests"]["status"] == "failed":
        relationship_result = {
            "relationships": [],
            "failed_pull_requests": [],
            "skipped_pull_requests": len(pull_requests),
        }
        collection["relationships"] = {"status": "not_run", "returned": 0, "failed": 0, "skipped": 0}
    else:
        try:
            relationship_result = collect_pull_request_relationships(
                owner,
                repo,
                pull_requests=pull_requests,
                collection_status=relationship_status,
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
            collection["relationships"] = {"status": "failed", "returned": 0, "failed": 0, "skipped": len(pull_requests)}
            warnings.append(
                f"Commit and changed-file relationship analysis failed: {describe_github_error(exc)}"
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
    if "relationships" not in collection:
        collection["relationships"] = {
            "status": "partial" if failed_relationships or skipped_relationships else "complete",
            "returned": len(relationship_result["relationships"]),
            "failed": len(failed_relationships),
            "skipped": skipped_relationships,
        }
    if relationship_result["relationships"]:
        issue_numbers = {issue["issue_number"] for issue in issues if isinstance(issue.get("issue_number"), int)}
        for relationship in relationship_result["relationships"]:
            for reference in relationship.get("issue_references", []):
                if reference["repository"].casefold() == f"{owner}/{repo}".casefold():
                    reference["target_in_collected_issues"] = reference["issue_number"] in issue_numbers
    if relationship_status.get("files_truncated"):
        warnings.append(f"Changed-file collection reached its page limit for {relationship_status['files_truncated']} pull request(s).")
        collection["relationships"]["status"] = "partial"
    if relationship_status.get("partial_file_requests"):
        warnings.append(f"Changed-file collection was incomplete for {relationship_status['partial_file_requests']} pull request(s).")
        collection["relationships"]["status"] = "partial"

    empty_results = [
        name for name, records in (
            ("issues", issues),
            ("pull_requests", pull_requests),
            ("commits", commits),
        ) if not records and collection.get(name, {}).get("status") == "complete"
    ]

    status = "partial" if warnings else "complete"
    counts = {
        "issues": len(issues),
        "pull_requests": len(pull_requests),
        "commits": len(commits),
        "changed_files": len(
            {file_info.get("filename") for commit in commits for file_info in commit.get("changed_files", [])
             if isinstance(file_info, dict) and isinstance(file_info.get("filename"), str)}
            | {filename for relationship in relationship_result["relationships"]
               for filename in relationship.get("changed_files", []) if isinstance(filename, str)}
        ),
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
        "collection": collection,
        "empty_results": empty_results,
        "issues": issues,
        "pull_requests": pull_requests,
        "commits": commits,
        "relationships": relationship_result["relationships"],
        "failed_pull_requests": failed_relationships,
        "skipped_pull_requests": skipped_relationships,
        # Retained for clients of the original issues-only endpoint.
        "total_bugs": len(issues),
        "bugs": issues,
    }
