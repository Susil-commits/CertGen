"""API routers package."""

from app.routers.certificates import router as certificates_router
from app.routers.jobs import router as jobs_router

__all__ = ["jobs_router", "certificates_router"]
