#!/bin/sh
set -e

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="/backup"
PG_HOST="chronicle-db"
PG_USER="chronicle_user"

echo "Starting backup for chronicle_db..."
pg_dump --host=$PG_HOST --username=$PG_USER --dbname=chronicle_db --file=$BACKUP_DIR/chronicle_db_dump-$TIMESTAMP.sql --format=p --clean --if-exists

echo "Starting backup for agent_memory..."
pg_dump --host=$PG_HOST --username=$PG_USER --dbname=agent_memory --file=$BACKUP_DIR/agent_memory_dump-$TIMESTAMP.sql --format=p --clean --if-exists

echo "Backup completed successfully."
