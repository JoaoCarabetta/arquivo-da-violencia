#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE arquivo_staging'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'arquivo_staging')\gexec
EOSQL
