# Configuration settings for kAIros

import os
from dotenv import load_dotenv

# Load environment-specific .env file
env = os.environ.get('FLASK_ENV', 'development')
if env == 'production':
    load_dotenv('.env.production')
else:
    load_dotenv('.env.development')

class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # LLM API settings
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_API_URL = os.environ.get('LLM_API_URL')
    
    # File upload settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max file size
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
    ALLOWED_EXTENSIONS = {'txt', 'pdf'}
    
    # Todoist API settings
    TODOIST_API_KEY = os.environ.get('TODOIST_API_KEY')
    TODOIST_CLIENT_ID = os.environ.get('TODOIST_CLIENT_ID')
    TODOIST_CLIENT_SECRET = os.environ.get('TODOIST_CLIENT_SECRET')
    TODOIST_WEBHOOK_URL = os.environ.get('TODOIST_WEBHOOK_URL')
    
    # Google Calendar API settings
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
    GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:5000/calendar/oauth2callback')
    GOOGLE_AUTH_SCOPE = ['https://www.googleapis.com/auth/calendar']
    
    # Email settings for reports
    SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
    SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
    DEFAULT_REPORT_EMAIL = os.environ.get('DEFAULT_REPORT_EMAIL')
    
    # Report scheduling
    DAILY_REPORT_HOUR = int(os.environ.get('DAILY_REPORT_HOUR', 7))  # 7 AM by default
    
    # Logging configuration
    LOG_DIR = os.environ.get('LOG_DIR', os.path.join(os.getcwd(), 'logs'))
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FORMAT = os.environ.get('LOG_FORMAT', 'standard')  # 'standard' or 'json'
    
    # API request retry settings
    DEFAULT_MAX_RETRIES = int(os.environ.get('DEFAULT_MAX_RETRIES', 3))
    DEFAULT_RETRY_BACKOFF = float(os.environ.get('DEFAULT_RETRY_BACKOFF', 1.5))
    DEFAULT_RETRY_TIMEOUT = int(os.environ.get('DEFAULT_RETRY_TIMEOUT', 10))  # seconds

    # Security configuration
    # Admin credentials
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME')
    ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH')
    ADMIN_PASSWORD_SALT = os.environ.get('ADMIN_PASSWORD_SALT')
    
    # Rate limiting
    RATE_LIMIT_WINDOW = int(os.environ.get('RATE_LIMIT_WINDOW', 60))  # seconds
    RATE_LIMIT_MAX_REQUESTS = int(os.environ.get('RATE_LIMIT_MAX_REQUESTS', 60))  # requests per window
    RATE_LIMIT_BLOCK_THRESHOLD = int(os.environ.get('RATE_LIMIT_BLOCK_THRESHOLD', 5))  # violations before block
    
    # IP whitelist (comma-separated list)
    IP_WHITELIST = os.environ.get('IP_WHITELIST', '')
    
    # Session security
    SESSION_TYPE = 'filesystem'
    PERMANENT_SESSION_LIFETIME = int(os.environ.get('SESSION_LIFETIME', 1800))  # 30 minutes in seconds
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # CSRF protection
    WTF_CSRF_ENABLED = True
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY', SECRET_KEY)
    WTF_CSRF_TIME_LIMIT = int(os.environ.get('WTF_CSRF_TIME_LIMIT', 3600))  # 1 hour in seconds
    
    # Content security policy
    CONTENT_SECURITY_POLICY = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self';"

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///kairos_dev.db'
    
    # Development-specific settings
    TESTING = False
    ENV = 'development'

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 
        'postgresql://postgres:postgres@db:5432/kairos'
    )
    
    # Production-specific settings
    TESTING = False
    ENV = 'production'
    
    # Enhanced security settings for production
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'  # Stricter than base config
    
    # Force HTTPS in production
    PREFERRED_URL_SCHEME = 'https'
    
    # Production rate limiting - stricter than base config
    RATE_LIMIT_MAX_REQUESTS = int(os.environ.get('RATE_LIMIT_MAX_REQUESTS', 30))  # 30 requests per minute
    
    # Enable database connection pooling in production
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 3600,  # Recycle connections after 1 hour
        'pool_pre_ping': True  # Check connection validity before use
    }
    
    # IP blocking persistence
    IP_BLOCK_STORAGE = os.path.join(os.environ.get('LOG_DIR', 'logs'), 'ip_blocks.json')
    
    # Set secure headers for responses
    SECURE_HEADERS = {
        'Strict-Transport-Security': 'max-age=63072000; includeSubDomains; preload',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'SAMEORIGIN',
        'X-XSS-Protection': '1; mode=block',
        'Referrer-Policy': 'strict-origin-when-cross-origin'
    }

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False