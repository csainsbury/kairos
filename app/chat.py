# Conversational Interface for kAIros

from flask import Blueprint, request, jsonify, render_template, current_app
import re
import json
import requests
from datetime import datetime

from app.utils import setup_logger, retry_with_backoff
from app.models import db, Task, Project, TaskStatus, TaskDomain
from app.ranking import rank_tasks
from app.task_parser import TaskParser

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
        r'what can I do in (\d+) minutes',
        r'what should I do with (\d+) minutes',
    ]
    
    for pattern in time_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                pass
    
    return None

def is_task_input(message):
    """Check if message is a task input
    
    Args:
        message: User's chat message
        
    Returns:
        Boolean indicating if message is likely a task input
    """
    # Check for add task command
    if re.match(r'^add\s+task:?\s+', message, re.IGNORECASE):
        return True
    
    # Check for task input patterns
    task_indicators = [
        r'@\w+',         # Project tag
        r'\[\d+[hm]\]',  # Duration tag
        r'#\w+',         # Domain tag
        r'due:\S+',      # Due date
        r'deadline:\S+', # Alternative due date
        r'by:\S+'        # Alternative due date
    ]
    
    # Count how many indicators are present
    indicator_count = 0
    for pattern in task_indicators:
        if re.search(pattern, message, re.IGNORECASE):
            indicator_count += 1
    
    # If message has 2+ indicators, likely a task
    return indicator_count >= 2

def create_task_from_parsed_data(task_data):
    """Create a task from parsed data
    
    Args:
        task_data: Dictionary with parsed task attributes
        
    Returns:
        (Task, message): Created task and confirmation message
    """
    # Process project association
    project_name = task_data.get('project')
    project = None
    
    if project_name:
        # Look up project by name
        project = Project.query.filter_by(name=project_name).first()
        
        # Create project if not found
        if not project:
            project = Project(
                name=project_name,
                domain=task_data['domain'],
                description=f"Project created from chat: {project_name}"
            )
            db.session.add(project)
            db.session.commit()
            logger.info(f"Created new project: {project_name}")
    
    # Create task
    task = Task(
        description=task_data['description'],
        domain=task_data['domain'],
        project_id=project.id if project else None,
        estimated_duration=task_data['estimated_duration'],
        deadline=task_data.get('deadline'),
        status=TaskStatus.PENDING
    )
    
    db.session.add(task)
    db.session.commit()
    
    logger.info(f"Created task from chat: {task.description}")
    
    # Create confirmation message
    message = f"Task added: {task.description}"
    if project:
        message += f" (Project: {project.name})"
    if task.deadline:
        message += f" (Due: {task.deadline.strftime('%Y-%m-%d')})"
    
    return task, message

def get_task_suggestions(available_time):
    """Get task suggestions for available time
    
    Args:
        available_time: Time available in minutes
        
    Returns:
        List of task suggestion dictionaries
    """
    # Get all pending tasks
    pending_tasks = Task.query.filter_by(status=TaskStatus.PENDING).all()
    
    # Rank tasks based on available time
    ranked_tasks = rank_tasks(pending_tasks, available_time)
    
    # Format task suggestions
    suggestions = []
    for task in ranked_tasks[:5]:  # Top 5 suggestions
        suggestion = {
            'id': task.id,
            'description': task.description,
            'estimated_duration': task.estimated_duration,
            'domain': task.domain.value
        }
        
        if task.project:
            suggestion['project'] = task.project.name
        
        if task.deadline:
            suggestion['deadline'] = task.deadline.strftime('%Y-%m-%d')
        
        suggestions.append(suggestion)
    
    return suggestions

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
        suggestions = get_task_suggestions(available_time)
        
        # Format response based on suggestions
        if suggestions:
            suggestion_texts = []
            for suggestion in suggestions:
                text = f"{suggestion['description']} ({suggestion['estimated_duration']} min)"
                if 'project' in suggestion:
                    text += f" [Project: {suggestion['project']}]"
                suggestion_texts.append(text)
            
            return jsonify({
                'status': 'success',
                'type': 'suggestions',
                'message': f"Here's what you could do with {available_time} minutes:",
                'suggestions': suggestion_texts
            })
        else:
            return jsonify({
                'status': 'success',
                'type': 'info',
                'message': f"I couldn't find any tasks that fit in {available_time} minutes."
            })
    
    # Check for task input
    if is_task_input(user_message):
        # Parse the task
        parser = TaskParser()
        task_data = parser.parse_task(user_message)
        
        if not task_data:
            return jsonify({
                'status': 'error',
                'message': "I couldn't understand your task. Please try again."
            }), 400
        
        # Validate the parsed task
        missing_fields = parser.validate_task(task_data)
        
        # If missing required fields, prompt for them
        if missing_fields:
            return jsonify({
                'status': 'incomplete',
                'message': "I need more information to add this task.",
                'missing_fields': missing_fields,
                'parsed_data': {
                    'description': task_data.get('description', ''),
                    'domain': task_data['domain'].value if 'domain' in task_data else None,
                    'project': task_data.get('project'),
                    'estimated_duration': task_data.get('estimated_duration'),
                    'deadline': task_data.get('deadline').isoformat() if task_data.get('deadline') else None
                }
            })
        
        # Create the task
        task, message = create_task_from_parsed_data(task_data)
        
        return jsonify({
            'status': 'success',
            'type': 'task_added',
            'message': message,
            'task_id': task.id
        })
    
    # Default response for unrecognized messages
    return jsonify({
        'status': 'success',
        'type': 'info',
        'message': "I can help you manage your tasks. Try adding a task with tags like #domain @project [duration] or ask what you can do with your available time."
    })

@chat_bp.route('/complete-task/<int:task_id>', methods=['POST'])
def complete_task(task_id):
    """API endpoint to mark a task as completed"""
    task = Task.query.get_or_404(task_id)
    
    # Mark task as completed
    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': f"Task marked as completed: {task.description}"
    })

@chat_bp.route('/task-details/<int:task_id>', methods=['GET'])
def task_details(task_id):
    """API endpoint to get detailed task information"""
    task = Task.query.get_or_404(task_id)
    
    # Format task details
    details = {
        'id': task.id,
        'description': task.description,
        'domain': task.domain.value,
        'estimated_duration': task.estimated_duration,
        'status': task.status.value
    }
    
    if task.project:
        details['project'] = {
            'id': task.project.id,
            'name': task.project.name
        }
    
    if task.deadline:
        details['deadline'] = task.deadline.isoformat()
    
    return jsonify(details)

@chat_bp.route('/', methods=['GET'])
def chat_interface():
    """Render the chat interface"""
    # This is a placeholder. A proper chat UI will be implemented in Task 7.
    return render_template('chat.html', title='kAIros Chat Interface')