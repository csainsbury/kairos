#!/bin/bash
# Remote Deployment Script for kAIros - Task 13
# This script automates the deployment of kAIros to a remote production server

set -e

# Display banner
echo "======================================================"
echo "       kAIros Remote Deployment Script (Task 13)"
echo "======================================================"
echo ""

# Check for required parameters
if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <server_ip> [ssh_key_path]"
    echo "  server_ip     - IP address of the target server"
    echo "  ssh_key_path  - Path to SSH key (optional, uses default if not provided)"
    exit 1
fi

SERVER_IP=$1
SSH_KEY=""

if [ "$#" -eq 2 ]; then
    SSH_KEY="-i $2"
fi

SSH_CMD="ssh $SSH_KEY ubuntu@$SERVER_IP"
SCP_CMD="scp $SSH_KEY"

echo "🔍 Validating deployment files..."
# Check for required files
if [ ! -f ".env.production" ]; then
    echo "❌ Error: .env.production file not found."
    echo "Please create this file with your production environment variables."
    exit 1
fi

if [ ! -f "docker/docker-compose.prod.yml" ]; then
    echo "❌ Error: docker/docker-compose.prod.yml file not found."
    exit 1
fi

if [ ! -f "nginx/conf.d/kairos.conf" ]; then
    echo "❌ Error: nginx/conf.d/kairos.conf file not found."
    exit 1
fi

echo "✅ Required files found."
echo ""

echo "🔧 Step 1/6: Preparing server at $SERVER_IP..."
# Initial server setup
$SSH_CMD << 'EOF'
# Update package lists
echo "📦 Updating package lists..."
sudo apt update && sudo apt upgrade -y

# Install required packages
echo "📦 Installing required packages..."
sudo apt install -y \
    docker.io \
    docker-compose \
    git \
    ufw \
    nginx \
    python3-certbot-nginx \
    postgresql-client \
    libpq-dev \
    fail2ban \
    prometheus-node-exporter \
    unzip \
    curl

# Configure firewall
echo "🔒 Configuring firewall..."
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable

# Configure fail2ban
echo "🔒 Setting up fail2ban..."
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
sudo sed -i 's/bantime  = 10m/bantime  = 1h/' /etc/fail2ban/jail.local
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# Configure Docker to start on boot
echo "🐳 Setting up Docker..."
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker ubuntu
EOF

echo "✅ Server preparation completed."
echo ""

echo "📂 Step 2/6: Creating application directories..."
# Create required directories
$SSH_CMD << 'EOF'
mkdir -p ~/kairos
mkdir -p ~/kairos/uploads
mkdir -p ~/kairos/ssl_certs
mkdir -p ~/kairos/backups
mkdir -p ~/kairos/logs
mkdir -p ~/kairos/static/error_pages
EOF

echo "✅ Directories created."
echo ""

