import os
from pathlib import Path

from dotenv import load_dotenv

# Locate backend/ .env reliably
BACKEND_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = BACKEND_DIR / ".env"

load_dotenv(ENV_FILE)

def get_github_headers() -> dict[str, str]:
    """
    Build GitHub api headers without exposing creadentials to clients
    """
    headers = {
        "Accept": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    token = os.getenv("GITHUB_TOKEN")

    if token:
        headers["Authorization"] = f"Bearer {token}"

    return headers