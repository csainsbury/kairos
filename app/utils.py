# Utility functions for kAIros

import logging
import logging.handlers
import os
import json
import traceback
import sys
from functools import wraps
import time
import hmac
import hashlib
import base64
import secrets
import random
from datetime import datetime, timedelta
from flask import request, has_request_context, current_app, session
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

# Custom JSON formatter for structured logging
class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging in production"""
    def format(self, record):
        log_record = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'module': record.name,
            'message': record.getMessage(),
        }
        
        # Add exception info if available
        if record.exc_info:
            log_record['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # Add request info if available
        if has_request_context():
            log_record['request'] = {
                'method': request.method,
                'path': request.path,
                'remote_addr': request.remote_addr,
            }
            
        return json.dumps(log_record)

# Configure logging based on environment
def setup_logger(name):
    """Setup a logger with environment-specific configuration
    
    Args:
        name: The name of the logger, typically __name__ of the calling module
        
    Returns:
        A configured logger instance with appropriate handlers and formatters
    """
    logger = logging.getLogger(name)
    
    # Clear any existing handlers to avoid duplication
    if logger.handlers:
        return logger
        
    if os.environ.get('FLASK_ENV') == 'production':
        # Production logging - structured JSON format
        logger.setLevel(logging.WARNING)
        
        # File handler with rotation
        log_dir = os.environ.get('LOG_DIR', 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        # Main log file with rotation (10MB files, keep 30 days of logs)
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, 'kairos.log'),
            maxBytes=10_000_000,  # 10MB
            backupCount=30
        )
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)
        
        # Error-specific log for critical issues
        error_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, 'errors.log'),
            maxBytes=10_000_000,  # 10MB
            backupCount=30
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(JSONFormatter())
        logger.addHandler(error_handler)
        
        # Also add console output for container logs
        console = logging.StreamHandler()
        console.setFormatter(JSONFormatter())
        logger.addHandler(console)
    else:
        # Development logging - more verbose, human-readable format
        logger.setLevel(logging.DEBUG)
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(console)
    
    return logger

# Standardized log method for capturing context
def log_with_context(logger, level, message, context=None, exc_info=None):
    """Log a message with additional context information
    
    Args:
        logger: The logger instance to use
        level: The log level (e.g., 'debug', 'info', 'warning', 'error', 'critical')
        message: The log message
        context: Dictionary of additional context data to include
        exc_info: Exception info to include, typically from sys.exc_info()
    """
    if not context:
        context = {}
        
    if has_request_context():
        context.update({
            'request_id': getattr(request, 'id', None),
            'endpoint': request.endpoint,
            'method': request.method,
            'path': request.path,
            'remote_addr': request.remote_addr,
            'user_agent': request.user_agent.string
        })
    
    # Format message with context for readability in development
    if os.environ.get('FLASK_ENV') != 'production' and context:
        context_str = ', '.join(f"{k}={v}" for k, v in context.items())
        message = f"{message} [{context_str}]"
    
    # Get the logging method and call it
    log_method = getattr(logger, level.lower())
    log_method(message, exc_info=exc_info)

# Retry mechanism with exponential backoff
def retry_with_backoff(max_retries=3, backoff_factor=1.5, retry_on=Exception, log_level='warning'):
    """Decorator for retrying functions with exponential backoff
    
    Args:
        max_retries: Maximum number of retry attempts before giving up
        backoff_factor: Factor to increase wait time between retries
        retry_on: Exception type or tuple of types to retry on
        log_level: Logging level to use for retry messages
    
    Returns:
        Decorator function that wraps the target function with retry logic
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = setup_logger(func.__module__)
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except retry_on as e:
                    retries += 1
                    if retries >= max_retries:
                        logger.error(
                            f"All {max_retries} retries failed for {func.__name__}", 
                            exc_info=sys.exc_info()
                        )
                        raise
                        
                    wait_time = backoff_factor * (2 ** retries)
                    context = {
                        'function': func.__name__,
                        'retry_count': retries,
                        'max_retries': max_retries,
                        'wait_time': f"{wait_time:.2f}s",
                        'exception': str(e)
                    }
                    
                    log_with_context(
                        logger, 
                        log_level,
                        f"Retry {retries}/{max_retries} for {func.__name__} in {wait_time:.2f}s",
                        context=context,
                        exc_info=sys.exc_info()
                    )
                    time.sleep(wait_time)
            
            # We should never reach here, but just in case
            return func(*args, **kwargs)
        return wrapper
    return decorator

