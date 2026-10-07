from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import jobs


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown events."""
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


@app.get("/", tags=["Root"])
def read_root() -> dict[str, str]:
    """Root endpoint welcoming API consumers."""
    return {
        "app": settings.APP_NAME,
        "version": "1.0.0",
        "status": "operational",
        "docs_url": "/docs",
    }


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    """Basic health check probe."""
    return {"status": "healthy"}


# Register Routers
app.include_router(jobs.router)
