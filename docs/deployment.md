# kAIros Deployment Guide

This guide provides detailed instructions for deploying the kAIros application in both development and production environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Development Deployment](#development-deployment)
3. [Production Deployment](#production-deployment)
4. [Environment Configuration](#environment-configuration)
5. [Database Management](#database-management)
6. [SSL Configuration](#ssl-configuration)
7. [Monitoring](#monitoring)
8. [Troubleshooting](#troubleshooting)

## Prerequisites

Before deploying kAIros, ensure you have the following:

- Docker and Docker Compose installed
- Git (if deploying from repository)
- Access to required API keys:
  - LLM API (for document summarization)
  - Google Calendar API
  - Todoist API (if using integration)
- Domain name (for production deployment)
- SMTP server details (for email reports)

## Development Deployment

Development deployment uses SQLite for simplicity and is intended for local testing.

1. Clone the repository:
   ```
   git clone [repository-url]
   cd kAIros
   ```

2. Create environment file:
   ```
   cp .env.development.template .env.development
   ```

3. Update the environment variables in `.env.development` with appropriate values.

4. Run the deployment script:
   ```
   ./scripts/deploy.sh --env development
   ```

5. Access the application at http://localhost:5000

## Production Deployment

### Server Preparation

1. Provision an Ubuntu server (20.04 LTS or later recommended)
2. Install required packages:
   ```
   apt update
   apt install -y docker.io docker-compose git certbot python3-certbot-nginx
   ```

3. Set up a user with Docker permissions:
   ```
   useradd -m -s /bin/bash kairos
   usermod -aG docker kairos
   ```

4. Configure firewall:
   ```
   ufw allow ssh
   ufw allow http
   ufw allow https
   ufw enable
   ```

### Application Deployment

1. Clone the repository:
   ```
   git clone [repository-url] /opt/kairos
   cd /opt/kairos
   ```

2. Create production environment file:
   ```
   cp .env.production.template .env.production
   ```

3. Update environment variables in `.env.production` with secure values:
   - Generate a strong SECRET_KEY
   - Set secure database passwords
   - Configure API keys
   - Set DOMAIN_NAME to your domain
   - Configure email settings

4. Deploy using the script:
   ```
   ./scripts/deploy.sh --env production
   ```

5. Configure SSL certificates (see [SSL Configuration](#ssl-configuration))

## Environment Configuration

The application uses environment-specific configuration files:

### `.env.development`
- Used for local development
- Configures SQLite or local PostgreSQL
- Uses development-friendly logging levels
- Enables debugging features

### `.env.production`
- Used for production deployment
- Enforces security best practices
- Configures PostgreSQL for data persistence
- Uses structured JSON logging
- Disables debugging features

Important production settings:

```
# Security
SECRET_KEY=<generate-a-secure-random-key>
SESSION_COOKIE_SECURE=True
REMEMBER_COOKIE_SECURE=True
SESSION_COOKIE_HTTPONLY=True

# Domain
DOMAIN_NAME=your-domain.com

# Database
POSTGRES_USER=kairos_prod
POSTGRES_PASSWORD=<secure-password>
POSTGRES_DB=kairos_production
DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}

# Logging
LOG_DIR=/var/log/kairos
LOG_LEVEL=WARNING
LOG_FORMAT=json
```

## Database Management

### Backups

Automated daily backups are configured through the backup container. To manually backup:

```
./scripts/backup_database.sh
```

Backups are stored in the `/backups` directory. Old backups (older than 7 days) are automatically pruned.

### Restore

To restore from a backup:

```
./scripts/restore_database.sh /backups/kairos_20250311_120000.backup
```

## SSL Configuration

The application uses NGINX with Let's Encrypt SSL certificates:

1. Update domain in `.env.production`:
   ```
   DOMAIN_NAME=your-domain.com
   ```

2. Obtain SSL certificates:
   ```
   certbot certonly --webroot -w /var/www/certbot \
     -d your-domain.com -d www.your-domain.com
   ```

3. Copy certificates to the SSL directory:
   ```
   cp /etc/letsencrypt/live/your-domain.com/fullchain.pem /opt/kairos/ssl_certs/your-domain.com.pem
   cp /etc/letsencrypt/live/your-domain.com/privkey.pem /opt/kairos/ssl_certs/your-domain.com.key
   ```

4. Restart NGINX container:
   ```
   docker-compose -f docker/docker-compose.prod.yml restart nginx
   ```

5. Set up auto-renewal:
   ```
   crontab -e
   ```
   Add: `0 3 * * * certbot renew --quiet && docker-compose -f /opt/kairos/docker/docker-compose.prod.yml restart nginx`

## Monitoring

The application includes a health check endpoint at `/health` that provides status information for all components. You can integrate this with monitoring tools like:

- Prometheus + Grafana
- Datadog
- New Relic
- Uptime Robot

Example using curl:
```
curl -s https://your-domain.com/health | python -m json.tool
```

## Troubleshooting

### Common Issues

1. **Database Connection Errors**
   - Check if the database container is running: `docker ps`
   - Verify database credentials in `.env.production`
   - Check logs: `docker-compose -f docker/docker-compose.prod.yml logs db`

2. **API Integration Issues**
   - Verify API keys in environment file
   - Check application logs for specific error messages
   - Ensure redirect URIs are correctly configured in API provider dashboards

3. **SSL Certificate Problems**
   - Verify certificates exist in the correct location
   - Check NGINX configuration
   - Ensure domain names match in configuration files
   - Review NGINX logs: `docker-compose -f docker/docker-compose.prod.yml logs nginx`

### Viewing Logs

```
# View specific container logs
docker-compose -f docker/docker-compose.prod.yml logs app
docker-compose -f docker/docker-compose.prod.yml logs nginx
docker-compose -f docker/docker-compose.prod.yml logs db

# Follow logs in real-time
docker-compose -f docker/docker-compose.prod.yml logs -f app
```

Application logs are also stored in `/var/log/kairos` (mapped to container).