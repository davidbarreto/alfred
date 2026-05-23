#!/bin/bash
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create the restricted app user
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DB_USER') THEN
            CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASSWORD';
        END IF;
    END \$\$;

    -- Create n8n user if it doesn't exist
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$N8N_DB_USER') THEN
            CREATE ROLE $N8N_DB_USER LOGIN PASSWORD '$N8N_DB_PASSWORD';
        END IF;
    END \$\$;

    -- Create n8n database
    CREATE DATABASE $N8N_DB_NAME;
    GRANT ALL PRIVILEGES ON DATABASE $N8N_DB_NAME TO $N8N_DB_USER;

    -- Grant permissions to the app user for the public schema
    GRANT CONNECT ON DATABASE $POSTGRES_DB TO $DB_USER;
    GRANT USAGE ON SCHEMA public TO $DB_USER;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO $DB_USER;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO $DB_USER;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$N8N_DB_NAME" <<-EOSQL
    -- Grant schema permissions for n8n user
    GRANT USAGE ON SCHEMA public TO $N8N_DB_USER;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $N8N_DB_USER;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO $N8N_DB_USER;
EOSQL
