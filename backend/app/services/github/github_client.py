import os
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load backend settings first, then fall back to the project-root .env. The
# root .env is also used by the Node collector, so this lets both backends use
# the same GitHub token without duplicating it into another secret file.
BACKEND_DIR = Path(__file__).resolve().parents[3]
PROJECT_DIR = BACKEND_DIR.parent

load_dotenv(BACKEND_DIR / ".env")
load_dotenv(PROJECT_DIR / ".env")

GITHUB_API_BASE_URL = "https://api.github.com"
REQUEST_TIMEOUT = (5, 30)


class GitHubNetworkError(RuntimeError):
    """A network failure prevented a request to GitHub."""


class GitHubAPIError(RuntimeError):
    """GitHub returned an unsuccessful API response."""

    def __init__(self, status_code: int, message: str, rate_limited: bool = False):
        self.status_code = status_code
        self.rate_limited = rate_limited
        self.invalid_token = status_code == 401
        super().__init__(message)


def describe_github_error(error: Exception) -> str:
    """Return a user-safe explanation that never includes request headers."""
    if isinstance(error, GitHubNetworkError):
        return str(error)
    if isinstance(error, GitHubAPIError):
        if error.invalid_token:
            return "GitHub rejected the configured GITHUB_TOKEN."
        if error.rate_limited:
            return "GitHub API rate limit reached."
        if error.status_code == 403:
            return "GitHub denied access; check token permissions and repository access."
        if error.status_code == 404:
            return "Repository or GitHub resource was not found or is not accessible."
        return f"GitHub API returned HTTP {error.status_code}."
    return str(error)


def github_get(url: str, *, params: dict | None = None, timeout=REQUEST_TIMEOUT):
    """GET a GitHub API resource with configured auth and normalized errors."""
    try:
        response = requests.get(
            url,
            params=params,
            timeout=timeout,
            headers=get_github_headers(),
        )
    except requests.exceptions.Timeout as exc:
        raise GitHubNetworkError("GitHub request timed out.") from exc
    except requests.exceptions.RequestException as exc:
        raise GitHubNetworkError("Unable to connect to GitHub.") from exc

    if response.status_code >= 400:
        rate_limited = response.status_code == 429 or (
            response.status_code == 403
            and response.headers.get("X-RateLimit-Remaining") == "0"
        )
        raise GitHubAPIError(
            response.status_code,
            f"GitHub API returned HTTP {response.status_code}.",
            rate_limited=rate_limited,
        )
    return response


def get_github_auth_status() -> dict:
    """Check token validity without exposing the token or GitHub profile."""
    if not os.getenv("GITHUB_TOKEN"):
        return {
            "status": "not_configured",
            "configured": False,
            "authenticated": False,
            "message": "No GitHub token is configured; public repository access is unauthenticated.",
        }

    try:
        response = github_get(f"{GITHUB_API_BASE_URL}/user")
    except GitHubAPIError as exc:
        if exc.invalid_token:
            status = "invalid_token"
            message = "GitHub rejected the configured token."
        elif exc.rate_limited:
            status = "rate_limited"
            message = "GitHub rate limit is exhausted."
        elif exc.status_code == 403:
            status = "insufficient_permissions"
            message = "GitHub denied the token's access to the authentication endpoint."
        else:
            status = "github_error"
            message = "GitHub could not validate the token."
        return {
            "status": status,
            "configured": True,
            "authenticated": False,
            "message": message,
        }
    except GitHubNetworkError:
        return {
            "status": "network_error",
            "configured": True,
            "authenticated": False,
            "message": "Could not connect to GitHub.",
        }

    try:
        payload = response.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return {
            "status": "github_error",
            "configured": True,
            "authenticated": False,
            "message": "GitHub returned an unexpected authentication response.",
        }
    return {
        "status": "authenticated",
        "configured": True,
        "authenticated": True,
        "message": "GitHub accepted the configured token.",
    }

def get_github_headers() -> dict[str, str]:
    """
    Build GitHub API headers without exposing credentials to clients.
    """
    headers = {
        "Accept": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    token = os.getenv("GITHUB_TOKEN")

    if token:
        headers["Authorization"] = f"Bearer {token}"

    return headers
