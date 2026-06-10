#!/usr/bin/env python3
"""
Database setup script - Create/recreate all tables from models.

This script uses SQLAlchemy's metadata.create_all() to create tables from the ORM models.
Run this once after creating the database, or after deleting all tables.

Usage:
    python setup_db.py
"""

import os
import asyncio
import logging
from sqlalchemy import text

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.engine import make_url
from app.config import get_settings
# Important: We must import the models so that SQLAlchemy's Base.metadata 
# is populated with table definitions before we call create_all(). 
# We import them explicitly to ensure they are registered.
from app.db.base import Base
from app.features.organizer.tasks.tables import Task
from app.features.organizer.notes.tables import Note
from app.features.organizer.tags.tables import Tag, tasks_tags, notes_tags
from app.features.monitors.tables import Monitor, MonitorLog

# Use Admin URL to ensure we have DROP/CREATE permissions
DATABASE_ADMIN_URL = os.getenv("DATABASE_ADMIN_URL", get_settings().database_url)
if not os.getenv("DATABASE_ADMIN_URL"):
    logging.warning("DATABASE_ADMIN_URL not found in environment. Falling back to settings.database_url.")

engine = create_async_engine(DATABASE_ADMIN_URL)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_all_tables():
    """Create all tables from SQLAlchemy models."""
    # Log which tables are actually found in metadata
    detected_tables = list(Base.metadata.tables.keys())
    logger.info(f"Checking Base.metadata for tables... Found: {len(detected_tables)}")

    if not detected_tables:
        logger.error("❌ No tables found in Base.metadata! Ensure all models are imported and share the same 'Base'.")
        return

    logger.info(f"Creating tables: {', '.join(detected_tables)}")    
    async with engine.begin() as conn:
        # Explicitly create schemas defined in models
        schemas = {table.schema for table in Base.metadata.tables.values() if table.schema}
        for schema_name in schemas:
            logger.info(f"Ensuring schema '{schema_name}' exists...")
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))

        await conn.run_sync(Base.metadata.create_all)

        # Grant the app user access to any custom schemas that were just created.
        # The admin user owns the schemas/tables; the app user needs explicit grants.
        app_user = make_url(os.getenv("DATABASE_URL", "")).username
        if app_user and schemas:
            for schema_name in schemas:
                logger.info(f"Granting '{app_user}' access to schema '{schema_name}'...")
                await conn.execute(text(f"GRANT USAGE ON SCHEMA {schema_name} TO {app_user}"))
                await conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema_name} TO {app_user}"))
                await conn.execute(text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema_name} TO {app_user}"))
                await conn.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_name} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {app_user}"))
                await conn.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_name} GRANT USAGE, SELECT ON SEQUENCES TO {app_user}"))

    logger.info("✓ All tables created successfully!")


async def drop_all_tables():
    """Drop all tables."""
    detected_tables = list(Base.metadata.tables.keys())
    
    if not detected_tables:
        logger.warning("⚠ No tables found in Base.metadata to drop. Make sure all models are imported.")
        return
    logger.warning(f"Dropping {len(detected_tables)} tables...")

    async with engine.begin() as conn:
        # Drop schemas with CASCADE to ensure all tables and constraints are removed
        schemas = {table.schema for table in Base.metadata.tables.values() if table.schema}
        for schema_name in schemas:
            logger.info(f"Dropping schema '{schema_name}' CASCADE...")
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))

        # Drop tables in the public/default schema with CASCADE.
        # Also explicitly drop any legacy table names that may exist from older schema versions.
        public_tables = [t for t in Base.metadata.tables.values() if not t.schema or t.schema == 'public']
        # Tables previously in public schema before the organizer schema was introduced.
        legacy_public_names = ["tags", "tasks", "notes", "tasks_tags", "notes_tags"]
        all_public_names = {t.name for t in public_tables} | set(legacy_public_names)
        for name in all_public_names:
            logger.info(f"Dropping public table '{name}' CASCADE...")
            await conn.execute(text(f"DROP TABLE IF EXISTS {name} CASCADE"))

    logger.info("✓ All tables dropped!")


async def main():
    """Main function."""
    import sys
    
    # Parse command-line arguments
    action = "both"  # Default: drop and create
    if len(sys.argv) > 1:
        action = sys.argv[1]
    
    if action not in ("drop", "create", "both"):
        logger.error(f"Invalid action: {action}. Use 'drop', 'create', or 'both'.")
        sys.exit(1)
    
    # Mask password for security in logs using SQLAlchemy's built-in URL helper
    url = make_url(DATABASE_ADMIN_URL)
    logger.info(f"Attempting database setup as user '{url.username}' on '{url.host}:{url.port}/{url.database}'")
    
    try:
        # Drop existing tables
        if action in ("drop", "both"):
            await drop_all_tables()
        
        # Create new tables from models
        if action in ("create", "both"):
            await create_all_tables()
        
        if action == "both":
            print("\n✓ Database reset complete!")
            print("  Tables have been dropped and recreated from current ORM models.")
        elif action == "drop":
            print("\n✓ All tables dropped!")
        elif action == "create":
            print("\n✓ All tables created!")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
