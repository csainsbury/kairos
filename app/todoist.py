# Todoist Integration for kAIros

from flask import Blueprint, request, jsonify, current_app
import json
import hmac
import hashlib
import re
from datetime import datetime

from app.utils import setup_logger, retry_with_backoff
from app.models import db, Task, Project, TaskStatus, TaskDomain
from app.task_parser import TaskParser

# Setup module logger
logger = setup_logger(__name__)

# Create blueprint for Todoist integration
todoist_bp = Blueprint('todoist', __name__, url_prefix='/todoist')

def verify_webhook_signature(request_data, signature_header):
    """Verify Todoist webhook signature
    
    Args:
        request_data: Raw request data
        signature_header: X-Todoist-Hmac-SHA256 header value
        
    Returns:
        Boolean indicating if signature is valid
    """
    if not signature_header:
        logger.warning("No signature header provided in webhook request")
        return False
    
    # Get client secret from config
    client_secret = current_app.config.get('TODOIST_CLIENT_SECRET')
    if not client_secret:
        logger.error("TODOIST_CLIENT_SECRET not configured")
        return False
    
    # Compute HMAC signature
    computed_signature = hmac.new(
        client_secret.encode('utf-8'),
        request_data,
        hashlib.sha256
    ).hexdigest()
    
    # Compare signatures
    is_valid = hmac.compare_digest(computed_signature, signature_header)
    if not is_valid:
        logger.warning("Invalid webhook signature")
    
    return is_valid

def extract_estimated_duration(content):
    """Extract estimated duration from task content
    
    Args:
        content: Todoist task content string
        
    Returns:
        Estimated duration in minutes, or None if not found
    """
    # Look for duration patterns like [30m] or [1h30m]
    duration_patterns = [
        (r'\[(\d+)m\]', lambda m: int(m.group(1))),  # minutes
        (r'\[(\d+)h\]', lambda m: int(m.group(1)) * 60),  # hours to minutes
        (r'\[(\d+)h(\d+)m\]', lambda m: int(m.group(1)) * 60 + int(m.group(2)))  # hours and minutes
    ]
    
    for pattern, extractor in duration_patterns:
        match = re.search(pattern, content)
        if match:
            return extractor(match)
    
    # Default duration if not specified
    return 30  # 30 minutes default

def extract_domain(content):
    """Extract domain from task content
    
    Args:
        content: Todoist task content string
        
    Returns:
        TaskDomain enum
    """
    # Look for domain tags like #work or #life_admin
    if re.search(r'#work\b', content, re.IGNORECASE):
        return TaskDomain.WORK
    elif re.search(r'#life_admin\b', content, re.IGNORECASE):
        return TaskDomain.LIFE_ADMIN
    elif re.search(r'#general_life\b', content, re.IGNORECASE):
        return TaskDomain.GENERAL_LIFE
    
    # Default to work domain
    return TaskDomain.WORK

def get_or_create_project(project_name, domain):
    """Get existing project or create a new one
    
    Args:
        project_name: Name of the project
        domain: TaskDomain for the project
        
    Returns:
        Project object
    """
    project = Project.query.filter_by(name=project_name).first()
    
    if not project:
        # Create new project
        project = Project(
            name=project_name,
            domain=domain,
            description=f"Project created from Todoist: {project_name}"
        )
        db.session.add(project)
        db.session.commit()
        logger.info(f"Created new project: {project_name}")
    
    return project

def handle_task_added(item_data):
    """Process a task added event from Todoist
    
    Args:
        item_data: Dictionary containing task data
    
    Returns:
        Task object that was created
    """
    content = item_data.get('content', '')
    external_id = str(item_data.get('id'))
    
    # Check if task already exists
    existing_task = Task.query.filter_by(external_id=external_id).first()
    if existing_task:
        logger.info(f"Task with external ID {external_id} already exists")
        return existing_task
    
    # Extract domain
    domain = extract_domain(content)
    
    # Extract project
    project_id = item_data.get('project_id')
    project_name = f"Todoist-{project_id}"  # Default name using ID
    
    # If we have project details, use actual name
    if 'project' in item_data:
        project_name = item_data['project'].get('name', project_name)
    
    # Get or create project
    project = get_or_create_project(project_name, domain)
    
    # Extract deadline
    due_data = item_data.get('due')
    deadline = None
    if due_data and 'date' in due_data:
        deadline_str = due_data['date']
        try:
            deadline = datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            logger.warning(f"Could not parse deadline: {deadline_str}")
    
    # Extract estimated duration
    estimated_duration = extract_estimated_duration(content)
    
    # Clean up content - remove tags
    description = re.sub(r'#\w+', '', content)  # Remove #tags
    description = re.sub(r'\[\d+[hm]+\d*[hm]*\]', '', description)  # Remove duration tags
    description = description.strip()
    
    # Create task
    task = Task(
        description=description,
        external_id=external_id,
        domain=domain,
        project_id=project.id if project else None,
        estimated_duration=estimated_duration,
        deadline=deadline,
        status=TaskStatus.PENDING
    )
    
    db.session.add(task)
    db.session.commit()
    
    logger.info(f"Created task from Todoist: {description}")
    return task

