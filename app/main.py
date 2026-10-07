from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import certificates, jobs
from app.utils.logging import setup_logging

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown events."""
    setup_logging()
    # Ensure generated output directory exists
    settings.get_output_dir()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Scalable Bulk Certificate Generation API with isolated background processing",
    lifespan=lifespan,
)

# Enable CORS for frontend integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static asset directory
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", tags=["Root"])
def read_root() -> dict[str, str]:
    """Root endpoint welcoming API consumers."""
    return {
        "app": settings.APP_NAME,
        "version": "1.0.0",
        "status": "operational",
        "docs_url": "/docs",
        "ui_url": "/ui",
    }


@app.get("/ui", tags=["Frontend"], include_in_schema=False)
def get_ui() -> FileResponse:
    """Serve the minimal certificate generation web interface."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    """Basic health check probe."""
    return {"status": "healthy"}


# Register Routers
app.include_router(jobs.router)
app.include_router(certificates.router)
