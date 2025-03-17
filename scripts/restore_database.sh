#!/bin/bash
# Database restore script for kAIros production environment

# Load environment variables
source ../.env.production

# Check if backup file is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <backup_file>"
    echo "Available backups:"
    ls -lt ../backups | grep .backup
    exit 1
fi

BACKUP_FILE=$1

# Check if the backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file $BACKUP_FILE does not exist."
    echo "Available backups:"
    ls -lt ../backups | grep .backup
    exit 1
fi

# Get database connection details from environment
DB_HOST=${DB_HOST:-db}
DB_PORT=${DB_PORT:-5432}

echo "==================================================================="
echo "WARNING: This will overwrite the current database with the backup."
echo "         All existing data will be LOST!"
echo "==================================================================="
read -p "Are you sure you want to continue? (y/n): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Restore cancelled."
    exit 1
fi

echo "Starting database restore from $BACKUP_FILE..."

# Create a temporary database to restore to first (to prevent damaging the live database if restore fails)
TEMP_DB=${POSTGRES_DB}_restore_temp
echo "Creating temporary database $TEMP_DB..."
psql -h $DB_HOST -p $DB_PORT -U $POSTGRES_USER -c "DROP DATABASE IF EXISTS $TEMP_DB;"
psql -h $DB_HOST -p $DB_PORT -U $POSTGRES_USER -c "CREATE DATABASE $TEMP_DB;"

# Restore backup to temporary database
echo "Restoring to temporary database $TEMP_DB..."
pg_restore -h $DB_HOST -p $DB_PORT -U $POSTGRES_USER -d $TEMP_DB $BACKUP_FILE

# Check if restore was successful
if [ $? -eq 0 ]; then
    echo "Temporary restore successful. Proceeding with full restore."
    
    # Terminate all connections to the main database
    echo "Terminating all connections to $POSTGRES_DB..."
    psql -h $DB_HOST -p $DB_PORT -U $POSTGRES_USER -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$POSTGRES_DB' AND pid <> pg_backend_pid();"
    
    # Drop and recreate the main database
    echo "Dropping and recreating main database $POSTGRES_DB..."
    psql -h $DB_HOST -p $DB_PORT -U $POSTGRES_USER -c "DROP DATABASE IF EXISTS $POSTGRES_DB;"
    psql -h $DB_HOST -p $DB_PORT -U $POSTGRES_USER -c "CREATE DATABASE $POSTGRES_DB WITH TEMPLATE $TEMP_DB;"
    
    echo "Restore completed successfully!"
    
    # Drop the temporary database
    echo "Cleaning up temporary database..."
    psql -h $DB_HOST -p $DB_PORT -U $POSTGRES_USER -c "DROP DATABASE IF EXISTS $TEMP_DB;"
else
    echo "Restore to temporary database failed! Main database was not affected."
    psql -h $DB_HOST -p $DB_PORT -U $POSTGRES_USER -c "DROP DATABASE IF EXISTS $TEMP_DB;"
    exit 1
fi

echo "Database restore process completed."