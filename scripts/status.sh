#!/bin/bash
# Script to check status of kAIros application containers

# Usage information
function show_usage {
    echo "Usage: $0 [--env development|production]"
    echo "  --env      Environment to check (default: development)"
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
    echo "Checking production environment..."
else
    COMPOSE_FILE="docker/docker-compose.dev.yml"
    echo "Checking development environment..."
fi

# Print divider line
function print_divider {
    echo "================================================================================"
}

# Show container status
print_divider
echo "CONTAINER STATUS:"
print_divider
docker-compose -f "$COMPOSE_FILE" ps
echo ""

# Show container health
print_divider
echo "CONTAINER HEALTH:"
print_divider
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Health}}"
echo ""

# Show disk usage
print_divider
echo "DISK USAGE:"
print_divider
docker system df
echo ""

# Show application health check
if [[ "$ENV" == "production" ]]; then
    print_divider
    echo "APPLICATION HEALTH CHECK:"
    print_divider
    # Try different endpoints in case NGINX isn't running yet
    if curl -s --fail http://localhost/health > /dev/null; then
        curl -s http://localhost/health | python -m json.tool
    elif curl -s --fail http://localhost:5000/health > /dev/null; then
        curl -s http://localhost:5000/health | python -m json.tool
    else
        echo "Health check endpoint not accessible"
    fi
    echo ""
fi

# Show logs for specific errors
print_divider
echo "RECENT ERRORS (last 10 lines of each service):"
print_divider
if [[ "$ENV" == "production" ]]; then
    echo "APP ERRORS:"
    docker-compose -f "$COMPOSE_FILE" logs --tail=10 app | grep -i "error\|exception\|traceback" || echo "No recent errors found"
    echo ""
    
    echo "NGINX ERRORS:"
    docker-compose -f "$COMPOSE_FILE" logs --tail=10 nginx | grep -i "error" || echo "No recent errors found"
    echo ""
    
    echo "DATABASE ERRORS:"
    docker-compose -f "$COMPOSE_FILE" logs --tail=10 db | grep -i "error\|fatal" || echo "No recent errors found"
else
    echo "APP ERRORS:"
    docker-compose -f "$COMPOSE_FILE" logs --tail=10 app | grep -i "error\|exception\|traceback" || echo "No recent errors found"
fi
echo ""

print_divider
echo "STATUS CHECK COMPLETE"
print_divider