# kAIros - Domain-Aware Task Management System
# Initial app configuration

from flask import Flask
import os

def create_app(config_name='development'):
    app = Flask(__name__)
    
    # Import configuration based on environment
    if config_name == 'development':
        app.config.from_object('config.DevelopmentConfig')
    elif config_name == 'production':
        app.config.from_object('config.ProductionConfig')
    elif config_name == 'testing':
        app.config.from_object('config.TestingConfig')
    else:
        app.config.from_object('config.DevelopmentConfig')
    
    # Setup database
    from app.models import db
    db.init_app(app)
    
    # Create upload directory if doesn't exist
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    
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
    
    # Register error handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return {"error": "Resource not found"}, 404
    
    @app.errorhandler(500)
    def internal_server_error(e):
        return {"error": "Internal server error"}, 500
    
    return app