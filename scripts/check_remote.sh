#!/bin/bash
# Remote Server Monitoring Script for kAIros
# Part of Task 13: Remote Deployment and Monitoring

set -e

# Display banner
echo "======================================================"
echo "       kAIros Remote Server Monitoring"
echo "======================================================"
echo ""

# Check for required parameters
if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <server_ip> [ssh_key_path]"
    echo "  server_ip     - IP address of the remote server"
    echo "  ssh_key_path  - Path to SSH key (optional, uses default if not provided)"
    exit 1
fi

SERVER_IP=$1
SSH_KEY=""

if [ "$#" -eq 2 ]; then
    SSH_KEY="-i $2"
fi

SSH_CMD="ssh $SSH_KEY ubuntu@$SERVER_IP"

# Function to print section headers
print_header() {
    echo ""
    echo "======================================================"
    echo "  $1"
    echo "======================================================"
}

# Check server connectivity
print_header "SERVER CONNECTIVITY"
ping -c 1 $SERVER_IP >/dev/null && echo "✅ Server is reachable" || echo "❌ Server is unreachable"

# Check SSH connectivity
if $SSH_CMD -o ConnectTimeout=5 "echo '✅ SSH connection successful'" 2>/dev/null; then
    echo "✅ SSH connection established"
else
    echo "❌ SSH connection failed"
    exit 1
fi

# Check system resources
print_header "SYSTEM RESOURCES"
$SSH_CMD << 'EOF'
echo "CPU Usage: $(top -bn1 | grep "Cpu(s)" | awk '{print $2 + $4}')%"
echo "Memory Usage: $(free -m | awk 'NR==2{printf "%.2f%%", $3*100/$2}')"
echo "Disk Usage: $(df -h / | awk 'NR==2{print $5}')"
echo "Load Average: $(cat /proc/loadavg)"
EOF

# Check for system updates
print_header "SYSTEM UPDATES"
$SSH_CMD << 'EOF'
UPDATES=$(apt list --upgradable 2>/dev/null | grep -v "Listing..." | wc -l)
SECURITY_UPDATES=$(apt list --upgradable 2>/dev/null | grep -i security | wc -l)
echo "Pending updates: $UPDATES (including $SECURITY_UPDATES security updates)"
EOF

# Check Docker status
print_header "DOCKER STATUS"
$SSH_CMD << 'EOF'
cd ~/kairos
echo "Container Status:"
docker-compose -f docker/docker-compose.prod.yml ps
echo ""
echo "Container Health:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Health}}"
EOF

# Check service status
print_header "SERVICE STATUS"
$SSH_CMD << 'EOF'
echo "NGINX Service: $(systemctl is-active nginx)"
echo "Docker Service: $(systemctl is-active docker)"
echo "Fail2Ban Service: $(systemctl is-active fail2ban)"
echo "Prometheus Node Exporter: $(systemctl is-active prometheus-node-exporter)"
EOF

# Check SSL certificate status
print_header "SSL CERTIFICATE STATUS"
$SSH_CMD << 'EOF'
cd ~/kairos
source .env.production
DOMAIN=${DOMAIN_NAME:-localhost}
if [ -f "/etc/letsencrypt/live/$DOMAIN/cert.pem" ]; then
    EXPIRY_DATE=$(sudo openssl x509 -enddate -noout -in /etc/letsencrypt/live/$DOMAIN/cert.pem | cut -d= -f 2)
    EXPIRY_EPOCH=$(date -d "$EXPIRY_DATE" +%s)
    CURRENT_EPOCH=$(date +%s)
    DAYS_LEFT=$(( ($EXPIRY_EPOCH - $CURRENT_EPOCH) / 86400 ))
    
    if [ $DAYS_LEFT -lt 7 ]; then
        echo "⚠️ SSL Certificate for $DOMAIN expires in $DAYS_LEFT days!"
    else
        echo "✅ SSL Certificate for $DOMAIN is valid for $DAYS_LEFT more days"
    fi
else
    if [ "$DOMAIN" = "localhost" ]; then
        echo "ℹ️ Using self-signed certificate for localhost"
    else
        echo "⚠️ No SSL certificate found for $DOMAIN"
    fi
