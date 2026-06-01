"""SQLAlchemy models for MMS messages and their parts."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class MMS(Base):
    """MMS message record."""

    __tablename__ = "mms"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    address: Mapped[str] = mapped_column(String(255), index=True)
    normalized_address: Mapped[str] = mapped_column(String(255), index=True)
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    date_ms: Mapped[int] = mapped_column(BigInteger)
    readable_date: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    msg_box: Mapped[int] = mapped_column(SmallInteger)  # 1=received, 2=sent
    subject: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # concatenated text parts
    ct_t: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    parts: Mapped[list["MMSPart"]] = relationship(
        back_populates="mms", cascade="all, delete-orphan"
    )
    user: Mapped["User"] = relationship(back_populates="mms_messages")


class MMSPart(Base):
    """Individual part/attachment of an MMS message."""

    __tablename__ = "mms_parts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    mms_id: Mapped[int] = mapped_column(
        ForeignKey("mms.id", ondelete="CASCADE")
    )
    seq: Mapped[int] = mapped_column(SmallInteger, default=0)
    content_type: Mapped[str] = mapped_column(String(128))
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary, nullable=True
    )  # base64-decoded media stored in DB

    mms: Mapped["MMS"] = relationship(back_populates="parts")
