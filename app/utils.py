# Utility functions for kAIros

import logging
import os
from functools import wraps
import time

# Configure logging based on environment
def setup_logger(name):
    """Setup a logger with environment-specific configuration"""
    logger = logging.getLogger(name)
    
    if os.environ.get('FLASK_ENV') == 'production':
        # Production logging - more structured
        logger.setLevel(logging.WARNING)
        # Add handlers for production (could be file-based, Sentry, etc.)
    else:
        # Development logging - more verbose
        logger.setLevel(logging.DEBUG)
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(console)
    
    return logger

# Retry mechanism with exponential backoff
def retry_with_backoff(max_retries=3, backoff_factor=1.5):
    """Decorator for retrying functions with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    wait_time = backoff_factor * (2 ** retries)
                    logger = setup_logger(func.__module__)
                    logger.warning(
                        f"Retry {retries+1}/{max_retries} for {func.__name__} "
                        f"in {wait_time:.2f}s after error: {str(e)}"
                    )
                    time.sleep(wait_time)
                    retries += 1
            # If we've exhausted retries, run one more time and let the exception propagate
            return func(*args, **kwargs)
        return wrapper
    return decorator