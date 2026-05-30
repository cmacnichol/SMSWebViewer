"""SQLAlchemy model for Call log records."""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Integer, SmallInteger, String, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Call(Base):
    """Phone call log record."""

    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="calls")
    number: Mapped[str] = mapped_column(String(32), index=True)
    normalized_number: Mapped[str] = mapped_column(String(32), index=True)
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    date_ms: Mapped[int] = mapped_column(BigInteger)
    readable_date: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    duration: Mapped[int] = mapped_column(Integer, default=0)  # seconds
    type: Mapped[int] = mapped_column(SmallInteger)  # 1=incoming, 2=outgoing, 3=missed
    presentation: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
