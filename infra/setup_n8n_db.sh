#!/bin/bash

################################################################################
# n8n Database Provisioning Script
#
# This script prepares the PostgreSQL database for n8n. It must be run BEFORE
# starting the n8n service.
#
# This script:
#   1. Creates the n8n PostgreSQL user and database
#   2. Installs required PostgreSQL extensions
#
# After this script completes, start the services and then run:
#   ./import_n8n_backup.sh
#
# Usage:
#   ./setup_n8n_db.sh
#
# Prerequisites:
#   - PostgreSQL must be running
#   - .env must be present with DB credentials
#   - n8n_export/n8n_backup must contain the backup files
################################################################################

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${SCRIPT_DIR}/n8n_export/n8n_backup"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}n8n Database Setup and Restore${NC}"
echo -e "${BLUE}========================================${NC}"

# Load environment variables
if [ -f "${SCRIPT_DIR}/.env" ]; then
    echo -e "${YELLOW}Loading environment from .env${NC}"
    set -a
    source "${SCRIPT_DIR}/.env"
    set +a
else
    echo -e "${RED}Error: .env file not found at ${SCRIPT_DIR}/.env${NC}"
    exit 1
fi

# Validate required environment variables
REQUIRED_VARS=(
    "N8N_DB_HOST"
    "N8N_DB_PORT"
    "N8N_DB_NAME"
    "N8N_DB_USER"
    "N8N_DB_PASSWORD"
    "DB_ADMIN_USER"
    "DB_ADMIN_PASSWORD"
)

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo -e "${RED}Error: Required environment variable '$var' is not set${NC}"
        exit 1
    fi
done

# Database connection parameters
DB_HOST="${N8N_DB_HOST}"
DB_PORT="${N8N_DB_PORT}"
DB_NAME="${N8N_DB_NAME}"
DB_USER="${N8N_DB_USER}"
DB_PASSWORD="${N8N_DB_PASSWORD}"
ADMIN_USER="${DB_ADMIN_USER}"
ADMIN_PASSWORD="${DB_ADMIN_PASSWORD}"

# PostgreSQL connection string for admin
ADMIN_CONNSTR="postgresql://${ADMIN_USER}:${ADMIN_PASSWORD}@${DB_HOST}:${DB_PORT}"

# PostgreSQL connection string for n8n user
N8N_CONNSTR="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

echo -e "${BLUE}Configuration:${NC}"
echo "  DB Host: $DB_HOST"
echo "  DB Port: $DB_PORT"
echo "  DB Name: $DB_NAME"
echo "  DB User: $DB_USER"
echo "  Backup Dir: $BACKUP_DIR"
echo ""

if [ "$USE_DOCKER_COMPOSE" = true ]; then
    echo -e "${BLUE}Connection Method:${NC} Using ${YELLOW}docker-compose exec${NC}"
else
    echo -e "${BLUE}Connection Method:${NC} Using ${YELLOW}direct TCP connection${NC}"
fi
echo ""

