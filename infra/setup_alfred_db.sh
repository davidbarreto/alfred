#!/bin/bash

################################################################################
# Alfred Database Setup Script
#
# This script drops and recreates all Alfred tables using the setup_db.py script.
# It runs the Python setup script inside the API container to ensure all
# dependencies are available.
#
# Usage:
#   ./setup_alfred_db.sh
#   ./setup_alfred_db.sh --drop-only
#   ./setup_alfred_db.sh --create-only
#
# Prerequisites:
#   - docker-compose must be running
#   - API service must be available
#   - .env file must be configured
################################################################################

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")/backend"
SETUP_SCRIPT="${BACKEND_DIR}/setup_db.py"

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
    "DB_HOST"
    "DB_PORT"
    "DB_NAME"
    "DB_USER"
    "DB_PASSWORD"
    "DB_ADMIN_USER"
    "DB_ADMIN_PASSWORD"
)

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo -e "${RED}Error: Required environment variable '$var' is not set${NC}"
        exit 1
    fi
done

# Parse command line arguments
ACTION="both" # Default: drop and create

while [[ $# -gt 0 ]]; do
    case $1 in
        --drop-only)
            ACTION="drop"
            shift
            ;;
        --create-only)
            ACTION="create"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--drop-only|--create-only]"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Alfred Database Setup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}Error: docker-compose is not available${NC}"
    exit 1
fi

# Determine docker-compose command
DOCKER_COMPOSE_CMD="docker-compose"
if ! command -v docker-compose &> /dev/null && docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
fi

# Check if API service is running
echo -e "${BLUE}Checking services...${NC}"
if ! $DOCKER_COMPOSE_CMD -f "${SCRIPT_DIR}/docker-compose.yml" ps api 2>/dev/null | grep -q "Up"; then
    echo -e "${RED}Error: API service is not running${NC}"
    echo "Start it with: docker-compose up -d"
    exit 1
fi

echo -e "${GREEN}✓ API service is running${NC}"
echo ""

# Check if setup script exists
if [ ! -f "$SETUP_SCRIPT" ]; then
    echo -e "${RED}Error: setup_db.py not found at ${SETUP_SCRIPT}${NC}"
    exit 1
fi

echo -e "${BLUE}Configuration:${NC}"
echo "  DB Host: $DB_HOST"
echo "  DB Port: $DB_PORT"
echo "  DB Name: $DB_NAME"
echo "  DB User: $DB_USER"
echo ""

echo -e "${BLUE}Running database setup...${NC}"
echo ""

# Copy the latest setup_db.py into the container so local edits take effect immediately
# without requiring a full image rebuild.
CONTAINER_ID=$($DOCKER_COMPOSE_CMD -f "${SCRIPT_DIR}/docker-compose.yml" ps -q api)
echo -e "${BLUE}Syncing setup script into container...${NC}"
docker cp "${SETUP_SCRIPT}" "${CONTAINER_ID}:/app/setup_db.py"

# Construct the admin URL from individual components (sourced from .env above via bash,
# which expands variables — unlike Docker Compose, which reads .env values literally).
CONSTRUCTED_ADMIN_URL="postgresql+asyncpg://${DB_ADMIN_USER}:${DB_ADMIN_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

# Run the setup script inside the API container, injecting the resolved admin URL
if $DOCKER_COMPOSE_CMD -f "${SCRIPT_DIR}/docker-compose.yml" exec -T \
    -e "DATABASE_ADMIN_URL=${CONSTRUCTED_ADMIN_URL}" \
    api python setup_db.py "$ACTION"; then
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${GREEN}✓ Database setup complete!${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
else
    echo ""
    echo -e "${RED}Error: Database setup failed${NC}"
    exit 1
fi
