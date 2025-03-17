# Todoist Integration for kAIros

from flask import Blueprint, request, jsonify, current_app
import json
import hmac
import hashlib

from app.utils import setup_logger
from app.models import db

# Setup module logger
logger = setup_logger(__name__)

# Create blueprint for Todoist integration
todoist_bp = Blueprint('todoist', __name__, url_prefix='/todoist')

@todoist_bp.route('/webhook', methods=['POST'])
def todoist_webhook():
    """Endpoint to receive Todoist webhooks"""
    # ToDo: Implement webhook verification signature
    
    # Parse the webhook payload
    payload = request.get_json()
    
    if not payload:
        logger.error("Received invalid JSON payload")
        return jsonify({'status': 'error', 'message': 'Invalid payload'}), 400
    
    # Extract task details from the payload
    # This will be expanded in Task 3
    try:
        # Placeholder parsing logic
        logger.info(f"Received Todoist webhook: {payload}")
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        logger.error(f"Error processing Todoist webhook: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500