import uuid
from typing import Optional, List
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    oidc_sub: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True, index=True)
    role: Mapped[str] = mapped_column(String, default="user")  # 'user' or 'admin'

    # Relationships
    tokens: Mapped[List["ApiToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    configs: Mapped[List["AppConfig"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    sms_messages: Mapped[List["SMS"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    mms_messages: Mapped[List["MMS"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    calls: Mapped[List["Call"]] = relationship(back_populates="user", cascade="all, delete-orphan")