echo "📤 Step 3/6: Uploading application files..."
# Transfer application files
$SCP_CMD -r ./* ubuntu@$SERVER_IP:~/kairos/
$SCP_CMD ./.env.production ubuntu@$SERVER_IP:~/kairos/

echo "✅ Files uploaded."
echo ""

echo "🔐 Step 4/6: Setting up SSL certificates..."
# Setup SSL certificates
$SSH_CMD << 'EOF'
cd ~/kairos
source .env.production
DOMAIN=$DOMAIN_NAME

# Use certbot to obtain SSL certificate if domain is valid
if [[ $DOMAIN != "your-domain.com" && $DOMAIN != "" ]]; then
    echo "🔒 Setting up SSL for $DOMAIN..."
    
    # Create temporary nginx config for domain validation
    sudo bash -c "cat > /etc/nginx/sites-available/$DOMAIN << EOL
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;
    
    location ~ /.well-known/acme-challenge {
        root /var/www/certbot;
    }
    
    location / {
        return 200 'Certification in progress';
    }
}
EOL"
    
    # Create certbot webroot
    sudo mkdir -p /var/www/certbot
    
    # Enable the site
    sudo ln -sf /etc/nginx/sites-available/$DOMAIN /etc/nginx/sites-enabled/
    sudo nginx -t && sudo systemctl reload nginx
    
    # Obtain certificate
    sudo certbot certonly --webroot -w /var/www/certbot -d $DOMAIN -d www.$DOMAIN
    
    # Copy certificates to our directory
    sudo cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem ssl_certs/$DOMAIN.pem
    sudo cp /etc/letsencrypt/live/$DOMAIN/privkey.pem ssl_certs/$DOMAIN.key
    
    # Set proper permissions
    sudo chown ubuntu:ubuntu ssl_certs/$DOMAIN.pem ssl_certs/$DOMAIN.key
    
    # Set up auto-renewal
    echo "0 3 * * * sudo certbot renew --quiet --post-hook 'systemctl reload nginx'" | sudo tee -a /etc/crontab
    
    echo "✅ SSL certificates created for $DOMAIN."
else
    echo "⚠️ Using self-signed certificate for testing as no domain was set."
    # Create self-signed certificate for testing
    openssl req -x509 -nodes -newkey rsa:4096 -days 30 \
        -keyout ssl_certs/kairos.key -out ssl_certs/kairos.pem \
        -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost"
    
    # Update environment file to use localhost
    sed -i 's/DOMAIN_NAME=.*/DOMAIN_NAME=localhost/' .env.production
fi
EOF

echo "✅ SSL certificates configured."
echo ""

echo "🐳 Step 5/6: Deploying with Docker..."
# Deploy with Docker Compose
$SSH_CMD << 'EOF'
cd ~/kairos

# Replace environment variables in the nginx config
source .env.production
DOMAIN=${DOMAIN_NAME:-localhost}
sed -i "s/\${DOMAIN_NAME}/$DOMAIN/g" nginx/conf.d/kairos.conf

# Generate admin password if it's still set to default
if grep -q "ADMIN_PASSWORD_HASH=replace_with_generated_hash" .env.production; then
    echo "🔑 Generating secure admin password..."
    python3 scripts/generate_admin_password.py --generate > admin_password.txt
    ADMIN_USERNAME=$(grep "ADMIN_USERNAME=" admin_password.txt | cut -d= -f2)
    ADMIN_PASSWORD_SALT=$(grep "ADMIN_PASSWORD_SALT=" admin_password.txt | cut -d= -f2)
    ADMIN_PASSWORD_HASH=$(grep "ADMIN_PASSWORD_HASH=" admin_password.txt | cut -d= -f2)
    
    # Get the generated password to show it once
    GENERATED_PASSWORD=$(grep "Generated secure password:" admin_password.txt | cut -d: -f2 | tr -d ' ')
    
    # Update the env file
    sed -i "s/ADMIN_PASSWORD_HASH=.*/ADMIN_PASSWORD_HASH=$ADMIN_PASSWORD_HASH/" .env.production
    sed -i "s/ADMIN_PASSWORD_SALT=.*/ADMIN_PASSWORD_SALT=$ADMIN_PASSWORD_SALT/" .env.production
    
    echo "✅ Admin password generated. IMPORTANT: Save this password!"
    echo "   Username: $ADMIN_USERNAME"
    echo "   Password: $GENERATED_PASSWORD"
    echo "   This is the only time this password will be shown."
    
    # Remove the password file
    rm admin_password.txt
fi

# Pull or build images
echo "🐳 Building Docker images..."
docker-compose -f docker/docker-compose.prod.yml build

# Start services
echo "🚀 Starting services..."
docker-compose -f docker/docker-compose.prod.yml up -d

# Wait for database to be ready
echo "⏳ Waiting for database to initialize..."
sleep 15

# Initialize database
echo "🗄️ Initializing database..."
docker-compose -f docker/docker-compose.prod.yml exec app python init_db.py

echo "✅ Docker services started and database initialized."
EOF

echo "✅ Deployment completed."
echo ""

echo "📊 Step 6/6: Setting up monitoring..."
# Configure monitoring
$SSH_CMD << 'EOF'
cd ~/kairos

