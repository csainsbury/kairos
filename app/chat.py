# Conversational Interface for kAIros

from flask import Blueprint, request, jsonify, render_template, current_app
import re

from app.utils import setup_logger
from app.ranking import rank_tasks

# Setup module logger
logger = setup_logger(__name__)

# Create blueprint for chat interface
chat_bp = Blueprint('chat', __name__, url_prefix='/chat')

def parse_time_available(message):
    """Extract available time from user message
    
    Args:
        message: User's chat message
        
    Returns:
        Available time in minutes, or None if not found
    """
    # Look for patterns like "I have 30 minutes" or "20 mins available"
    time_patterns = [
        r'I have (\d+) minutes',
        r'I have (\d+) mins',
        r'(\d+) minutes available',
        r'(\d+) mins available',
        r'available time: (\d+)',
    ]
    
    for pattern in time_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                pass
    
    return None

def parse_task_input(message):
    """Extract task details from user message
    
    Args:
        message: User's chat message
        
    Returns:
        Dictionary with task details, or None if not a task input
    """
    # Placeholder - Will be expanded in Task 3/7
    # This is a very basic implementation
    
    # Check if message starts with 'add task:' or similar
    if not re.match(r'^add\s+task:?\s+', message, re.IGNORECASE):
        return None
    
    # Remove the 'add task:' prefix
    task_text = re.sub(r'^add\s+task:?\s+', '', message, flags=re.IGNORECASE)
    
    # Extract project if specified with @project
    project_match = re.search(r'@(\w+)', task_text)
    project = project_match.group(1) if project_match else None
    
    # Extract duration if specified with [30m]
    duration_match = re.search(r'\[(\d+)m\]', task_text)
    duration = int(duration_match.group(1)) if duration_match else None
    
    # Clean up task description
    description = task_text
    if project_match:
        description = description.replace(project_match.group(0), '').strip()
    if duration_match:
        description = description.replace(duration_match.group(0), '').strip()
    
    return {
        'description': description,
        'project': project,
        'duration': duration
    }

@chat_bp.route('/message', methods=['POST'])
def process_message():
    """API endpoint to process chat messages"""
    data = request.get_json()
    
    if not data or 'message' not in data:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400
    
    user_message = data['message']
    logger.info(f"Processing chat message: {user_message}")
    
    # Check for time-available query
    available_time = parse_time_available(user_message)
    if available_time:
        # Placeholder - Will be implemented in Task 7
        # This would call the ranking engine with the available time
        return jsonify({
            'status': 'success',
            'type': 'suggestions',
            'message': f"Here's what you could do with {available_time} minutes:",
            'suggestions': [
                "First suggested task (placeholder)",
                "Second suggested task (placeholder)"
            ]
        })
    
    # Check for task input
    task_details = parse_task_input(user_message)
    if task_details:
        # Placeholder - Will be implemented in Task 7
        return jsonify({
            'status': 'success',
            'type': 'task_added',
            'message': f"Task added: {task_details['description']}"
        })
    
    # Default response for unrecognized messages
    return jsonify({
        'status': 'success',
        'type': 'info',
        'message': "I can help you manage your tasks. Try asking what you can do with your available time, or add a new task."
    })

@chat_bp.route('/', methods=['GET'])
def chat_interface():
    """Render the chat interface"""
    # Placeholder - Will be implemented in Task 7
    # This would render a template with the chat UI
    return "<h1>kAIros Chat Interface</h1><p>Coming soon in Task 7</p>"