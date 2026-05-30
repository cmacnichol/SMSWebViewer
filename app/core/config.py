"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration loaded from environment variables and .env file."""

    DATABASE_URL: str = "sqlite+aiosqlite:////data/smsviewer.db"

    # Google OAuth2 Credentials
    GCP_CLIENT_ID: str = ""
    GCP_CLIENT_SECRET: str = ""
    OAUTH_REDIRECT_URI: str = "http://localhost:8000/api/auth/callback"

    # Cron expression for automatic sync (default: 2 AM daily)
    SYNC_SCHEDULE: str = "0 2 * * *"

    # Default country code for phone normalization (E.164)
    DEFAULT_COUNTRY_CODE: str = "US"

    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # Authentication
    AUTH_MODE: str = "NONE"  # NONE, BASIC, OIDC
    SECRET_KEY: str = "change-me-in-production"
    
    # OIDC Configuration
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_ISSUER_URL: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        secrets_dir="/run/secrets"
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the cached singleton Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