# Set up Prometheus Node Exporter
sudo systemctl enable prometheus-node-exporter
sudo systemctl start prometheus-node-exporter

# Set up application monitoring
cat > ~/kairos/scripts/monitor.sh << 'EOL'
#!/bin/bash

# Health check monitoring script
LOG_FILE=~/kairos/logs/monitoring.log
mkdir -p $(dirname $LOG_FILE)

# Function to log with timestamp
log() {
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1" >> $LOG_FILE
}

# Check system resources
check_system() {
    log "System Check:"
    log "CPU: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}')% used"
    log "Memory: $(free -m | awk 'NR==2{printf "%.2f%%", $3*100/$2}')"
    log "Disk: $(df -h / | awk 'NR==2{print $5}')"
}

# Check Docker containers
check_containers() {
    log "Container Status:"
    docker ps --format "{{.Names}}: {{.Status}}" | while read line; do
        log "$line"
    done
}

# Check application health
check_app_health() {
    source ~/kairos/.env.production
    DOMAIN=${DOMAIN_NAME:-localhost}
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://$DOMAIN/health 2>/dev/null || echo "Failed")
    log "Health endpoint status: $STATUS"
    
    if [ "$STATUS" != "200" ]; then
        log "ERROR: Health check failed!"
        # Send alert if mail is configured
        if [ -n "$DEFAULT_REPORT_EMAIL" ] && [ -x "$(command -v mail)" ]; then
            echo "Health check failed for kAIros at $(date)" | mail -s "kAIros Health Alert" $DEFAULT_REPORT_EMAIL
        fi
    fi
}

# Run all checks
log "=== Monitoring check started ==="
check_system
check_containers
check_app_health
log "=== Monitoring check completed ==="
log ""
EOL

chmod +x ~/kairos/scripts/monitor.sh

# Create cron job for monitoring
echo "*/5 * * * * ~/kairos/scripts/monitor.sh" > monitor_cron
crontab monitor_cron
rm monitor_cron

# Create enhanced backup scheduler
cat > ~/kairos/scripts/scheduled_backup.sh << 'EOL'
#!/bin/bash
# Enhanced scheduled backup script

set -e

cd ~/kairos
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=./backups
mkdir -p $BACKUP_DIR

echo "Starting scheduled backup at $(date)..."

# Execute backup through docker
docker-compose -f docker/docker-compose.prod.yml exec -T db pg_dump -U $POSTGRES_USER $POSTGRES_DB -F c -f /backups/kairos_$TIMESTAMP.backup

# Verify backup
if [ -f "$BACKUP_DIR/kairos_$TIMESTAMP.backup" ]; then
    echo "✅ Backup created: kairos_$TIMESTAMP.backup"
    
    # Upload to remote if configured
    if [ -n "$BACKUP_REMOTE_PATH" ]; then
        echo "Uploading to remote storage..."
        # Add your remote backup command here (e.g., rclone, aws s3 cp, etc.)
    fi
    
    # Clean up old backups (keep last 30 days)
    find $BACKUP_DIR -name "kairos_*.backup" -type f -mtime +30 -delete
    echo "Cleaned up old backups."
else
    echo "❌ Backup failed!"
    # Send alert
    if [ -n "$DEFAULT_REPORT_EMAIL" ] && [ -x "$(command -v mail)" ]; then
        echo "Database backup failed for kAIros at $(date)" | mail -s "kAIros Backup Failure" $DEFAULT_REPORT_EMAIL
    fi
fi
EOL

chmod +x ~/kairos/scripts/scheduled_backup.sh

# Schedule daily backups
echo "0 2 * * * ~/kairos/scripts/scheduled_backup.sh >> ~/kairos/logs/backup.log 2>&1" >> monitor_cron
crontab monitor_cron
rm monitor_cron

echo "✅ Monitoring and backup systems configured."

# Create comprehensive system status script
cat > ~/kairos/scripts/system_status.sh << 'EOL'
#!/bin/bash
# Comprehensive system status report for kAIros

# Print header
echo "======================================================"
echo "           kAIros System Status Report"
echo "             $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================"

