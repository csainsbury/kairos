#!/bin/bash
# Database backup script for kAIros production environment

# Load environment variables
source ../.env.production

# Set backup directory
BACKUP_DIR="../backups"
mkdir -p $BACKUP_DIR

# Set timestamp for backup filename
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/kairos_$TIMESTAMP.backup"

# Get database connection details from environment
DB_HOST=${DB_HOST:-db}
DB_PORT=${DB_PORT:-5432}

echo "Starting PostgreSQL backup to $BACKUP_FILE..."

# Create backup using pg_dump (custom format for better restore capabilities)
pg_dump -h $DB_HOST -p $DB_PORT -U $POSTGRES_USER -d $POSTGRES_DB -F c -f $BACKUP_FILE

# Check if backup was successful
if [ $? -eq 0 ]; then
    echo "Backup successfully created at $BACKUP_FILE"
    # Calculate size of backup
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "Backup size: $BACKUP_SIZE"
    
    # Clean up old backups (keep only last 7 days)
    echo "Cleaning up old backups (older than 7 days)..."
    find $BACKUP_DIR -name "*.backup" -type f -mtime +7 -delete
    
    # List remaining backups
    echo "Remaining backups:"
    ls -lh $BACKUP_DIR | grep .backup
else
    echo "Backup failed!"
    exit 1
fi

echo "Backup process completed."