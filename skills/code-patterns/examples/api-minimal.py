# API Pattern: Minimal
# Use for: Health checks, internal tools, simple endpoints

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}


@router.get("/version")
def get_version():
    """Return application version."""
    return {"version": "1.0.0"}
