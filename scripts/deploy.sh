#!/bin/bash
# Deployment script for kAIros application

# Usage information
function show_usage {
    echo "Usage: $0 [--env development|production]"
    echo "  --env      Environment to deploy (default: development)"
    exit 1
}

# Parse command line arguments
ENV="development"  # Default environment
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --env)
        ENV="$2"
        shift 2
        ;;
        --help)
        show_usage
        ;;
        *)
        echo "Unknown option: $1"
        show_usage
        ;;
    esac
done

# Validate environment
if [[ "$ENV" != "development" && "$ENV" != "production" ]]; then
    echo "Error: Environment must be either 'development' or 'production'"
    show_usage
fi

# Set environment-specific variables
if [[ "$ENV" == "production" ]]; then
    COMPOSE_FILE="docker/docker-compose.prod.yml"
    ENV_FILE=".env.production"
    echo "Deploying production environment..."
else
    COMPOSE_FILE="docker/docker-compose.dev.yml"
    ENV_FILE=".env.development"
    echo "Deploying development environment..."
fi

# Check if environment file exists
if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: Environment file $ENV_FILE does not exist"
    echo "Please create it first (you can copy from the template)"
    exit 1
fi

# Create required directories
echo "Creating required directories..."
mkdir -p uploads
mkdir -p logs
mkdir -p backups
mkdir -p ssl_certs
mkdir -p static/error_pages

# Check if domain is configured (for production only)
if [[ "$ENV" == "production" ]]; then
    DOMAIN_NAME=$(grep DOMAIN_NAME "$ENV_FILE" | cut -d= -f2)
    if [[ -z "$DOMAIN_NAME" || "$DOMAIN_NAME" == "your-domain.com" ]]; then
        echo "Warning: DOMAIN_NAME in $ENV_FILE is not set or has default value"
        echo "Update domain name in $ENV_FILE before proceeding"
        read -p "Continue anyway? (y/n): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
fi

# Stop any running containers
echo "Stopping any running containers..."
docker-compose -f "$COMPOSE_FILE" down

# Pull the latest changes if in a git repository
if [ -d ".git" ]; then
    echo "Pulling latest changes from git repository..."
    git pull
fi

# Build and start containers
echo "Building and starting containers..."
docker-compose -f "$COMPOSE_FILE" up -d --build

# Setup database if needed (only for development)
if [[ "$ENV" == "development" ]]; then
    echo "Setting up development database..."
    docker-compose -f "$COMPOSE_FILE" exec app flask db upgrade
fi

# Check container status
echo "Checking container status..."
docker-compose -f "$COMPOSE_FILE" ps

# Display health status for production
if [[ "$ENV" == "production" ]]; then
    echo "Waiting for application to be ready..."
    sleep 10
    
    # Check health status
    echo "Health check status:"
    curl -s http://localhost/health | python -m json.tool
    
    echo ""
    echo "Production deployment complete!"
    echo "IMPORTANT: Configure SSL certificates for production use:"
    echo "  1. Update nginx/conf.d/kairos.conf with your domain information"
    echo "  2. Use Let's Encrypt certbot to generate certificates"
    echo "     certbot certonly --webroot -w /var/www/certbot -d $DOMAIN_NAME -d www.$DOMAIN_NAME"
    echo "  3. Place certificates in ssl_certs directory"
else
    echo ""
    echo "Development deployment complete!"
    echo "Access the application at: http://localhost:5000"
fi