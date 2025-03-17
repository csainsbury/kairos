# Admin functionality for kAIros

from functools import wraps
import os
import hmac
import hashlib
import json
import time
from datetime import datetime, timedelta
from flask import (
    Blueprint, current_app, request, jsonify, session, 
    render_template, redirect, url_for
)

from app.utils import (
    setup_logger, log_with_context, generate_csrf_token, 
    validate_csrf_token, csrf_protection, sanitize_input
)
from app.models import db

# Setup logger
logger = setup_logger(__name__)

# Create blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Admin login attempts tracking
login_attempts = {}  # IP address -> (failed_attempts, last_attempt_timestamp)
LOCKOUT_THRESHOLD = 5  # Number of failed attempts before lockout
LOCKOUT_DURATION = 30 * 60  # 30 minutes in seconds

def hash_password(password, salt=None):
    """Hash a password using PBKDF2 with SHA-256
    
    Args:
        password: Plain text password
        salt: Optional salt to use, generates random if None
        
    Returns:
        Tuple of (salt, hashed_password)
    """
    if salt is None:
        salt = os.urandom(32)  # 32 bytes salt
    
    # Use 100,000 iterations of PBKDF2
    key = hashlib.pbkdf2_hmac(
        'sha256',  # Hash algorithm
        password.encode('utf-8'),  # Password as bytes
        salt,  # Salt
        100000,  # Iterations
        dklen=64  # Get a 64 byte key
    )
    
    return salt, key

def verify_password(stored_password, stored_salt, provided_password):
    """Verify a password against stored hash
    
    Args:
        stored_password: Stored password hash
        stored_salt: Stored salt
        provided_password: Password to verify
        
    Returns:
        Boolean indicating if password is correct
    """
    # Hash the provided password with the stored salt
    _, calculated_hash = hash_password(provided_password, stored_salt)
    
    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(calculated_hash, stored_password)

def is_locked_out(ip_address):
    """Check if an IP address is locked out due to failed login attempts
    
    Args:
        ip_address: IP address to check
        
    Returns:
        Tuple of (is_locked_out, remaining_time)
    """
    # Clean up old lockouts
    cleanup_lockouts()
    
    if ip_address not in login_attempts:
        return False, 0
        
    attempts, timestamp = login_attempts[ip_address]
    
    # Check if locked out and lockout period still active
    if attempts >= LOCKOUT_THRESHOLD:
        lockout_end = timestamp + LOCKOUT_DURATION
        now = time.time()
        
        if now < lockout_end:
            remaining = int(lockout_end - now)
            return True, remaining
            
        # Lockout expired, reset attempts
        login_attempts[ip_address] = (0, now)
        
    return False, 0

def cleanup_lockouts():
    """Clean up expired lockout entries"""
    now = time.time()
    cutoff = now - LOCKOUT_DURATION
    
    # Remove entries older than lockout duration
    for ip in list(login_attempts.keys()):
        attempts, timestamp = login_attempts[ip]
        if timestamp < cutoff:
            del login_attempts[ip]

def record_login_attempt(ip_address, success):
    """Record a login attempt
    
    Args:
        ip_address: IP address making the attempt
        success: Whether the attempt was successful
    """
    now = time.time()
    
    if success:
        # Successful login resets attempts
        if ip_address in login_attempts:
            del login_attempts[ip_address]
    else:
        # Failed login increments attempts
        if ip_address in login_attempts:
            attempts, _ = login_attempts[ip_address]
            login_attempts[ip_address] = (attempts + 1, now)
        else:
            login_attempts[ip_address] = (1, now)

