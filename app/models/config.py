"""Application configuration model stored in the database."""

from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AppConfig(Base):
    """Singleton configuration table for storing OAuth state and user settings."""

    __tablename__ = "app_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    
    # OAuth Tokens
    gdrive_refresh_token: Mapped[str | None] = mapped_column(default=None)
    gdrive_access_token: Mapped[str | None] = mapped_column(default=None)
    gdrive_token_expiry: Mapped[float | None] = mapped_column(default=None)
    
    # Sync Configuration
    gdrive_sync_folder_id: Mapped[str | None] = mapped_column(default=None)
    sync_schedule: Mapped[str] = mapped_column(default="0 2 * * *")
