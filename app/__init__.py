# kAIros - Domain-Aware Task Management System
# Initial app configuration

from flask import Flask, request, g
import os
import atexit
import sys
import uuid
import time
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, time

def create_app(config_name='development'):
    app = Flask(__name__)
    
    # Import configuration based on environment
    if config_name == 'development':
        app.config.from_object('config.DevelopmentConfig')
        os.environ['FLASK_ENV'] = 'development'
    elif config_name == 'production':
        app.config.from_object('config.ProductionConfig')
        os.environ['FLASK_ENV'] = 'production'
    elif config_name == 'testing':
        app.config.from_object('config.TestingConfig')
        os.environ['FLASK_ENV'] = 'testing'
    else:
        app.config.from_object('config.DevelopmentConfig')
        os.environ['FLASK_ENV'] = 'development'
    
    # Setup database
    from app.models import db
    db.init_app(app)
    
    # Create upload directory if doesn't exist
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    
    # Create logs directory if in production and using file logs
    if config_name == 'production':
        log_dir = app.config.get('LOG_DIR', 'logs')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            
    # Initialize security components
    from app.utils import SecretsManager, RateLimiter
    
    # Setup secrets manager for API keys
    secrets_manager = SecretsManager(app)
    app.secrets_manager = secrets_manager
    
    # Setup rate limiter for API endpoints
    rate_limiter = RateLimiter(app)
    app.rate_limiter = rate_limiter
    
    # Request middleware for logging and tracking
    @app.before_request
    def before_request():
        # Generate unique request ID for tracking in logs
        request_id = str(uuid.uuid4())
        request.id = request_id
        g.start_time = time.time()
        
        # Import here to avoid circular imports
        from app.utils import setup_logger
        logger = setup_logger('kAIros.request')
        
        # Log basic request info
        logger.info(
            f"Request started: {request.method} {request.path}",
            extra={
                'request_id': request_id,
                'method': request.method,
                'path': request.path,
                'remote_addr': request.remote_addr,
                'user_agent': getattr(request.user_agent, 'string', '')
            }
        )
    
    @app.after_request
    def after_request(response):
        # Log request completion time
        if hasattr(g, 'start_time'):
            from app.utils import setup_logger, log_with_context
            logger = setup_logger('kAIros.request')
            
            duration = time.time() - g.start_time
            status_code = response.status_code
            
            log_level = 'info'
            if status_code >= 400 and status_code < 500:
                log_level = 'warning'
            elif status_code >= 500:
                log_level = 'error'
                
            log_with_context(
                logger,
                log_level,
                f"Request completed: {request.method} {request.path} ({status_code})",
                context={
                    'request_id': getattr(request, 'id', None),
                    'status_code': status_code,
                    'duration': f"{duration:.3f}s"
                }
            )
        return response
    
    # Register blueprints
    from app.routes import bp as routes_bp
    app.register_blueprint(routes_bp)
    
    from app.todoist import todoist_bp
    app.register_blueprint(todoist_bp)
    
    from app.calendar import calendar_bp
    app.register_blueprint(calendar_bp)
    
    from app.document import document_bp
    app.register_blueprint(document_bp)
    
    from app.chat import chat_bp
    app.register_blueprint(chat_bp)
    
    # Register admin blueprint if not in testing
    if config_name != 'testing':
        from app.admin import admin_bp
        app.register_blueprint(admin_bp)
    
    # Register error handlers
    @app.errorhandler(404)
    def page_not_found(e):
        from app.utils import setup_logger
        logger = setup_logger('kAIros.error')
        logger.warning(
            f"404 Not Found: {request.path}",
            extra={
                'status_code': 404,
                'request_id': getattr(request, 'id', None)
            }
        )
        return {
            "status": "error", 
            "error": {
                "type": "resource_not_found",
                "message": "The requested resource was not found"
            }
        }, 404
    
    @app.errorhandler(500)
    def internal_server_error(e):
        from app.utils import setup_logger
        logger = setup_logger('kAIros.error')
        logger.error(
            f"500 Server Error: {str(e)}",
            extra={
                'status_code': 500,
                'request_id': getattr(request, 'id', None)
            },
            exc_info=True
        )
        
        # Limit error details in production
        if config_name == 'production':
            error_message = "An internal server error occurred"
        else:
            error_message = str(e)
            
        return {
            "status": "error",
            "error": {
                "type": "server_error",
                "message": error_message
            }
        }, 500
    
    # Global exception handler for unhandled exceptions
    @app.errorhandler(Exception)
    def unhandled_exception(e):
        from app.utils import setup_logger
        logger = setup_logger('kAIros.error')
        logger.critical(
            f"Unhandled Exception: {str(e)}",
            extra={
                'request_id': getattr(request, 'id', None),
                'exception_type': e.__class__.__name__
            },
            exc_info=True
        )
        
        # Limit error details in production
        if config_name == 'production':
            error_message = "An unexpected error occurred"
        else:
            error_message = str(e)
            
        return {
            "status": "error",
            "error": {
                "type": "unhandled_exception",
                "message": error_message
            }
        }, 500
    
    # Setup report scheduler (only in production)
    if config_name == 'production' and not app.config.get('TESTING'):
        # Initialize scheduler
        scheduler = BackgroundScheduler()
        
        # Import report function
        from app.report import generate_and_send_report
        from app.utils import setup_logger
        
        def scheduled_report_job():
            logger = setup_logger('kAIros.scheduler')
            logger.info("Starting scheduled daily report job")
            
            try:
                with app.app_context():
                    # Use default recipient from config
                    recipient_email = app.config.get('DEFAULT_REPORT_EMAIL')
                    if recipient_email:
                        # Report for previous day
                        yesterday = datetime.now().date().strftime('%Y-%m-%d')
                        generate_and_send_report(date=yesterday, recipient_email=recipient_email)
                        logger.info(f"Daily report sent successfully to {recipient_email}")
                    else:
                        logger.error("No recipient email configured for daily report")
            except Exception as e:
                logger.error(f"Error sending daily report: {str(e)}", exc_info=True)
        
        # Schedule job to run daily at specified hour
        report_hour = app.config.get('DAILY_REPORT_HOUR', 7)
        scheduler.add_job(
            func=scheduled_report_job,
            trigger='cron',
            hour=report_hour,
            minute=0
        )
        
        # Start the scheduler
        scheduler.start()
        logger = setup_logger('kAIros.app')
        logger.info(f"Background scheduler started, daily report scheduled for {report_hour}:00")
        
        # Shut down the scheduler when exiting the app
        atexit.register(lambda: scheduler.shutdown())
    
    return app