# Exception handler for consistent error responses
def handle_exception(func):
    """Decorator to handle exceptions and provide consistent API responses"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger = setup_logger(func.__module__)
            logger.error(f"Exception in {func.__name__}: {str(e)}", exc_info=sys.exc_info())
            
            # Determine if this is a user error or system error
            if isinstance(e, (ValueError, TypeError, KeyError)):
                # User input error - client's fault
                status_code = 400
                error_type = "validation_error"
            else:
                # System error - our fault
                status_code = 500
                error_type = "system_error"
                
            # Only show detailed errors in development
            if os.environ.get('FLASK_ENV') == 'production':
                error_detail = "See server logs for details" 
            else:
                error_detail = str(e)
                
            return {
                "status": "error",
                "error": {
                    "type": error_type,
                    "message": error_detail
                }
            }, status_code
    return wrapper

# CSRF token functions
def generate_csrf_token():
    """Generate a secure CSRF token
    
    Returns:
        CSRF token string
    """
    if 'csrf_token' not in session:
        # Generate random token
        token = secrets.token_hex(32)
        session['csrf_token'] = token
    else:
        token = session['csrf_token']
        
    return token

def validate_csrf_token(token):
    """Validate a CSRF token against session
    
    Args:
        token: Token from form submission
        
    Returns:
        Boolean indicating if token is valid
    """
    expected_token = session.get('csrf_token')
    if not expected_token:
        return False
        
    # Compare tokens with constant-time comparison to prevent timing attacks
    return hmac.compare_digest(token, expected_token)

def csrf_protection(func):
    """Decorator to protect routes against CSRF attacks
    
    Args:
        func: View function to protect
        
    Returns:
        Wrapped function with CSRF protection
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Only protect state-changing methods
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            # Get token from various locations
            token = None
            if request.json:
                token = request.json.get('csrf_token')
            elif request.form:
                token = request.form.get('csrf_token')
            elif request.headers.get('X-CSRF-TOKEN'):
                token = request.headers.get('X-CSRF-TOKEN')
                
            if not token or not validate_csrf_token(token):
                logger = setup_logger('kAIros.security')
                logger.warning(f'CSRF validation failed for {request.path}')
                
                return {
                    "status": "error",
                    "error": {
                        "type": "security_error",
                        "message": "CSRF validation failed"
                    }
                }, 403
                
        return func(*args, **kwargs)
    return wrapper

# Secure Data Sanitization
def sanitize_input(input_string):
    """Sanitize user input to prevent injection attacks
    
    Args:
        input_string: String to sanitize
        
    Returns:
        Sanitized string
    """
    if not input_string:
        return input_string
        
    # Remove potentially dangerous characters
    sanitized = input_string
    # Replace HTML tags
    sanitized = sanitized.replace('<', '&lt;').replace('>', '&gt;')
    # Replace SQL injection patterns
    sanitized = sanitized.replace("'", "''")
    sanitized = sanitized.replace(";", "")
    
    return sanitized

