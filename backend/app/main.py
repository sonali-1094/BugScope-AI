import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.repositories import router as repository_router

app = FastAPI(
    title="BugScope AI",
    description="AI-assisted historical bug investigation system",
    version="0.1.0"
)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "BUGSCOPE_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(repository_router)

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "BugScope AI"
    }