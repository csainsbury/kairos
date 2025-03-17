#!/bin/bash
# Database setup script for kAIros

# Default to development environment
ENV="development"
CREATE_DEMO_DATA=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --env)
            ENV="$2"
            shift 2
            ;;
        --demo)
            CREATE_DEMO_DATA=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate environment
if [[ "$ENV" != "development" && "$ENV" != "production" && "$ENV" != "testing" ]]; then
    echo "Invalid environment: $ENV"
    echo "Valid options: development, production, testing"
    exit 1
fi

# Set environment variable for Flask
export FLASK_ENV=$ENV

echo "Setting up $ENV database..."

# Check if we need demo data
DEMO_FLAG=""
if [[ "$CREATE_DEMO_DATA" = true && "$ENV" = "development" ]]; then
    DEMO_FLAG="--demo"
    echo "Will create demo data for development environment"
fi

# Run database initialization
python init_db.py --env $ENV $DEMO_FLAG

# Check if initialization was successful
if [ $? -eq 0 ]; then
    echo "Database setup complete!"
    exit 0
else
    echo "Database setup failed."
    exit 1
fi