# System information
echo -e "\n📊 SYSTEM INFORMATION:"
echo "------------------------------------------------------"
echo "Hostname: $(hostname)"
echo "Kernel: $(uname -r)"
echo "Uptime: $(uptime -p)"
echo "CPU Load: $(cat /proc/loadavg | cut -d ' ' -f 1,2,3)"
echo "Memory Usage: $(free -h | awk 'NR==2{printf "%s/%s (%.2f%%)\n", $3, $2, $3*100/$2}')"
echo "Disk Usage: $(df -h / | awk 'NR==2{printf "%s/%s (%s)\n", $3, $2, $5}')"

# Docker status
echo -e "\n🐳 DOCKER SERVICES:"
echo "------------------------------------------------------"
cd ~/kairos
docker-compose -f docker/docker-compose.prod.yml ps

# Container health details
echo -e "\n🩺 CONTAINER HEALTH:"
echo "------------------------------------------------------"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Health}}"

# Resource usage by container
echo -e "\n💾 CONTAINER RESOURCE USAGE:"
echo "------------------------------------------------------"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"

# Database size
echo -e "\n📁 DATABASE SIZE:"
echo "------------------------------------------------------"
source .env.production
docker-compose -f docker/docker-compose.prod.yml exec db psql -U $POSTGRES_USER -c "SELECT pg_database_size('$POSTGRES_DB')/1024/1024 as size_mb;"

# Nginx status
echo -e "\n🌐 NGINX STATUS:"
echo "------------------------------------------------------"
if sudo systemctl is-active nginx > /dev/null; then
    echo "NGINX service: RUNNING"
else
    echo "NGINX service: NOT RUNNING"
fi

# SSL certificate expiration
echo -e "\n🔐 SSL CERTIFICATE STATUS:"
echo "------------------------------------------------------"
source .env.production
DOMAIN=${DOMAIN_NAME:-localhost}
if [ -f "/etc/letsencrypt/live/$DOMAIN/cert.pem" ]; then
    echo "Certificate for $DOMAIN:"
    sudo certbot certificates | grep -A2 "$DOMAIN"
    EXPIRY=$(sudo openssl x509 -enddate -noout -in /etc/letsencrypt/live/$DOMAIN/cert.pem | cut -d= -f 2)
    echo "Expires: $EXPIRY"
else
    echo "No Let's Encrypt certificate found for $DOMAIN"
fi

# Recent backups
echo -e "\n💾 RECENT BACKUPS:"
echo "------------------------------------------------------"
ls -lt ~/kairos/backups | head -n 10

# Recent errors from logs
echo -e "\n⚠️ RECENT ERRORS (last 24 hours):"
echo "------------------------------------------------------"
echo "Application errors:"
docker-compose -f docker/docker-compose.prod.yml logs --since 24h app | grep -i "error\|exception\|traceback" | tail -n 20 || echo "No recent errors found"

# Monitoring status
echo -e "\n📈 MONITORING STATUS:"
echo "------------------------------------------------------"
if systemctl is-active prometheus-node-exporter > /dev/null; then
    echo "Prometheus Node Exporter: RUNNING"
else
    echo "Prometheus Node Exporter: NOT RUNNING"
fi

if crontab -l | grep -q "monitor.sh"; then
    echo "Monitoring cron job: CONFIGURED"
else
    echo "Monitoring cron job: NOT CONFIGURED"
fi

echo -e "\n======================================================"
echo "               End of Status Report"
echo "======================================================"
EOL

chmod +x ~/kairos/scripts/system_status.sh

echo "✅ System status script created."

# Create documentation
mkdir -p ~/kairos/docs/task13
cat > ~/kairos/docs/task13/remote_deployment.md << 'EOL'
# kAIros Remote Deployment Documentation

This document provides information about the remote deployment setup for kAIros.

## Server Configuration

The kAIros application is deployed on an Ubuntu server with the following components:

- **Web Server**: NGINX with SSL configuration
- **Application Server**: Python Flask (containerized)
- **Database**: PostgreSQL (containerized)
- **Cache**: Redis (containerized)
- **Monitoring**: Prometheus Node Exporter and custom monitoring scripts