# Check if backup directory exists
if [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${RED}Error: Backup directory not found: $BACKUP_DIR${NC}"
    exit 1
fi

# Check if backup files exist
if [ ! -d "$BACKUP_DIR/entities" ]; then
    echo -e "${RED}Error: Entities directory not found: $BACKUP_DIR/entities${NC}"
    exit 1
fi

# Determine connection method
USE_DOCKER_COMPOSE=false
DB_CONTAINER="db"

# Check if docker-compose is available
if command -v docker-compose &> /dev/null; then
    # Check if db service is running
    if docker-compose ps "$DB_CONTAINER" 2>/dev/null | grep -qE "Up|running"; then
        USE_DOCKER_COMPOSE=true
    fi
fi

# Function to execute SQL as admin
execute_sql_admin() {
    local sql="$1"
    
    if [ "$USE_DOCKER_COMPOSE" = true ]; then
        docker-compose exec -T "$DB_CONTAINER" psql -U "$ADMIN_USER" -d postgres -c "$sql"
    else
        PGPASSWORD="$ADMIN_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$ADMIN_USER" -d postgres -c "$sql"
    fi
}

# Function to execute SQL as n8n user
execute_sql_n8n() {
    local sql="$1"
    
    if [ "$USE_DOCKER_COMPOSE" = true ]; then
        docker-compose exec -T "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "$sql"
    else
        PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "$sql"
    fi
}

# Function to execute SQL file as n8n user
execute_sql_file_n8n() {
    local file="$1"
    
    if [ "$USE_DOCKER_COMPOSE" = true ]; then
        docker-compose exec -T "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -f "$file"
    else
        PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$file"
    fi
}

echo -e "${BLUE}Step 1: Checking PostgreSQL Connection${NC}"

if [ "$USE_DOCKER_COMPOSE" = true ]; then
    echo "Using connection method: docker-compose exec"
else
    echo "Using connection method: direct TCP connection"
fi

if execute_sql_admin "SELECT 1;" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PostgreSQL is accessible${NC}"
else
    echo -e "${RED}✗ Cannot connect to PostgreSQL${NC}"
    echo ""
    echo -e "${YELLOW}Troubleshooting:${NC}"
    if [ "$USE_DOCKER_COMPOSE" = false ]; then
        echo "  1. Ensure PostgreSQL container is running:"
        echo "     docker-compose ps db"
        echo "  2. Start services if needed:"
        echo "     docker-compose up -d"
        echo "  3. Verify credentials in .env file"
    fi
    exit 1
fi

echo ""
echo -e "${BLUE}Step 2: Creating n8n Database${NC}"

# First, ensure the database user exists
echo "Ensuring database user '$DB_USER' exists..."
if execute_sql_admin "SELECT 1 FROM pg_user WHERE usename='$DB_USER';" 2>/dev/null | grep -q "1"; then
    echo -e "${GREEN}✓ User '$DB_USER' already exists${NC}"
else
    echo "Creating user '$DB_USER'..."
    execute_sql_admin "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"
    echo -e "${GREEN}✓ User '$DB_USER' created${NC}"
fi

echo ""

# Check if database exists
DB_EXISTS=$(PGPASSWORD="$ADMIN_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$ADMIN_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" || echo "0")

if [ "$DB_EXISTS" = "1" ]; then
    echo -e "${YELLOW}Database '$DB_NAME' already exists${NC}"
    read -p "Do you want to DROP and recreate it? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Dropping existing database..."
        execute_sql_admin "DROP DATABASE IF EXISTS $DB_NAME;"
        echo "Creating new database..."
        execute_sql_admin "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
        echo -e "${GREEN}✓ Database recreated${NC}"
    else
        echo -e "${YELLOW}Keeping existing database${NC}"
    fi
else
    echo "Creating database '$DB_NAME'..."
    execute_sql_admin "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
    echo -e "${GREEN}✓ Database created${NC}"
fi

echo ""
echo -e "${BLUE}Step 3: Installing PostgreSQL Extensions${NC}"

# Install required extensions
EXTENSIONS=("uuid-ossp" "citext" "ltree")
for ext in "${EXTENSIONS[@]}"; do
    if execute_sql_n8n "CREATE EXTENSION IF NOT EXISTS \"$ext\";" 2>/dev/null; then
        echo -e "${GREEN}✓ Extension '$ext' ready${NC}"
    else
        echo -e "${YELLOW}⚠ Could not create extension '$ext' (may not be needed)${NC}"
    fi
done

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ n8n Database Provisioning Complete!${NC}"
echo -e "${BLUE}========================================${NC}"

echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Start the services:"
echo "   docker-compose up -d"
echo ""
echo "2. Once n8n is running, restore workflows, credentials and entities:"
echo "   ./import_n8n_backup.sh"
echo ""
