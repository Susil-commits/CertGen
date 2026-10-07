from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment or .env file."""

    APP_NAME: str = "Bulk Certificate Generator"
    APP_ENV: str = "development"
    DATABASE_URL: str = "sqlite:///./cert_generator.db"
    OUTPUT_DIR: Path = Path("generated")
    LOG_LEVEL: str = "INFO"

    # Base directory of the project
    BASE_DIR: Path = Path(__file__).resolve().parent.parent

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_output_dir(self) -> Path:
        """Return output directory and ensure it exists."""
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        return self.OUTPUT_DIR


settings = Settings()
settings.get_output_dir()