## Directory Structure

- `~/kairos/` - Main application directory
  - `backups/` - Database backups
  - `logs/` - Application and monitoring logs
  - `ssl_certs/` - SSL certificates
  - `uploads/` - User uploaded files
  - `static/` - Static files served by NGINX

## Security Measures

- HTTPS with Let's Encrypt SSL certificates
- Firewall (UFW) configured to allow only ports 22, 80, and 443
- Fail2Ban for brute force protection
- Secure NGINX configuration with security headers
- Rate limiting for API endpoints
- Database credentials stored securely

## Maintenance Procedures

### Regular Updates

To update the application:

```bash
cd ~/kairos
git pull
docker-compose -f docker/docker-compose.prod.yml build
docker-compose -f docker/docker-compose.prod.yml up -d
```

### Backups

Database backups are automatically scheduled daily at 2:00 AM. Manual backups can be created:

```bash
cd ~/kairos
./scripts/scheduled_backup.sh
```

Backups are stored in `~/kairos/backups/` and retained for 30 days.

### Monitoring

System monitoring runs every 5 minutes via cron. To check the monitoring logs:

```bash
tail -f ~/kairos/logs/monitoring.log
```

For a comprehensive system status report:

```bash
~/kairos/scripts/system_status.sh
```

## Troubleshooting

### Restarting Services

To restart all services:

```bash
cd ~/kairos
docker-compose -f docker/docker-compose.prod.yml restart
```

To restart just one service (e.g., the application):

```bash
cd ~/kairos
docker-compose -f docker/docker-compose.prod.yml restart app
```

### Viewing Logs

To view application logs:

```bash
cd ~/kairos
docker-compose -f docker/docker-compose.prod.yml logs app
```

Add `--tail=100` to see only the last 100 lines, or `--follow` to follow the logs in real-time.

### Common Issues

1. **Database connection errors**: Check if the database container is running and if the credentials in `.env.production` are correct.

2. **Web server not reachable**: Verify NGINX is running and check the configuration.

3. **SSL certificate issues**: Check certificate expiration and renewal status with `certbot certificates`.

4. **Out of disk space**: Use `df -h` to check disk usage and `docker system prune` to clean up unused Docker resources.

## Disaster Recovery

In case of server failure, follow these steps:

1. Provision a new server
2. Run the deployment script again
3. Restore from the latest backup:
   ```bash
   cd ~/kairos
   ./scripts/restore_database.sh backups/[latest_backup_file]
   ```

For detailed recovery procedures, see `/docs/disaster_recovery.md`.
EOL

# Mark task as in progress in todo2.md
echo "✅ Documentation created."
EOF

echo "✅ Monitoring setup completed."
echo ""

echo "🚀 Finalizing deployment..."
# Final verification
$SSH_CMD << 'EOF'
cd ~/kairos

# Verify all services are running
echo "🔍 Checking container status:"
docker-compose -f docker/docker-compose.prod.yml ps

# Check application health
source .env.production
DOMAIN=${DOMAIN_NAME:-localhost}
echo "🔍 Checking application health endpoint..."
curl -k https://$DOMAIN/health || echo "Health check failed, please verify manually."

# Run the system status script
echo "🔍 Running system status check..."
./scripts/system_status.sh

# Final message
echo ""
echo "======================================================"
echo "       kAIros deployment verification completed"
echo "======================================================"
EOF

echo ""
echo "======================================================"
echo "       kAIros Remote Deployment Completed"
echo "======================================================"
echo ""
echo "Your kAIros instance is now deployed and accessible at:"
echo "https://$DOMAIN_NAME"
echo ""
echo "For maintenance and monitoring:"
echo "- System status: ~/kairos/scripts/system_status.sh"
echo "- Backup script: ~/kairos/scripts/scheduled_backup.sh"
echo "- Monitoring logs: ~/kairos/logs/monitoring.log"
echo ""
echo "For detailed maintenance procedures, see:"
echo "~/kairos/docs/task13/remote_deployment.md"
echo "======================================================"