def handle_task_completed(item_data):
    """Process a task completed event from Todoist
    
    Args:
        item_data: Dictionary containing task data
    
    Returns:
        Task object that was updated, or None if not found
    """
    external_id = str(item_data.get('id'))
    
    # Find task
    task = Task.query.filter_by(external_id=external_id).first()
    if not task:
        logger.warning(f"Task with external ID {external_id} not found")
        return None
    
    # Mark as completed
    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.utcnow()
    
    db.session.commit()
    
    logger.info(f"Marked task as completed: {task.description}")
    return task

def handle_task_updated(item_data):
    """Process a task updated event from Todoist
    
    Args:
        item_data: Dictionary containing task data
    
    Returns:
        Task object that was updated, or None if not found
    """
    external_id = str(item_data.get('id'))
    
    # Find task
    task = Task.query.filter_by(external_id=external_id).first()
    if not task:
        logger.warning(f"Task with external ID {external_id} not found")
        return None
    
    # Update fields
    content = item_data.get('content', '')
    if content:
        # Extract domain
        domain = extract_domain(content)
        task.domain = domain
        
        # Clean up content - remove tags
        description = re.sub(r'#\w+', '', content)  # Remove #tags
        description = re.sub(r'\[\d+[hm]+\d*[hm]*\]', '', description)  # Remove duration tags
        task.description = description.strip()
        
        # Extract estimated duration
        estimated_duration = extract_estimated_duration(content)
        task.estimated_duration = estimated_duration
    
    # Extract deadline
    due_data = item_data.get('due')
    if due_data and 'date' in due_data:
        deadline_str = due_data['date']
        try:
            task.deadline = datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            logger.warning(f"Could not parse deadline: {deadline_str}")
    
    db.session.commit()
    
    logger.info(f"Updated task from Todoist: {task.description}")
    return task

def handle_task_deleted(item_data):
    """Process a task deleted event from Todoist
    
    Args:
        item_data: Dictionary containing task data
    
    Returns:
        True if deletion successful, False otherwise
    """
    external_id = str(item_data.get('id'))
    
    # Find task
    task = Task.query.filter_by(external_id=external_id).first()
    if not task:
        logger.warning(f"Task with external ID {external_id} not found")
        return False
    
    # Delete task
    db.session.delete(task)
    db.session.commit()
    
    logger.info(f"Deleted task from Todoist: {task.description}")
    return True

@retry_with_backoff(max_retries=3)
def process_webhook_event(event_data):
    """Process a webhook event from Todoist
    
    Args:
        event_data: Dictionary containing event data
    
    Returns:
        Result of event handling
    """
    event_name = event_data.get('event_name')
    
    if not event_name:
        logger.error("No event_name in webhook payload")
        return None
    
    # Get the item data
    item_data = event_data.get('event_data', {})
    
    # Process different event types
    if event_name == 'item:added':
        return handle_task_added(item_data)
    elif event_name == 'item:completed':
        return handle_task_completed(item_data)
    elif event_name == 'item:updated':
        return handle_task_updated(item_data)
    elif event_name == 'item:deleted':
        return handle_task_deleted(item_data)
    else:
        logger.info(f"Ignoring unsupported event type: {event_name}")
        return None

@todoist_bp.route('/webhook', methods=['POST'])
def todoist_webhook():
    """Endpoint to receive Todoist webhooks"""
    # Get raw request data for signature verification
    request_data = request.get_data()
    
    # Verify signature if in production
    if current_app.config.get('ENV') == 'production':
        signature = request.headers.get('X-Todoist-Hmac-SHA256')
        if not verify_webhook_signature(request_data, signature):
            return jsonify({
                'status': 'error',
                'message': 'Invalid signature'
            }), 401
    
    # Parse the webhook payload
    payload = request.get_json()
    
    if not payload:
        logger.error("Received invalid JSON payload")
        return jsonify({'status': 'error', 'message': 'Invalid payload'}), 400
    
    # Process the webhook
    try:
        result = process_webhook_event(payload)
        
        return jsonify({
            'status': 'success',
            'message': 'Webhook processed successfully'
        }), 200
    except Exception as e:
        logger.error(f"Error processing Todoist webhook: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@todoist_bp.route('/parse', methods=['POST'])
def parse_task():
    """Endpoint for manual task parsing"""
    data = request.get_json()
    
    if not data or 'text' not in data:
        return jsonify({'status': 'error', 'message': 'Missing task text'}), 400
    
    task_text = data['text']
    
    # Parse the task text
    parser = TaskParser()
    task_data = parser.parse_task(task_text)
    
    if not task_data:
        return jsonify({'status': 'error', 'message': 'Could not parse task'}), 400
    
    # Validate the parsed task
    missing_fields = parser.validate_task(task_data)
    
    # If missing required fields, prompt for them
    if missing_fields:
        return jsonify({
            'status': 'incomplete',
            'message': 'Missing required fields',
            'missing_fields': missing_fields,
            'parsed_data': task_data
        }), 200
    
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
                description=f"Project created from task input: {project_name}"
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
    
    logger.info(f"Created task from direct input: {task.description}")
    
    return jsonify({
        'status': 'success',
        'message': 'Task created successfully',
        'task_id': task.id
    }), 201