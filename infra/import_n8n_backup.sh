#!/bin/bash

################################################################################
# n8n Backup Import Script
#
# Restores workflows, credentials, and entities into a running n8n instance.
# This is the SECOND step of the n8n setup — run setup_n8n_db.sh first.
#
# Usage:
#   ./import_n8n_backup.sh                        # import everything
#   ./import_n8n_backup.sh --workflows-only
#   ./import_n8n_backup.sh --credentials-only
#   ./import_n8n_backup.sh --entities-only
#   ./import_n8n_backup.sh --repair-entities      # clean stale tables then re-import entities
#   ./import_n8n_backup.sh --cleanup-public-entities-only
#
# Prerequisites:
#   - setup_n8n_db.sh must have been run first (DB must exist)
#   - n8n container must be running: docker-compose up -d
#   - n8n_export/n8n_backup must contain the backup files
################################################################################

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${SCRIPT_DIR}/n8n_export/n8n_backup"
N8N_CONTAINER="n8n"
DOCKER_COMPOSE_CMD=""

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
    "DB_HOST"
    "DB_PORT"
    "DB_NAME"
    "DB_ADMIN_USER"
    "DB_ADMIN_PASSWORD"
)

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo -e "${RED}Error: Required environment variable '$var' is not set${NC}"
        exit 1
    fi
done

IMPORT_WORKFLOWS=true
IMPORT_CREDENTIALS=true
IMPORT_ENTITIES=true
CLEANUP_PUBLIC_ENTITIES=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --workflows-only)
            IMPORT_CREDENTIALS=false
            IMPORT_ENTITIES=false
            shift
            ;;
        --credentials-only)
            IMPORT_WORKFLOWS=false
            IMPORT_ENTITIES=false
            shift
            ;;
        --entities-only)
            IMPORT_WORKFLOWS=false
            IMPORT_CREDENTIALS=false
            IMPORT_ENTITIES=true
            shift
            ;;
        --repair-entities)
            IMPORT_WORKFLOWS=false
            IMPORT_CREDENTIALS=false
            IMPORT_ENTITIES=true
            CLEANUP_PUBLIC_ENTITIES=true
            shift
            ;;
        --cleanup-public-entities-only)
            IMPORT_WORKFLOWS=false
            IMPORT_CREDENTIALS=false
            IMPORT_ENTITIES=false
            CLEANUP_PUBLIC_ENTITIES=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}n8n Backup Import${NC}"
echo -e "${BLUE}========================================${NC}"

# Check if n8n container is running when import actions are requested
if [ "$IMPORT_WORKFLOWS" = true ] || [ "$IMPORT_CREDENTIALS" = true ] || [ "$IMPORT_ENTITIES" = true ]; then
    if ! docker ps --format '{{.Names}}' | grep -q "^${N8N_CONTAINER}$"; then
        echo -e "${RED}Error: n8n container is not running${NC}"
        echo "Start it with: docker-compose up -d"
        exit 1
    fi

    echo -e "${GREEN}✓ n8n container is running${NC}"
    echo ""
else
    echo -e "${YELLOW}Note: No n8n import action requested; skipping n8n container check${NC}"
    echo ""
fi

