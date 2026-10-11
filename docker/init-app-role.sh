#!/usr/bin/env bash
# Runs on a fresh volume; can also be invoked explicitly for an existing volume.
set -Eeuo pipefail

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${DB_USER:?DB_USER is required}"

if [[ ! "$DB_USER" =~ ^[a-z_][a-z0-9_]{0,62}$ || "$DB_USER" == "$POSTGRES_USER" || "$DB_USER" == pg_* ]]; then
    echo "DB_USER must be a dedicated application role with a valid identifier." >&2
    exit 1
fi

read_password() {
    local name="$1" file_name="${1}_FILE" value="${!1:-}"
    if [[ -n "$value" && -n "${!file_name:-}" ]]; then
        echo "Set only one of $name or $file_name." >&2
        exit 1
    fi
    if [[ -n "${!file_name:-}" ]]; then
        value="$(cat -- "${!file_name}")"
    fi
    if [[ -z "${value//[[:space:]]/}" || "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
        echo "$name must be nonempty and single-line." >&2
        exit 1
    fi
    export "$name=$value"
}

read_password DB_PASSWORD
read_password POSTGRES_PASSWORD
if [[ "$DB_PASSWORD" == "$POSTGRES_PASSWORD" ]]; then
    echo "Application and administrator passwords must be different." >&2
    exit 1
fi

# Read passwords inside psql so they never appear in command-line arguments.
# Use psql's identifier/literal quoting, not shell interpolation into SQL.
psql -X -q --set ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv app_user DB_USER
\getenv app_password DB_PASSWORD
\getenv admin_user POSTGRES_USER
\getenv admin_password POSTGRES_PASSWORD
\getenv db_name POSTGRES_DB
BEGIN;
SET LOCAL log_statement = 'none';
SET LOCAL log_min_error_statement = 'panic';
SELECT format('CREATE ROLE %I', :'app_user')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_user') \gexec
ALTER ROLE :"app_user" WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD :'app_password';
ALTER ROLE :"admin_user" PASSWORD :'admin_password';
REVOKE ALL ON DATABASE :"db_name" FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE :"db_name" FROM :"app_user";
REVOKE ALL ON SCHEMA public FROM :"app_user";
GRANT CONNECT ON DATABASE :"db_name" TO :"app_user";
COMMIT;
SQL

echo "Application role configured with CONNECT only (SELECT 1 needs no table privileges)."
