"""Async SQLAlchemy engine, session factory, and database initialization."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_settings = get_settings()

# Build engine kwargs — SQLite requires check_same_thread=False
_connect_args: dict = {}
if _settings.DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine = create_async_engine(
    _settings.DATABASE_URL,
    echo=False,
    connect_args=_connect_args,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all tables using metadata.create_all (no Alembic)."""
    # Import models so they register with Base.metadata
    from app.models.sms import SMS  # noqa: F401
    from app.models.mms import MMS, MMSPart  # noqa: F401
    from app.models.call import Call  # noqa: F401
    from app.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Simple migration for new columns
        from sqlalchemy import text
        try:
            await conn.execute(text("ALTER TABLE app_config ADD COLUMN sync_schedule VARCHAR DEFAULT '0 2 * * *'"))
        except Exception:
            pass # Column already exists
            
        # Multi-tenant migration
        from app.core.db_migration import run_multi_tenant_migration
        await run_multi_tenant_migration(conn)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