# Verify backup directory
if [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${RED}Error: Backup directory not found: $BACKUP_DIR${NC}"
    exit 1
fi

# Function to check if file exists in container
container_file_exists() {
    docker exec "$N8N_CONTAINER" test -f "$1" 2>/dev/null
}

# Function to run command in container
run_in_container() {
    docker exec -i "$N8N_CONTAINER" "$@"
}

# Function to copy file to container
copy_to_container() {
    local src="$1"
    local dest="$2"
    docker cp "$src" "${N8N_CONTAINER}:${dest}"
}

# Detect Docker Compose command if available
if command -v docker >/dev/null 2>&1 && command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE_CMD="docker-compose"
elif command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE_CMD="docker compose"
fi

# Returns true when the db service is running in Docker Compose
db_container_running() {
    if [ -n "$DOCKER_COMPOSE_CMD" ]; then
        [ -n "$($DOCKER_COMPOSE_CMD -f "$SCRIPT_DIR/docker-compose.yml" ps -q db 2>/dev/null)" ]
    else
        docker ps --format '{{.Names}}' | grep -q '^db$'
    fi
}

# Execute a SQL query against a specific database using postgres admin credentials.
psql_exec() {
    local dbname="$1"
    local sql="$2"

    if db_container_running; then
        if [ -n "$DOCKER_COMPOSE_CMD" ]; then
            $DOCKER_COMPOSE_CMD -f "$SCRIPT_DIR/docker-compose.yml" exec -T db psql -U "$DB_ADMIN_USER" -d "$dbname" -At -c "$sql"
        else
            docker exec -i db sh -lc "PGPASSWORD='$DB_ADMIN_PASSWORD' psql -h localhost -p 5432 -U '$DB_ADMIN_USER' -d '$dbname' -At -c \"$sql\""
        fi
    elif command -v psql >/dev/null 2>&1; then
        PGPASSWORD="$DB_ADMIN_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_ADMIN_USER" -d "$dbname" -At -c "$sql"
    else
        echo -e "${RED}Error: psql is not installed locally and the db container is not available via docker-compose${NC}"
        exit 1
    fi
}

cleanup_public_entities() {
    echo -e "${BLUE}Step 0: Cleaning up stale n8n tables from $DB_NAME${NC}"

    APP_TABLES=$(psql_exec "$DB_NAME" "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public';")
    N8N_TABLES=$(psql_exec "$N8N_DB_NAME" "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public';")

    if [ -z "$APP_TABLES" ] || [ -z "$N8N_TABLES" ]; then
        echo -e "${RED}Error: Could not query table lists from the databases${NC}"
        exit 1
    fi

    DROP_TABLES=()
    while IFS= read -r table; do
        if echo "$N8N_TABLES" | grep -xq "$table"; then
            DROP_TABLES+=("$table")
        fi
    done <<< "$APP_TABLES"

    if [ ${#DROP_TABLES[@]} -eq 0 ]; then
        echo -e "${GREEN}✓ No n8n tables found in $DB_NAME${NC}"
        return
    fi

    echo "The following tables will be removed from $DB_NAME:"
    for table in "${DROP_TABLES[@]}"; do
        echo "  - $table"
    done

    read -p "Continue and DROP these tables from $DB_NAME? (y/N): " -r
    echo
    if ! [[ "$REPLY" =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Cleanup aborted${NC}"
        exit 1
    fi

    DROP_SQL=""
    for table in "${DROP_TABLES[@]}"; do
        DROP_SQL+="DROP TABLE IF EXISTS public.\"$table\" CASCADE; "
    done

    if psql_exec "$DB_NAME" "$DROP_SQL"; then
        echo -e "${GREEN}✓ Removed ${#DROP_TABLES[@]} n8n tables from $DB_NAME${NC}"
    else
        echo -e "${RED}✗ Failed to remove n8n tables from $DB_NAME${NC}"
        exit 1
    fi
    echo
}

echo -e "${BLUE}Step 1: Preparing Backup Files${NC}"

# Create temp directory in container for backup files
CONTAINER_BACKUP_DIR="/tmp/n8n_backup_$$"
run_in_container mkdir -p "$CONTAINER_BACKUP_DIR/workflows"
run_in_container mkdir -p "$CONTAINER_BACKUP_DIR/credentials"
run_in_container mkdir -p "$CONTAINER_BACKUP_DIR/entities"

echo -e "${GREEN}✓ Backup directories created in container${NC}"
echo ""

# Import workflows
if [ "$IMPORT_WORKFLOWS" = true ]; then
    echo -e "${BLUE}Step 2: Importing Workflows${NC}"
    
    WORKFLOW_FILES=("$BACKUP_DIR/n8n_backup_workflows"/*.json)
    WORKFLOW_COUNT=${#WORKFLOW_FILES[@]}
    
    if [ -f "${WORKFLOW_FILES[0]}" ]; then
        echo "Found $WORKFLOW_COUNT workflows to import"
        
        # Copy workflows to container
        for workflow_file in "${WORKFLOW_FILES[@]}"; do
            filename=$(basename "$workflow_file")
            echo "  → Copying $filename..."
            copy_to_container "$workflow_file" "$CONTAINER_BACKUP_DIR/workflows/$filename"
        done
        
        echo ""
        echo "Importing workflows into n8n..."
        
        # Import each workflow
        IMPORT_SUCCESS=0
        IMPORT_FAILED=0
        
        for workflow_file in "${WORKFLOW_FILES[@]}"; do
            filename=$(basename "$workflow_file")
            container_path="$CONTAINER_BACKUP_DIR/workflows/$filename"
            
            if run_in_container n8n import:workflow --input "$container_path" > /dev/null 2>&1; then
                echo -e "${GREEN}✓${NC} Imported: $filename"
                IMPORT_SUCCESS=$((IMPORT_SUCCESS + 1))
            else
                echo -e "${RED}✗${NC} Failed: $filename"
                IMPORT_FAILED=$((IMPORT_FAILED + 1))
            fi
        done
        
        echo ""
        echo -e "${GREEN}Workflows imported: $IMPORT_SUCCESS${NC}"
        if [ $IMPORT_FAILED -gt 0 ]; then
            echo -e "${YELLOW}Workflows failed: $IMPORT_FAILED${NC}"
        fi
        
        # Cleanup
        run_in_container rm -rf "$CONTAINER_BACKUP_DIR/workflows"
    else
        echo -e "${YELLOW}No workflow files found${NC}"
    fi
    echo ""
fi

# Import credentials
if [ "$IMPORT_CREDENTIALS" = true ]; then
    echo -e "${BLUE}Step 3: Importing Credentials${NC}"
    
    # Try decrypted credentials first (more likely to work)
    CRED_DIR="$BACKUP_DIR/n8n_backup_credentials_decrypted"
    
    if [ ! -d "$CRED_DIR" ] || [ -z "$(ls -A "$CRED_DIR")" ]; then
        # Fall back to encrypted credentials
        CRED_DIR="$BACKUP_DIR/n8n_backup_credentials"
        echo -e "${YELLOW}Using encrypted credentials (decrypted not available)${NC}"
    else
        echo -e "${GREEN}Using decrypted credentials${NC}"
    fi
    
    CRED_FILES=("$CRED_DIR"/*.json)
    CRED_COUNT=${#CRED_FILES[@]}
    
    if [ -f "${CRED_FILES[0]}" ]; then
        echo "Found $CRED_COUNT credential files"
        
        # Copy credentials to container
        for cred_file in "${CRED_FILES[@]}"; do
            filename=$(basename "$cred_file")
            echo "  → Copying $filename..."
            copy_to_container "$cred_file" "$CONTAINER_BACKUP_DIR/credentials/$filename"
        done
        
        echo ""
        echo "Importing credentials into n8n..."
        
        credential_dir="$CONTAINER_BACKUP_DIR/credentials"
        
        if run_in_container n8n import:credentials --separate --input "$credential_dir" > /tmp/n8n_credential_import.log 2>&1; then
            echo -e "${GREEN}✓ Credentials imported successfully${NC}"
        else
            echo -e "${RED}✗ Credentials import failed${NC}"
            echo "Credential import output:"
            run_in_container cat /tmp/n8n_credential_import.log || true
        fi
        
        # Cleanup
        run_in_container rm -rf "$CONTAINER_BACKUP_DIR/credentials"
    else
        echo -e "${YELLOW}No credential files found${NC}"
    fi
    echo ""
fi

# Import entities via n8n CLI
if [ "$IMPORT_ENTITIES" = true ]; then
    if [ "$CLEANUP_PUBLIC_ENTITIES" = true ]; then
        cleanup_public_entities
    fi

    echo -e "${BLUE}Step 4: Importing Entities${NC}"

    if [ -d "$BACKUP_DIR/entities" ] && [ -f "$BACKUP_DIR/entities.zip" ]; then
        echo "Copying entity files into container..."
        docker cp "$BACKUP_DIR/entities/." "${N8N_CONTAINER}:$CONTAINER_BACKUP_DIR/entities/"
        docker cp "$BACKUP_DIR/entities.zip" "${N8N_CONTAINER}:$CONTAINER_BACKUP_DIR/entities.zip"

        echo "Importing entities into n8n..."
        
        if run_in_container sh -lc "DB_POSTGRESDB_USER='$DB_ADMIN_USER' DB_POSTGRESDB_PASSWORD='$DB_ADMIN_PASSWORD' DB_POSTGRESDB_DATABASE='$N8N_DB_NAME' DB_POSTGRESDB_HOST='$N8N_DB_HOST' DB_POSTGRESDB_PORT='$N8N_DB_PORT' n8n import:entities --inputDir='$CONTAINER_BACKUP_DIR' --truncateTables --skipMigrationChecks"; then
            echo -e "${GREEN}✓ Entities imported successfully${NC}"
        else
            echo -e "${RED}✗ Entity import failed${NC}"
            echo -e "${YELLOW}Run the command manually to inspect errors:${NC}"
            echo "  docker exec $N8N_CONTAINER sh -lc 'DB_POSTGRESDB_USER=... DB_POSTGRESDB_PASSWORD=... DB_POSTGRESDB_DATABASE=... DB_POSTGRESDB_HOST=... DB_POSTGRESDB_PORT=... n8n import:entities --inputDir=$CONTAINER_BACKUP_DIR --truncateTables --skipMigrationChecks'"
        fi
    else
        if [ ! -d "$BACKUP_DIR/entities" ]; then
            echo -e "${YELLOW}No entity backup directory found: $BACKUP_DIR/entities${NC}"
        fi
        if [ ! -f "$BACKUP_DIR/entities.zip" ]; then
            echo -e "${YELLOW}Entity archive not found: $BACKUP_DIR/entities.zip${NC}"
        fi
    fi
    echo ""
fi

# Cleanup container backup directory
run_in_container rm -rf "$CONTAINER_BACKUP_DIR" || true

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ Import Complete!${NC}"
echo -e "${BLUE}========================================${NC}"

echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Verify workflows in n8n UI: http://localhost:5678"
echo "2. Check credentials are available in settings"
echo "3. Re-authenticate any external service credentials if needed"
echo ""
