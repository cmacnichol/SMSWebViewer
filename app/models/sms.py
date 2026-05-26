"""SMS model — maps to the `sms` table."""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Integer, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SMS(Base):
    """Individual SMS message record parsed from SMS Backup & Restore XML."""

    __tablename__ = "sms"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Addresses
    address: Mapped[str] = mapped_column(String(32), index=True)
    normalized_address: Mapped[str] = mapped_column(String(32), index=True)
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Timestamps
    date_ms: Mapped[int] = mapped_column(BigInteger)
    readable_date: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Message metadata
    type: Mapped[int] = mapped_column(SmallInteger)  # 1=recv, 2=sent, 3=draft, etc.
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    read: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    status: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    service_center: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    sub_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    def __repr__(self) -> str:
        return f"<SMS id={self.id} address={self.normalized_address} type={self.type}>"
