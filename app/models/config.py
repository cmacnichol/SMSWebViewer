"""Application configuration model stored in the database."""

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AppConfig(Base):
    """Singleton configuration table for storing OAuth state and user settings."""

    __tablename__ = "app_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="configs")
    
    # OAuth Tokens
    gdrive_refresh_token: Mapped[str | None] = mapped_column(default=None)
    gdrive_access_token: Mapped[str | None] = mapped_column(default=None)
    gdrive_token_expiry: Mapped[float | None] = mapped_column(default=None)
    
    # Sync Configuration
    gdrive_sync_folder_id: Mapped[str | None] = mapped_column(default=None)
    sync_schedule: Mapped[str] = mapped_column(default="0 2 * * *")
    
    # Sync State
    last_sms_modified: Mapped[str | None] = mapped_column(default=None)
    last_calls_modified: Mapped[str | None] = mapped_column(default=None)
    
    # UI Sync Status
    last_sync_status: Mapped[str | None] = mapped_column(default="never")
    last_sync_time: Mapped[str | None] = mapped_column(default=None)
    last_sync_error: Mapped[str | None] = mapped_column(default=None)
    last_sync_stats: Mapped[str | None] = mapped_column(default=None)