# Secrets Management
class SecretsManager:
    """Manager for secure encryption, storage and rotation of API keys and secrets"""
    
    def __init__(self, app=None):
        self.app = app
        self.encryption_key = None
        self.fernet = None
        
        if app is not None:
            self.init_app(app)
            
    def init_app(self, app):
        """Initialize with Flask app instance
        
        Args:
            app: Flask application instance
        """
        self.app = app
        
        # Check if cryptography is available
        if not CRYPTOGRAPHY_AVAILABLE:
            app.logger.warning("Cryptography package not available. Secure secrets storage disabled.")
            return
            
        # Set up encryption key
        secret_key = app.config.get('SECRET_KEY')
        if not secret_key:
            app.logger.error("SECRET_KEY must be configured for secrets encryption")
            return
            
        try:
            # Generate encryption key from application secret
            salt = b'kAIros_secure_salt_v1'  # Should be stored securely in production
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(secret_key.encode()))
            self.fernet = Fernet(key)
            
            # Create rotation directories if needed
            self._setup_secrets_directory()
            
            app.logger.info("SecretsManager initialized successfully")
        except Exception as e:
            app.logger.error(f"Failed to initialize SecretsManager: {e}")
    
    def _setup_secrets_directory(self):
        """Create and secure secrets directory structure"""
        env = os.environ.get('FLASK_ENV', 'development')
        secrets_dir = os.path.join(self.app.config.get('LOG_DIR', 'logs'), 'secrets')
        
        try:
            if not os.path.exists(secrets_dir):
                os.makedirs(secrets_dir, exist_ok=True)
                
            # Set secure permissions in production
            if env == 'production':
                os.chmod(secrets_dir, 0o700)  # Only owner can read/write/execute
                
            # Create required subdirectories
            active_dir = os.path.join(secrets_dir, 'active')
            if not os.path.exists(active_dir):
                os.makedirs(active_dir, exist_ok=True)
                if env == 'production':
                    os.chmod(active_dir, 0o700)
                    
            rotated_dir = os.path.join(secrets_dir, 'rotated')
            if not os.path.exists(rotated_dir):
                os.makedirs(rotated_dir, exist_ok=True)
                if env == 'production':
                    os.chmod(rotated_dir, 0o700)
        except Exception as e:
            self.app.logger.error(f"Failed to setup secrets directory: {e}")
    
    def encrypt(self, plaintext):
        """Encrypt a sensitive value
        
        Args:
            plaintext: String value to encrypt
            
        Returns:
            Encrypted string value (base64 encoded)
        """
        if not CRYPTOGRAPHY_AVAILABLE or not self.fernet:
            return plaintext
            
        if not plaintext:
            return None
            
        try:
            encrypted = self.fernet.encrypt(plaintext.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            logger = setup_logger('kAIros.security')
            logger.error(f"Encryption failed: {e}")
            return None
    
    def decrypt(self, encrypted_value):
        """Decrypt a sensitive value
        
        Args:
            encrypted_value: Encrypted string (base64 encoded)
            
        Returns:
            Decrypted string value
        """
        if not CRYPTOGRAPHY_AVAILABLE or not self.fernet:
            return encrypted_value
            
        if not encrypted_value:
            return None
            
        try:
            encrypted = base64.urlsafe_b64decode(encrypted_value.encode())
            decrypted = self.fernet.decrypt(encrypted)
            return decrypted.decode()
        except Exception as e:
            logger = setup_logger('kAIros.security')
            logger.error(f"Decryption failed: {e}")
            return None
    
    def store_secret(self, key, value, expiry_days=90):
        """Store a secret with encryption and expiry
        
        Args:
            key: Key name for the secret
            value: Secret value to store
            expiry_days: Days until rotation is recommended
            
        Returns:
            True if successful
        """
        if not CRYPTOGRAPHY_AVAILABLE or not self.fernet:
            return False
            
        env = os.environ.get('FLASK_ENV', 'development')
        secrets_dir = os.path.join(self.app.config.get('LOG_DIR', 'logs'), 'secrets', 'active')
        
        # Calculate expiry date
        expiry_date = datetime.utcnow() + timedelta(days=expiry_days)
        
        # Create secret object
        secret_obj = {
            'value': self.encrypt(value),
            'created': datetime.utcnow().isoformat(),
            'expiry': expiry_date.isoformat(),
            'rotation_needed': False
        }
        
        # Calculate secure filename based on key
        filename = hashlib.sha256(f"{env}_{key}".encode()).hexdigest()
        filepath = os.path.join(secrets_dir, f"{filename}.json")
        
        try:
            # Write to file
            with open(filepath, 'w') as f:
                json.dump(secret_obj, f)
                
            # Set secure permissions in production
            if env == 'production':
                os.chmod(filepath, 0o600)  # Only owner can read/write
                
            return True
        except Exception as e:
            logger = setup_logger('kAIros.security')
            logger.error(f"Failed to store secret {key}: {e}")
            return False
    
    def get_secret(self, key):
        """Retrieve a secret
        
        Args:
            key: Key name of the secret
            
        Returns:
            Decrypted secret value or None if not found
        """
        if not CRYPTOGRAPHY_AVAILABLE or not self.fernet:
            # Fallback to environment variable
            return os.environ.get(key)
            
        env = os.environ.get('FLASK_ENV', 'development')
        secrets_dir = os.path.join(self.app.config.get('LOG_DIR', 'logs'), 'secrets', 'active')
        
        # Calculate secure filename
        filename = hashlib.sha256(f"{env}_{key}".encode()).hexdigest()
        filepath = os.path.join(secrets_dir, f"{filename}.json")
        
        # Check if file exists
        if not os.path.exists(filepath):
            # Fallback to environment variable
            return os.environ.get(key)
            
        try:
            # Read from file
            with open(filepath, 'r') as f:
                secret_obj = json.load(f)
                
            # Check if rotation needed
            expiry = datetime.fromisoformat(secret_obj.get('expiry'))
            if expiry < datetime.utcnow() and not secret_obj.get('rotation_needed', False):
                logger = setup_logger('kAIros.security')
                logger.warning(f"Secret {key} has expired and should be rotated")
                
                # Update file with rotation flag
                secret_obj['rotation_needed'] = True
                with open(filepath, 'w') as f:
                    json.dump(secret_obj, f)
            
            # Return decrypted value
            return self.decrypt(secret_obj.get('value'))
        except Exception as e:
            logger = setup_logger('kAIros.security')
            logger.error(f"Failed to read secret {key}: {e}")
            # Fallback to environment variable
            return os.environ.get(key)
    
    def rotate_secret(self, key, new_value=None):
        """Rotate a secret with a new value
        
        Args:
            key: Key name of the secret
            new_value: New secret value (if None, reencrypts with new key)
            
        Returns:
            True if successful
        """
        if not CRYPTOGRAPHY_AVAILABLE or not self.fernet:
            return False
            
        env = os.environ.get('FLASK_ENV', 'development')
        active_dir = os.path.join(self.app.config.get('LOG_DIR', 'logs'), 'secrets', 'active')
        rotated_dir = os.path.join(self.app.config.get('LOG_DIR', 'logs'), 'secrets', 'rotated')
        
        # Calculate secure filename
        filename = hashlib.sha256(f"{env}_{key}".encode()).hexdigest()
        active_path = os.path.join(active_dir, f"{filename}.json")
        
        # Check if secret exists
        if not os.path.exists(active_path):
            return False
            
        try:
            # Read existing secret
            with open(active_path, 'r') as f:
                secret_obj = json.load(f)
                
            # Get current value if no new value provided
            if new_value is None:
                current_value = self.decrypt(secret_obj.get('value'))
                if current_value is None:
                    return False
                new_value = current_value
                
            # Create timestamp for rotated filename
            timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
            rotated_path = os.path.join(rotated_dir, f"{filename}_{timestamp}.json")
            
            # Move old secret to rotated directory
            with open(rotated_path, 'w') as f:
                json.dump(secret_obj, f)
                
            # Set secure permissions in production
            if env == 'production':
                os.chmod(rotated_path, 0o600)
                
            # Store new secret
            return self.store_secret(key, new_value)
        except Exception as e:
            logger = setup_logger('kAIros.security')
            logger.error(f"Failed to rotate secret {key}: {e}")
            return False
    
    def list_secrets_needing_rotation(self):
        """List all secrets that need rotation
        
        Returns:
            List of secret keys needing rotation
        """
        if not CRYPTOGRAPHY_AVAILABLE or not self.fernet:
            return []
            
        env = os.environ.get('FLASK_ENV', 'development')
        secrets_dir = os.path.join(self.app.config.get('LOG_DIR', 'logs'), 'secrets', 'active')
        
        if not os.path.exists(secrets_dir):
            return []
            
        rotation_needed = []
        try:
            for filename in os.listdir(secrets_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(secrets_dir, filename)
                    
                    with open(filepath, 'r') as f:
                        secret_obj = json.load(f)
                        
                    # Check expiry
                    expiry = datetime.fromisoformat(secret_obj.get('expiry'))
                    if expiry < datetime.utcnow() or secret_obj.get('rotation_needed', False):
                        rotation_needed.append(filename)
        except Exception as e:
            logger = setup_logger('kAIros.security')
            logger.error(f"Error checking secrets for rotation: {e}")
            
        return rotation_needed
        
# IP rate limiting and security
class RateLimiter:
    """Basic in-memory rate limiter for API endpoints"""
    
    def __init__(self, app=None):
        self.app = app
        self.limits = {}  # IP -> {timestamp: count}
        self.blocked = set()  # Set of blocked IPs
        self.window = 60  # Default 60 second window
        self.max_requests = 60  # Default 60 requests per minute
        self.block_threshold = 5  # Number of violations before blocking
        self.whitelist = set()  # Whitelisted IPs
        
        if app is not None:
            self.init_app(app)
            
    def init_app(self, app):
        """Initialize with Flask app
        
        Args:
            app: Flask app instance
        """
        self.app = app
        
        # Load config values
        self.window = app.config.get('RATE_LIMIT_WINDOW', 60)
        self.max_requests = app.config.get('RATE_LIMIT_MAX_REQUESTS', 60)
        self.block_threshold = app.config.get('RATE_LIMIT_BLOCK_THRESHOLD', 5)
        
        # Load whitelist IPs
        whitelist = app.config.get('IP_WHITELIST', '')
        if whitelist:
            self.whitelist = set(ip.strip() for ip in whitelist.split(','))
            
        # Add local IPs to whitelist
        self.whitelist.add('127.0.0.1')
        self.whitelist.add('::1')
        
        # Clean expired entries periodically
        @app.before_request
        def cleanup():
            self._cleanup_expired()
            
    def _cleanup_expired(self):
        """Remove expired entries from tracking dictionaries"""
        now = time.time()
        cutoff = now - self.window
        
        # Clean expired request counts
        for ip in list(self.limits.keys()):
            self.limits[ip] = {ts: count for ts, count in self.limits[ip].items() if ts > cutoff}
            if not self.limits[ip]:
                del self.limits[ip]
                
    def is_rate_limited(self, ip):
        """Check if an IP is currently rate limited
        
        Args:
            ip: IP address to check
            
        Returns:
            Boolean indicating if rate limited
        """
        # Check whitelist
        if ip in self.whitelist:
            return False
            
        # Check if blocked
        if ip in self.blocked:
            return True
            
        # Get current window
        now = time.time()
        cutoff = now - self.window
        
        # Initialize if IP not seen before
        if ip not in self.limits:
            self.limits[ip] = {now: 1}
            return False
            
        # Count requests in current window
        current_count = sum(count for ts, count in self.limits[ip].items() if ts > cutoff)
        
        # Add current request
        if now in self.limits[ip]:
            self.limits[ip][now] += 1
        else:
            self.limits[ip][now] = 1
            
        # Check if over limit
        if current_count > self.max_requests:
            # Count violations
            violations = self.limits[ip].get('violations', 0) + 1
            self.limits[ip]['violations'] = violations
            
            # Block if too many violations
            if violations >= self.block_threshold:
                self.blocked.add(ip)
                logger = setup_logger('kAIros.security')
                logger.warning(f"IP {ip} blocked due to rate limit violations")
                
            return True
            
        return False
        
    def rate_limit(self, func):
        """Decorator to apply rate limiting to a route
        
        Args:
            func: Function to decorate
            
        Returns:
            Decorated function
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            if has_request_context():
                ip = request.remote_addr
                
                if self.is_rate_limited(ip):
                    logger = setup_logger('kAIros.security')
                    logger.warning(f"Rate limit exceeded for IP {ip} on {request.path}")
                    
                    return {
                        "status": "error",
                        "error": {
                            "type": "rate_limit_exceeded",
                            "message": "Rate limit exceeded, please try again later"
                        }
                    }, 429
                    
            return func(*args, **kwargs)
        return wrapper