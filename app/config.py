"""Application configuration loaded from environment variables / .env file.

Kept intentionally small: the app only needs to know where the database
lives and where generated PDF files should be written.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings with sensible local defaults."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Bulk Certificate Generator"
    database_url: str = "sqlite:///./certificates.db"
    certificate_storage_dir: str = "./storage/certificates"

    @property
    def storage_path(self) -> Path:
        """Absolute filesystem path used to store certificate PDFs.

        Resolved to an absolute path so the `file_path` values persisted
        in the database stay valid even if the server is restarted from
        a different working directory.
        """
        path = Path(self.certificate_storage_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
