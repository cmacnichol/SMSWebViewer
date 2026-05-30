import logging
import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from app.core.config import get_settings
from app.core.security import get_password_hash

logger = logging.getLogger(__name__)

async def run_multi_tenant_migration(conn: AsyncConnection):
    """
    Adds user_id to existing tables and migrates legacy data to a Default Admin user.
    """
    tables_to_migrate = ["sms", "mms", "calls", "app_config"]
    migration_needed = False

    for table in tables_to_migrate:
        try:
            # In SQLite, adding a foreign key column without constraints is safe.
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id VARCHAR REFERENCES users(id)"))
            migration_needed = True
            logger.info(f"Added user_id column to {table}.")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                pass # Already migrated
            else:
                logger.error(f"Error adding user_id to {table}: {e}")
                
    # Add sync state columns to app_config
    for col in ["last_sms_modified", "last_calls_modified", "last_sync_status", "last_sync_time", "last_sync_error", "last_sync_stats"]:
        try:
            await conn.execute(text(f"ALTER TABLE app_config ADD COLUMN {col} VARCHAR"))
            logger.info(f"Added {col} column to app_config.")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                pass
            else:
                logger.error(f"Error adding {col} to app_config: {e}")

    # Check if users table has an admin user
    res = await conn.execute(text("SELECT id, password_hash FROM users WHERE role = 'admin' LIMIT 1"))
    admin_row = res.fetchone()
    
    default_password = get_password_hash("admin")
    
    if not admin_row:
        logger.info("No admin user found. Generating Default Admin user...")
        admin_id = str(uuid.uuid4())
        
        await conn.execute(
            text("INSERT INTO users (id, username, password_hash, role) VALUES (:id, :username, :password_hash, :role)"),
            {"id": admin_id, "username": "admin", "password_hash": default_password, "role": "admin"}
        )
        logger.info(f"Created Default Admin user with ID {admin_id}. Username: admin | Password: admin")
    else:
        admin_id = admin_row[0]
        if not admin_row[1]:
            # Admin exists but has no password hash (legacy migration)
            await conn.execute(
                text("UPDATE users SET password_hash = :password_hash WHERE id = :id"),
                {"password_hash": default_password, "id": admin_id}
            )
            logger.info("Set default password 'admin' for existing Default Admin user.")
        
    # Always try to update legacy records (any records missing a user_id)
    # This ensures that if the admin user was created but records weren't migrated, they will be now.
    for table in tables_to_migrate:
        await conn.execute(
            text(f"UPDATE {table} SET user_id = :admin_id WHERE user_id IS NULL"),
            {"admin_id": admin_id}
        )
    logger.info("Migrated all unassigned legacy records to Default Admin.")