def admin_required(func):
    """Decorator to require admin authentication
    
    Args:
        func: Function to protect
        
    Returns:
        Wrapper function with auth check
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get('admin_authenticated'):
            # API endpoint returns 401, HTML pages redirect to login
            if request.headers.get('Accept', '').startswith('application/json'):
                return jsonify({
                    'status': 'error',
                    'error': {
                        'type': 'authentication_required',
                        'message': 'Admin authentication required'
                    }
                }), 401
            else:
                return redirect(url_for('admin.login'))
                
        return func(*args, **kwargs)
    return wrapper

@admin_bp.route('/login', methods=['GET'])
def login():
    """Admin login form page"""
    ip_address = request.remote_addr
    
    # Check for lockout
    locked, remaining = is_locked_out(ip_address)
    if locked:
        minutes = remaining // 60
        seconds = remaining % 60
        lockout_msg = f"Too many failed attempts. Please try again in {minutes}m {seconds}s."
        return render_template('admin/login.html', 
                               error=lockout_msg, 
                               csrf_token=generate_csrf_token(),
                               locked=True)
                               
    return render_template('admin/login.html', 
                           csrf_token=generate_csrf_token())

@admin_bp.route('/login', methods=['POST'])
@csrf_protection
def process_login():
    """Handle admin login form submission"""
    ip_address = request.remote_addr
    
    # Check for lockout
    locked, remaining = is_locked_out(ip_address)
    if locked:
        minutes = remaining // 60
        seconds = remaining % 60
        return jsonify({
            'status': 'error',
            'error': {
                'type': 'account_locked',
                'message': f"Too many failed attempts. Try again in {minutes}m {seconds}s.",
                'remaining': remaining
            }
        }), 429
        
    # Get form data (with sanitization)
    username = sanitize_input(request.form.get('username', ''))
    password = request.form.get('password', '')
    
    # Get admin credentials from configuration
    admin_username = current_app.config.get('ADMIN_USERNAME')
    admin_password_hash = current_app.config.get('ADMIN_PASSWORD_HASH')
    admin_password_salt = current_app.config.get('ADMIN_PASSWORD_SALT')
    
    if not admin_username or not admin_password_hash or not admin_password_salt:
        logger.error("Admin credentials not configured")
        record_login_attempt(ip_address, False)
        return jsonify({
            'status': 'error',
            'error': {
                'type': 'configuration_error',
                'message': 'Admin authentication not configured'
            }
        }), 500
        
    # In production, convert stored salt from hex to bytes
    if isinstance(admin_password_salt, str):
        try:
            admin_password_salt = bytes.fromhex(admin_password_salt)
        except ValueError:
            logger.error("Invalid admin password salt format")
            return jsonify({
                'status': 'error',
                'error': {
                    'type': 'configuration_error',
                    'message': 'Invalid admin configuration'
                }
            }), 500
            
    # Same for password hash
    if isinstance(admin_password_hash, str):
        try:
            admin_password_hash = bytes.fromhex(admin_password_hash)
        except ValueError:
            logger.error("Invalid admin password hash format")
            return jsonify({
                'status': 'error',
                'error': {
                    'type': 'configuration_error',
                    'message': 'Invalid admin configuration'
                }
            }), 500
    
    # Verify username and password
    if username != admin_username or not verify_password(
            admin_password_hash, admin_password_salt, password):
        logger.warning(f"Failed admin login attempt for username: {username}")
        record_login_attempt(ip_address, False)
        
        return jsonify({
            'status': 'error',
            'error': {
                'type': 'authentication_failed',
                'message': 'Invalid username or password'
            }
        }), 401
        
    # Success - set session variables
    session['admin_authenticated'] = True
    session['admin_username'] = username
    session['admin_last_activity'] = datetime.utcnow().isoformat()
    
    # Record successful login
    record_login_attempt(ip_address, True)
    logger.info(f"Admin login successful: {username}")
    
    return jsonify({
        'status': 'success',
        'message': 'Authentication successful',
        'redirect': url_for('admin.dashboard')
    })

@admin_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    """Log out admin user"""
    # Clear admin session data
    session.pop('admin_authenticated', None)
    session.pop('admin_username', None)
    session.pop('admin_last_activity', None)
    
    if request.method == 'POST':
        return jsonify({
            'status': 'success',
            'message': 'Logged out successfully',
            'redirect': url_for('admin.login')
        })
    else:
        return redirect(url_for('admin.login'))

@admin_bp.route('/dashboard', methods=['GET'])
@admin_required
def dashboard():
    """Admin dashboard page"""
    return render_template('admin/dashboard.html', 
                          username=session.get('admin_username'),
                          csrf_token=generate_csrf_token())

@admin_bp.route('/api-keys', methods=['GET'])
@admin_required
def api_keys():
    """View and manage API keys"""
    # Get list of API keys needing rotation
    secrets_manager = getattr(current_app, 'secrets_manager', None)
    keys_needing_rotation = []
    
    if secrets_manager:
        keys_needing_rotation = secrets_manager.list_secrets_needing_rotation()
        
    return render_template('admin/api_keys.html',
                          keys_needing_rotation=keys_needing_rotation,
                          csrf_token=generate_csrf_token())

@admin_bp.route('/api-keys/rotate', methods=['POST'])
@admin_required
@csrf_protection
def rotate_api_key():
    """Rotate an API key"""
    key_name = request.form.get('key_name')
    new_value = request.form.get('new_value')
    
    if not key_name:
        return jsonify({
            'status': 'error',
            'error': {
                'type': 'validation_error',
                'message': 'Key name is required'
            }
        }), 400
        
    # Get secrets manager
    secrets_manager = getattr(current_app, 'secrets_manager', None)
    if not secrets_manager:
        return jsonify({
            'status': 'error',
            'error': {
                'type': 'configuration_error',
                'message': 'Secrets manager not configured'
            }
        }), 500
        
    # Rotate key
    success = secrets_manager.rotate_secret(key_name, new_value)
    
    if success:
        logger.info(f"API key rotated: {key_name}")
        return jsonify({
            'status': 'success',
            'message': f'API key {key_name} rotated successfully'
        })
    else:
        logger.error(f"Failed to rotate API key: {key_name}")
        return jsonify({
            'status': 'error',
            'error': {
                'type': 'rotation_failed',
                'message': 'Failed to rotate API key'
            }
        }), 500

@admin_bp.route('/security-log', methods=['GET'])
@admin_required
def security_log():
    """View security logs"""
    # Read security log file if it exists
    log_path = os.path.join(current_app.config.get('LOG_DIR', 'logs'), 'security.log')
    log_entries = []
    
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r') as f:
                # Get last 100 lines
                lines = f.readlines()[-100:]
                
                # Parse JSON lines
                for line in lines:
                    try:
                        log_entries.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        # If not JSON, just use raw text
                        log_entries.append({'message': line.strip()})
        except Exception as e:
            logger.error(f"Error reading security log: {e}")
            
    return render_template('admin/security_log.html',
                          log_entries=log_entries,
                          csrf_token=generate_csrf_token())

@admin_bp.route('/ip-blocks', methods=['GET'])
@admin_required
def ip_blocks():
    """View and manage IP blocks"""
    # Get rate limiter
    rate_limiter = getattr(current_app, 'rate_limiter', None)
    blocked_ips = []
    
    if rate_limiter:
        blocked_ips = list(rate_limiter.blocked)
        
    return render_template('admin/ip_blocks.html',
                          blocked_ips=blocked_ips,
                          whitelist=list(rate_limiter.whitelist) if rate_limiter else [],
                          csrf_token=generate_csrf_token())

@admin_bp.route('/ip-blocks/unblock', methods=['POST'])
@admin_required
@csrf_protection
def unblock_ip():
    """Unblock an IP address"""
    ip_address = request.form.get('ip_address')
    
    if not ip_address:
        return jsonify({
            'status': 'error',
            'error': {
                'type': 'validation_error',
                'message': 'IP address is required'
            }
        }), 400
        
    # Get rate limiter
    rate_limiter = getattr(current_app, 'rate_limiter', None)
    if not rate_limiter:
        return jsonify({
            'status': 'error',
            'error': {
                'type': 'configuration_error',
                'message': 'Rate limiter not configured'
            }
        }), 500
        
    # Unblock IP
    if ip_address in rate_limiter.blocked:
        rate_limiter.blocked.remove(ip_address)
        logger.info(f"IP unblocked: {ip_address}")
        
        return jsonify({
            'status': 'success',
            'message': f'IP {ip_address} unblocked successfully'
        })
    else:
        return jsonify({
            'status': 'error',
            'error': {
                'type': 'not_blocked',
                'message': 'IP is not currently blocked'
            }
        }), 400

@admin_bp.route('/ip-blocks/whitelist', methods=['POST'])
@admin_required
@csrf_protection
def whitelist_ip():
    """Add an IP to the whitelist"""
    ip_address = request.form.get('ip_address')
    
    if not ip_address:
        return jsonify({
            'status': 'error',
            'error': {
                'type': 'validation_error',
                'message': 'IP address is required'
            }
        }), 400
        
    # Validate IP format
    import ipaddress
    try:
        ipaddress.ip_address(ip_address)
    except ValueError:
        return jsonify({
            'status': 'error',
            'error': {
                'type': 'validation_error',
                'message': 'Invalid IP address format'
            }
        }), 400
        
    # Get rate limiter
    rate_limiter = getattr(current_app, 'rate_limiter', None)
    if not rate_limiter:
        return jsonify({
            'status': 'error',
            'error': {
                'type': 'configuration_error',
                'message': 'Rate limiter not configured'
            }
        }), 500
        
    # Add to whitelist
    rate_limiter.whitelist.add(ip_address)
    
    # Remove from blocked if present
    if ip_address in rate_limiter.blocked:
        rate_limiter.blocked.remove(ip_address)
        
    logger.info(f"IP added to whitelist: {ip_address}")
    
    return jsonify({
        'status': 'success',
        'message': f'IP {ip_address} added to whitelist'
    })

# Middleware to check admin session timeout
@admin_bp.before_request
def check_admin_session_timeout():
    """Check if admin session has timed out"""
    if 'admin_authenticated' in session and session['admin_authenticated']:
        # Get last activity time
        last_activity = session.get('admin_last_activity')
        if last_activity:
            last_activity_time = datetime.fromisoformat(last_activity)
            # Check if session has timed out (30 minutes)
            if datetime.utcnow() - last_activity_time > timedelta(minutes=30):
                # Session expired, log out
                session.pop('admin_authenticated', None)
                session.pop('admin_username', None)
                session.pop('admin_last_activity', None)
                
                if request.headers.get('Accept', '').startswith('application/json'):
                    return jsonify({
                        'status': 'error',
                        'error': {
                            'type': 'session_expired',
                            'message': 'Admin session expired'
                        }
                    }), 401
                else:
                    return redirect(url_for('admin.login'))
            
            # Update last activity time
            session['admin_last_activity'] = datetime.utcnow().isoformat()