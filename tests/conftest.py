import os
import tempfile
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app

# In-memory SQLite engine for fast, isolated tests
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
    future=True,
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment() -> Generator[None, None, None]:
    """Configure isolated environment variables and directories for test run."""
    with tempfile.TemporaryDirectory() as temp_dir:
        original_output = settings.OUTPUT_DIR
        settings.OUTPUT_DIR = Path(temp_dir)
        yield
        settings.OUTPUT_DIR = original_output


@pytest.fixture(autouse=True)
def setup_test_db() -> Generator[None, None, None]:
    """Create fresh tables before every test and drop them after."""
    import app.workers.tasks

    orig_factory = app.workers.tasks.SessionLocal
    app.workers.tasks.SessionLocal = TestingSessionLocal

    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    app.workers.tasks.SessionLocal = orig_factory


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide a test transactional database session."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest_asyncio.fixture
async def client(db_session: Session) -> AsyncGenerator[AsyncClient, None]:
    """Provide an asynchronous HTTP client configured for ASGI testing."""

    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
