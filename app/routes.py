# Routes for kAIros application

from flask import Blueprint, jsonify, current_app

bp = Blueprint('main', __name__)

@bp.route('/health', methods=['GET'])
def health_check():
    """Simple endpoint to verify the server is running"""
    return jsonify({
        'status': 'healthy',
        'version': '0.1.0',
        'environment': current_app.config.get('ENV', 'development')
    })