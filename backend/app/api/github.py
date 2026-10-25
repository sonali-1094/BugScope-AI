from fastapi import APIRouter

from app.services.github.github_client import get_github_auth_status

router = APIRouter(prefix="/api/github", tags=["GitHub"])


@router.get("/auth-status")
def github_auth_status():
    """Report token configuration and validation without returning credentials."""
    return get_github_auth_status()
