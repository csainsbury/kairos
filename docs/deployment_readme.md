# kAIros: Step-by-Step Deployment Guide

This guide provides detailed instructions for deploying kAIros to a remote production server.

## Prerequisites

- An Ubuntu server (Ubuntu 20.04 LTS or newer recommended)
- Root access or sudo privileges 
- A domain name pointing to your server (optional but recommended)
- SSH access to the server

## Deployment Steps

### 1. Initial Server Setup

1. **Connect to your server**:
   ```bash
   ssh root@your-server-ip
   ```

2. **Create a non-root user with sudo privileges**:
   ```bash
   adduser ubuntu
   usermod -aG sudo ubuntu
   ```

3. **Set up SSH key authentication for the new user**:
   ```bash
   mkdir -p /home/ubuntu/.ssh
   chmod 700 /home/ubuntu/.ssh
   # Copy your public key to the authorized_keys file
   echo "your-public-key-content" > /home/ubuntu/.ssh/authorized_keys
   chmod 600 /home/ubuntu/.ssh/authorized_keys
   chown -R ubuntu:ubuntu /home/ubuntu/.ssh
   ```

4. **Disable password authentication** (optional but recommended):
   ```bash
   # Edit SSH configuration
   nano /etc/ssh/sshd_config
   ```
   
   Find and change these settings:
   ```
   PasswordAuthentication no
   PubkeyAuthentication yes
   PermitRootLogin no
   ```
   
   Restart SSH service:
   ```bash
   systemctl restart sshd
   ```

5. **Update the system packages**:
   ```bash
   apt update && apt upgrade -y
   ```

### 2. Preparing Your Local Environment

1. **Clone the kAIros repository** (if you haven't already):
   ```bash
   git clone https://github.com/your-username/kAIros.git
   cd kAIros
   ```

2. **Create/update the production environment file**:
   Copy `.env.production.template` to `.env.production` and edit with your settings:
   ```bash
   cp .env.production.template .env.production
   nano .env.production
   ```
   
   At minimum, update these variables:
   - `SECRET_KEY`: Generate a strong random string
   - `LLM_API_KEY`: Your actual API key
   - `DOMAIN_NAME`: Your domain name or server IP
   - `POSTGRES_PASSWORD`: Strong database password
   - `ADMIN_USERNAME` and `ADMIN_PASSWORD_HASH`: Will be set by the deployment script
   - `MAIL_*` settings for email notifications

### 3. Automated Deployment

The automated deployment script handles most of the setup process:

1. **Make the deployment script executable**:
   ```bash
   chmod +x scripts/remote_deploy.sh
   ```

2. **Run the deployment script**:
   ```bash
   ./scripts/remote_deploy.sh your-server-ip [path-to-ssh-key]
   ```
   
   This script will:
   - Install required packages (Docker, NGINX, Certbot, etc.)
   - Configure the firewall and security settings
   - Transfer the application files
   - Set up SSL certificates
   - Build and start Docker containers
   - Initialize the database
   - Configure monitoring and backup scripts

3. **Save the generated admin password** displayed during deployment.

### 4. Manual Post-Deployment Steps

1. **Verify deployment success**:
   ```bash
   ssh ubuntu@your-server-ip
   cd ~/kairos
   ./scripts/system_status.sh
   ```

2. **Test application functionality**:
   - Visit `https://your-domain-name` in a browser
   - Log in with the admin credentials
   - Test core features (task creation, document upload, etc.)

3. **Configure domain DNS settings** (if using a domain):
   - Ensure A records point to your server IP
   - Verify SSL certificate is properly issued

### 5. Setting Up External Integrations

1. **Google Calendar Integration**:
   - Create a Google Cloud project
   - Enable the Google Calendar API
   - Generate OAuth credentials
   - Update the following in `.env.production`:
     ```
     GOOGLE_CLIENT_ID=your-client-id
     GOOGLE_CLIENT_SECRET=your-client-secret
     GOOGLE_REDIRECT_URI=https://your-domain/calendar/oauth2callback
     ```
   - Restart the application:
     ```bash
     cd ~/kairos
     docker-compose -f docker/docker-compose.prod.yml restart app
     ```

2. **Todoist Integration** (if used):
   - Create a Todoist developer app
   - Generate API credentials
   - Update the Todoist settings in `.env.production`
   - Restart the application

### 6. Monitoring and Maintenance

1. **Check the system status**:
   ```bash
   cd ~/kairos
   ./scripts/system_status.sh
   ```

2. **View application logs**:
   ```bash
   cd ~/kairos
   docker-compose -f docker/docker-compose.prod.yml logs app
   ```

3. **Monitor the system remotely** (from your local machine):
   ```bash
   ./scripts/check_remote.sh your-server-ip [path-to-ssh-key]
   ```

4. **Create manual backups**:
   ```bash
   cd ~/kairos
   ./scripts/scheduled_backup.sh
   ```
   
5. **Update the application** when new code is available:
   ```bash
   cd ~/kairos
   ./scripts/update.sh
   ```

### 7. Restoring from Backup

If you need to restore the database from a backup:

1. **List available backups**:
   ```bash
   ls -la ~/kairos/backups
   ```

2. **Restore from a specific backup**:
   ```bash
   cd ~/kairos
   ./scripts/restore_database.sh backups/kairos_20250317_120000.backup
   ```

### 8. Troubleshooting

1. **Containers not starting**:
   ```bash
   cd ~/kairos
   docker-compose -f docker/docker-compose.prod.yml ps
   docker-compose -f docker/docker-compose.prod.yml logs
   ```

2. **NGINX issues**:
   ```bash
   sudo nginx -t
   sudo systemctl status nginx
   ```

3. **SSL certificate problems**:
   ```bash
   sudo certbot certificates
   ```

4. **Database connection errors**:
   ```bash
   cd ~/kairos
   docker-compose -f docker/docker-compose.prod.yml exec db pg_isready -U kairos_prod
   ```

5. **Application not responding**:
   ```bash
   cd ~/kairos
   docker-compose -f docker/docker-compose.prod.yml restart app
   ```

### Security Recommendations

1. **Regular updates**:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

2. **Check for failed login attempts**:
   ```bash
   sudo fail2ban-client status
   ```

3. **Review firewall rules**:
   ```bash
   sudo ufw status
   ```

4. **Rotate API keys periodically**:
   Edit `.env.production` and restart the application.

5. **Check SSL certificate expiration**:
   ```bash
   sudo certbot certificates
   ```

## Conclusion

Your kAIros instance should now be deployed and running. For detailed information on each component, refer to the documentation in the `docs/` directory. If you encounter issues, check the logs and system status for diagnostic information.

For automatic updates, consider setting up a CI/CD pipeline that uses the provided scripts to automate the deployment process whenever new code is pushed to your repository.