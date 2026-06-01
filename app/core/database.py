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
    """Run Alembic upgrades and data migrations."""
    import logging
    import asyncio
    
    logger = logging.getLogger(__name__)
    
    from sqlalchemy import inspect
    def get_tables(sync_conn):
        return inspect(sync_conn).get_table_names()
        
    async with engine.connect() as conn:
        tables = await conn.run_sync(get_tables)
        
    has_legacy = "app_config" in tables
    has_alembic = "alembic_version" in tables
    
    if has_legacy and not has_alembic:
        logger.info("Legacy pre-Alembic database detected. Bootstrapping schema to baseline...")
        from app.core.db_migration import bootstrap_legacy_schema
        async with engine.begin() as conn:
            await bootstrap_legacy_schema(conn)
            
        logger.info("Stamping database with Alembic baseline...")
        proc = await asyncio.create_subprocess_exec(
            "alembic", "stamp", "head",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise Exception(f"Alembic stamp failed: STDERR: {stderr.decode()} STDOUT: {stdout.decode()}")
    else:
        logger.info("Running database migrations via Alembic...")
        proc = await asyncio.create_subprocess_exec(
            "alembic", "upgrade", "head",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise Exception(f"Alembic upgrade failed: {stderr.decode()}")
        
    logger.info(f"Alembic migrations completed successfully. Output: {stdout.decode()}")
    
    # Multi-tenant data migration
    from app.core.db_migration import run_multi_tenant_migration
    async with engine.begin() as conn:
        await run_multi_tenant_migration(conn)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
