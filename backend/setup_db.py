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

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.engine import make_url
from app.core.config import settings
# Important: We must import the models so that SQLAlchemy's Base.metadata 
# is populated with table definitions before we call create_all(). 
# We import them explicitly to ensure they are registered.
from app.db.base import Base
from app.db.models import Monitor, MonitorLog  # noqa: F401

# Use Admin URL to ensure we have DROP/CREATE permissions
DATABASE_ADMIN_URL = os.getenv("DATABASE_ADMIN_URL", settings.database_url)
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
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("✓ All tables created successfully!")


async def drop_all_tables():
    """Drop all tables."""
    logger.warning("Dropping all tables...")
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    logger.info("✓ All tables dropped!")


async def main():
    """Main function."""
    # Mask password for security in logs using SQLAlchemy's built-in URL helper
    url = make_url(DATABASE_ADMIN_URL)
    logger.info(f"Attempting database setup as user '{url.username}' on '{url.host}:{url.port}{url.database}'")
    
    try:
        # Drop existing tables
        await drop_all_tables()
        
        # Create new tables from models
        await create_all_tables()
        
        print("\n✓ Database reset complete!")
        print("  Tables have been recreated from current ORM models.")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