fi
EOF

# Check application health
print_header "APPLICATION HEALTH"
$SSH_CMD << 'EOF'
cd ~/kairos
source .env.production
DOMAIN=${DOMAIN_NAME:-localhost}
HEALTH_STATUS=$(curl -s -k -o /dev/null -w "%{http_code}" https://$DOMAIN/health 2>/dev/null || echo "Failed")

if [ "$HEALTH_STATUS" = "200" ]; then
    echo "✅ Application is healthy (status code: 200)"
    echo ""
    echo "Health Check Details:"
    curl -s -k https://$DOMAIN/health | python3 -m json.tool
else
    echo "❌ Application health check failed (status code: $HEALTH_STATUS)"
fi
EOF

# Check recent backups
print_header "BACKUP STATUS"
$SSH_CMD << 'EOF'
cd ~/kairos
if [ -d "backups" ]; then
    BACKUP_COUNT=$(find backups -name "*.backup" | wc -l)
    LAST_BACKUP=$(find backups -name "*.backup" -type f -printf "%T@ %p\n" 2>/dev/null | sort -nr | head -1)
    
    if [ -n "$LAST_BACKUP" ]; then
        LAST_BACKUP_FILE=$(echo $LAST_BACKUP | cut -d' ' -f2)
        LAST_BACKUP_TIME=$(echo $LAST_BACKUP | cut -d' ' -f1 | xargs -I{} date -d @{} '+%Y-%m-%d %H:%M:%S')
        LAST_BACKUP_SIZE=$(du -h "$LAST_BACKUP_FILE" | cut -f1)
        
        echo "Total backups: $BACKUP_COUNT"
        echo "Last backup: $LAST_BACKUP_FILE"
        echo "Backup time: $LAST_BACKUP_TIME"
        echo "Backup size: $LAST_BACKUP_SIZE"
        
        # Check if backup is recent (within 36 hours)
        BACKUP_EPOCH=$(date -d "$LAST_BACKUP_TIME" +%s)
        CURRENT_EPOCH=$(date +%s)
        HOURS_AGO=$(( ($CURRENT_EPOCH - $BACKUP_EPOCH) / 3600 ))
        
        if [ $HOURS_AGO -gt 36 ]; then
            echo "⚠️ Last backup is $HOURS_AGO hours old!"
        else
            echo "✅ Backup is recent ($HOURS_AGO hours ago)"
        fi
    else
        echo "⚠️ No backups found!"
    fi
else
    echo "❌ Backup directory not found"
fi
EOF

# Check recent errors in logs
print_header "RECENT ERRORS"
$SSH_CMD << 'EOF'
cd ~/kairos
echo "Application Errors (last 24 hours):"
docker-compose -f docker/docker-compose.prod.yml logs --since 24h app | grep -i "error\|exception\|critical" | tail -n 10 || echo "No recent application errors found"

echo ""
echo "NGINX Errors (last 24 hours):"
docker-compose -f docker/docker-compose.prod.yml logs --since 24h nginx | grep -i "error" | tail -n 10 || echo "No recent NGINX errors found"

echo ""
echo "Database Errors (last 24 hours):"
docker-compose -f docker/docker-compose.prod.yml logs --since 24h db | grep -i "error\|fatal" | tail -n 10 || echo "No recent database errors found"
EOF

# Check security status
print_header "SECURITY STATUS"
$SSH_CMD << 'EOF'
echo "Fail2Ban Status:"
sudo fail2ban-client status | grep "Jail list:" | sed 's/^.*:\s//'

echo ""
echo "UFW Status:"
sudo ufw status | grep Status

echo ""
echo "Last 5 Failed Login Attempts:"
last -f /var/log/btmp -n 5 2>/dev/null || echo "No failed login attempts found or log not readable"

echo ""
echo "Current Users Logged In:"
who
EOF

# Final summary
print_header "MONITORING SUMMARY"
echo "Remote server monitoring completed for $SERVER_IP"
echo "For a more detailed report, run the system_status.sh script on the server itself:"
echo "  $SSH_CMD '~/kairos/scripts/system_status.sh'"
echo ""
echo "Remote monitoring completed: $(date)"
echo "======================================================"