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
    
    # Security settings for production
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False