# Conversational Interface for kAIros

from flask import Blueprint, request, jsonify, render_template, current_app, session
import re
import json
import requests
from datetime import datetime, timedelta
import uuid

from app.utils import setup_logger, retry_with_backoff
from app.models import db, Task, Project, TaskStatus, TaskDomain, Document
from app.ranking import rank_tasks, recommend_next_task, get_domain_weights, get_ranked_tasks_by_domain
from app.task_parser import TaskParser
from app.calendar import get_calendar_events

# Setup module logger
logger = setup_logger(__name__)

# Create blueprint for chat interface
chat_bp = Blueprint('chat', __name__, url_prefix='/chat')

# Define message types for conversation
MESSAGE_TYPES = {
    'GREETING': 'greeting',
    'TASK_QUERY': 'task_query',
    'TASK_CREATION': 'task_creation',
    'CALENDAR_QUERY': 'calendar_query',
    'TIME_AVAILABLE': 'time_available',
    'GENERAL_QUESTION': 'general_question',
    'TASK_UPDATE': 'task_update',
    'TASK_COMPLETION': 'task_completion',
    'HELP_REQUEST': 'help_request',
    'DOMAIN_QUERY': 'domain_query',
    'PROJECT_QUERY': 'project_query',
    'DOCUMENT_QUERY': 'document_query'
}

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
        r'I have (\d+) hours?',
        r'I have (\d+):(\d+)',  # hour:minute format
        r'(\d+) minutes available',
        r'(\d+) mins available',
        r'(\d+) hours? available',
        r'available time:? (\d+)',
        r'what can I do in (\d+) minutes',
        r'what can I do in (\d+) mins',
        r'what can I do in (\d+) hours?',
        r'what should I do with (\d+) minutes',
        r'what should I do with (\d+) mins',
        r'what should I do with (\d+) hours?'
    ]
    
    for pattern in time_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            try:
                # Handle hour:minute format
                if pattern.endswith(':(\d+)'):
                    hours = int(match.group(1))
                    minutes = int(match.group(2))
                    return hours * 60 + minutes
                # Handle hours format
                elif 'hours' in pattern or 'hour' in pattern:
                    return int(match.group(1)) * 60
                # Handle minutes format
                else:
                    return int(match.group(1))
            except (ValueError, IndexError):
                pass
    
    return None

def parse_date_query(message):
    """Extract date query from user message
    
    Args:
        message: User's chat message
        
    Returns:
        Tuple of (start_date, end_date) as datetime objects, or None if not found
    """
    # Implement date patterns like "today", "tomorrow", "this week", etc.
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Check for common date patterns
    if re.search(r'\btoday\b', message, re.IGNORECASE):
        return (today, today + timedelta(days=1) - timedelta(seconds=1))
    
    if re.search(r'\btomorrow\b', message, re.IGNORECASE):
        tomorrow = today + timedelta(days=1)
        return (tomorrow, tomorrow + timedelta(days=1) - timedelta(seconds=1))
    
    if re.search(r'\bthis week\b', message, re.IGNORECASE):
        # Calculate beginning of week (Monday)
        start_of_week = today - timedelta(days=today.weekday())
        return (start_of_week, start_of_week + timedelta(days=7) - timedelta(seconds=1))
    
    if re.search(r'\bnext week\b', message, re.IGNORECASE):
        # Calculate beginning of next week
        start_of_week = today - timedelta(days=today.weekday()) + timedelta(days=7)
        return (start_of_week, start_of_week + timedelta(days=7) - timedelta(seconds=1))
    
    # For other cases, return None for now
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
        
    if re.match(r'^add\s+', message, re.IGNORECASE) and re.search(r'#\w+|\[\d+[hm]\]|@\w+', message):
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

def is_calendar_query(message):
    """Check if message is a calendar query
    
    Args:
        message: User's chat message
        
    Returns:
        Boolean indicating if message is a calendar query
    """
    calendar_patterns = [
        r'\bcalendar\b',
        r'\bschedule\b',
        r'\bevent(s)?\b',
        r'\bappointment(s)?\b',
        r'\bmeeting(s)?\b',
        r'\bplans? for (today|tomorrow|this week|next week)\b',
        r'\bwhat( is|\'s)? (happening|going on) (today|tomorrow|this week|next week)\b'
    ]
    
    for pattern in calendar_patterns:
        if re.search(pattern, message, re.IGNORECASE):
            return True
    
    return False

def is_domain_query(message):
    """Check if message is querying about a specific domain
    
    Args:
        message: User's chat message
        
    Returns:
        Domain enum if found, None otherwise
    """
    # Check for work domain
    if re.search(r'\bwork tasks?\b', message, re.IGNORECASE) or re.search(r'\btasks? for work\b', message, re.IGNORECASE):
        return TaskDomain.WORK
    
    # Check for life admin domain
    if re.search(r'\blife admin tasks?\b', message, re.IGNORECASE) or re.search(r'\badmin tasks?\b', message, re.IGNORECASE):
        return TaskDomain.LIFE_ADMIN
    
    # Check for general life domain
    if re.search(r'\bgeneral life tasks?\b', message, re.IGNORECASE) or re.search(r'\bpersonal tasks?\b', message, re.IGNORECASE):
        return TaskDomain.GENERAL_LIFE
    
    return None

def is_help_request(message):
    """Check if message is a help request
    
    Args:
        message: User's chat message
        
    Returns:
        Boolean indicating if message is a help request
    """
    help_patterns = [
        r'\bhelp\b',
        r'\bhow (do|to|can) I\b',
        r'\bwhat (can|do) you do\b',
        r'\binstruction(s)?\b',
        r'\bcommand(s)?\b',
        r'\bfeature(s)?\b'
    ]
    
    for pattern in help_patterns:
        if re.search(pattern, message, re.IGNORECASE):
            return True
    
    return False

def is_project_query(message):
    """Check if message is querying about projects
    
    Args:
        message: User's chat message
        
    Returns:
        Project name if found, None otherwise
    """
    # Check for project listing query
    if re.search(r'\blist projects\b', message, re.IGNORECASE) or re.search(r'\ball projects\b', message, re.IGNORECASE):
        return "__LIST_ALL__"
    
    # Check for specific project
    match = re.search(r'\bproject\s+(["\']?)([^"\']+)\1\b', message, re.IGNORECASE) or re.search(r'\btasks?\s+in\s+project\s+(["\']?)([^"\']+)\1\b', message, re.IGNORECASE)
    if match:
        return match.group(2)
    
    # Alternative pattern for project name with @ symbol
    match = re.search(r'@(\w+)', message)
    if match and 'tasks' in message.lower():
        return match.group(1)
    
    return None

def is_document_query(message):
    """Check if message is querying about documents
    
    Args:
        message: User's chat message
        
    Returns:
        Boolean indicating if message is a document query
    """
    document_patterns = [
        r'\bdocument(s)?\b',
        r'\bfile(s)?\b',
        r'\bpdf(s)?\b',
        r'\bupload(s|ed)?\b',
        r'\bsummar(y|ies)\b'
    ]
    
    # Check if message contains document patterns and query words
    has_document_term = any(re.search(pattern, message, re.IGNORECASE) for pattern in document_patterns)
    has_query_term = any(term in message.lower() for term in ['list', 'show', 'about', 'tell', 'what', 'any', 'get', 'find'])
    
    return has_document_term and has_query_term

def is_task_completion(message):
    """Check if message is about completing a task
    
    Args:
        message: User's chat message
        
    Returns:
        Task identifier if found, None otherwise
    """
    # Check for completion patterns
    complete_patterns = [
        r'complete(d)?\s+task\s+["\']?([^"\']+)["\']?',
        r'mark\s+["\']?([^"\']+)["\']?\s+as\s+complete(d)?',
        r'finish(ed)?\s+["\']?([^"\']+)["\']?'
    ]
    
    for pattern in complete_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            task_name = match.group(2) if 'task' in pattern else match.group(1)
            return task_name
    
    # Check for number-based task completion
    match = re.search(r'complete(d)?\s+task\s+#?(\d+)', message, re.IGNORECASE) or re.search(r'mark\s+task\s+#?(\d+)\s+as\s+complete(d)?', message, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1) if 'as' in match.group(0) else match.group(2))
        except (ValueError, IndexError):
            pass
    
    return None

def classify_message(message):
    """Determine the intent of a user message
    
    Args:
        message: User's chat message
        
    Returns:
        Tuple of (message_type, extracted_data)
    """
    # Check for help requests first (high priority)
    if is_help_request(message):
        return (MESSAGE_TYPES['HELP_REQUEST'], None)
    
    # Check for task creation intent
    if is_task_input(message):
        return (MESSAGE_TYPES['TASK_CREATION'], message)
    
    # Check for time available queries
    available_time = parse_time_available(message)
    if available_time is not None:
        return (MESSAGE_TYPES['TIME_AVAILABLE'], available_time)
    
    # Check for calendar queries
    if is_calendar_query(message):
        date_range = parse_date_query(message)
        return (MESSAGE_TYPES['CALENDAR_QUERY'], date_range)
    
    # Check for domain queries
    domain = is_domain_query(message)
    if domain:
        return (MESSAGE_TYPES['DOMAIN_QUERY'], domain)
    
    # Check for project queries
    project = is_project_query(message)
    if project:
        return (MESSAGE_TYPES['PROJECT_QUERY'], project)
    
    # Check for document queries
    if is_document_query(message):
        return (MESSAGE_TYPES['DOCUMENT_QUERY'], None)
    
    # Check for task completion
    task_identifier = is_task_completion(message)
    if task_identifier:
        return (MESSAGE_TYPES['TASK_COMPLETION'], task_identifier)
    
    # Check for task queries (generic queries about tasks)
    if re.search(r'\btasks?\b', message, re.IGNORECASE):
        return (MESSAGE_TYPES['TASK_QUERY'], None)
    
    # Check for greeting
    if re.match(r'^(hi|hello|hey|greetings|good (morning|afternoon|evening))(\s|$)', message, re.IGNORECASE):
        return (MESSAGE_TYPES['GREETING'], None)
    
    # Default to general question
    return (MESSAGE_TYPES['GENERAL_QUESTION'], message)

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

def get_task_suggestions(available_time, domain=None):
    """Get task suggestions for available time
    
    Args:
        available_time: Time available in minutes
        domain: Optional domain to filter by
        
    Returns:
        List of task suggestion dictionaries
    """
    # Get pending tasks
    query = Task.query.filter_by(status=TaskStatus.PENDING)
    
    # Apply domain filter if provided
    if domain:
        query = query.filter_by(domain=domain)
    
    pending_tasks = query.all()
    
    # Rank tasks based on available time
    ranked_tasks = rank_tasks(pending_tasks, available_time)
    
    # Format task suggestions
    suggestions = []
    for i, task in enumerate(ranked_tasks[:5]):  # Top 5 suggestions
        suggestion = {
            'id': task.id,
            'rank': i + 1,
            'description': task.description,
            'estimated_duration': task.estimated_duration,
            'domain': task.domain.value if task.domain else None
        }
        
        if task.project:
            suggestion['project'] = task.project.name
        
        if task.deadline:
            suggestion['deadline'] = task.deadline.strftime('%Y-%m-%d')
        
        suggestions.append(suggestion)
    
    return suggestions

def get_calendar_summary(start_date=None, end_date=None):
    """Get summary of calendar events
    
    Args:
        start_date: Optional start date for range
        end_date: Optional end date for range
        
    Returns:
        Dictionary with calendar summary information
    """
    # Default to today if no dates provided
    if not start_date:
        start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if not end_date:
        end_date = start_date + timedelta(days=1) - timedelta(seconds=1)
    
    try:
        # Get events from calendar
        events = get_calendar_events(start_date, end_date)
        
        # Calculate total event time
        total_minutes = 0
        for event in events:
            try:
                start = datetime.fromisoformat(event['start'].replace('Z', '+00:00'))
                end = datetime.fromisoformat(event['end'].replace('Z', '+00:00'))
                event_minutes = (end - start).total_seconds() / 60
                total_minutes += event_minutes
            except (ValueError, KeyError):
                # Skip events with parsing issues
                continue
        
        # Calculate available time (assuming 16 waking hours per day)
        day_count = (end_date - start_date).days + 1
        total_available = day_count * 16 * 60  # 16 hours per day in minutes
        remaining_minutes = total_available - total_minutes
        
        return {
            'events': events,
            'event_count': len(events),
            'total_minutes': total_minutes,
            'available_minutes': remaining_minutes,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting calendar summary: {str(e)}")
        return {
            'events': [],
            'event_count': 0,
            'total_minutes': 0,
            'available_minutes': 0,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'error': str(e)
        }

def get_domain_summary():
    """Get summary of tasks by domain
    
    Returns:
        Dictionary with domain summary information
    """
    # Get pending tasks by domain
    work_tasks = Task.query.filter_by(domain=TaskDomain.WORK, status=TaskStatus.PENDING).all()
    life_admin_tasks = Task.query.filter_by(domain=TaskDomain.LIFE_ADMIN, status=TaskStatus.PENDING).all()
    general_life_tasks = Task.query.filter_by(domain=TaskDomain.GENERAL_LIFE, status=TaskStatus.PENDING).all()
    
    # Calculate total time by domain
    work_minutes = sum(task.estimated_duration for task in work_tasks)
    life_admin_minutes = sum(task.estimated_duration for task in life_admin_tasks)
    general_life_minutes = sum(task.estimated_duration for task in general_life_tasks)
    
    # Get domain weights for context
    domain_weights = get_domain_weights()
    
    return {
        'work': {
            'count': len(work_tasks),
            'total_minutes': work_minutes,
            'weight': domain_weights.get('work', 1.0)
        },
        'life_admin': {
            'count': len(life_admin_tasks),
            'total_minutes': life_admin_minutes,
            'weight': domain_weights.get('life_admin', 0.8)
        },
        'general_life': {
            'count': len(general_life_tasks),
            'total_minutes': general_life_minutes,
            'weight': domain_weights.get('general_life', 0.6)
        },
        'total_count': len(work_tasks) + len(life_admin_tasks) + len(general_life_tasks),
        'total_minutes': work_minutes + life_admin_minutes + general_life_minutes
    }

def get_project_summary(project_name=None):
    """Get summary of tasks by project
    
    Args:
        project_name: Optional project name to filter by
        
    Returns:
        Dictionary with project summary information
    """
    if project_name == "__LIST_ALL__":
        # Get all projects with task counts
        projects = Project.query.all()
        project_summaries = []
        
        for project in projects:
            pending_count = Task.query.filter_by(project_id=project.id, status=TaskStatus.PENDING).count()
            completed_count = Task.query.filter_by(project_id=project.id, status=TaskStatus.COMPLETED).count()
            total_count = pending_count + completed_count
            
            if total_count > 0:  # Only include projects with tasks
                project_summaries.append({
                    'id': project.id,
                    'name': project.name,
                    'domain': project.domain.value if project.domain else None,
                    'pending_count': pending_count,
                    'completed_count': completed_count,
                    'total_count': total_count,
                    'completion_rate': completed_count / total_count if total_count > 0 else 0
                })
        
        return {
            'projects': project_summaries,
            'total_count': len(project_summaries)
        }
    
    elif project_name:
        # Get specific project
        project = Project.query.filter(Project.name.ilike(f"%{project_name}%")).first()
        
        if not project:
            return {
                'error': f"Project '{project_name}' not found."
            }
        
        # Get tasks for this project
        pending_tasks = Task.query.filter_by(project_id=project.id, status=TaskStatus.PENDING).all()
        completed_tasks = Task.query.filter_by(project_id=project.id, status=TaskStatus.COMPLETED).all()
        
        # Get documents for this project
        documents = Document.query.filter_by(project_id=project.id).all()
        
        # Calculate total minutes
        pending_minutes = sum(task.estimated_duration for task in pending_tasks)
        completed_minutes = sum(task.estimated_duration for task in completed_tasks)
        
        # Format document summaries
        document_summaries = []
        for doc in documents:
            document_summaries.append({
                'id': doc.id,
                'filename': doc.filename,
                'file_type': doc.file_type,
                'created_at': doc.created_at.strftime('%Y-%m-%d'),
                'summary': doc.summary[:200] + '...' if doc.summary and len(doc.summary) > 200 else doc.summary
            })
        
        return {
            'project': {
                'id': project.id,
                'name': project.name,
                'domain': project.domain.value if project.domain else None,
                'pending_tasks': [
                    {
                        'id': task.id,
                        'description': task.description,
                        'estimated_duration': task.estimated_duration,
                        'deadline': task.deadline.strftime('%Y-%m-%d') if task.deadline else None
                    } for task in pending_tasks
                ],
                'completed_tasks': [
                    {
                        'id': task.id,
                        'description': task.description,
                        'estimated_duration': task.estimated_duration,
                        'completed_at': task.completed_at.strftime('%Y-%m-%d') if task.completed_at else None
                    } for task in completed_tasks
                ],
                'documents': document_summaries,
                'pending_count': len(pending_tasks),
                'completed_count': len(completed_tasks),
                'document_count': len(documents),
                'pending_minutes': pending_minutes,
                'completed_minutes': completed_minutes,
                'completion_rate': len(completed_tasks) / (len(pending_tasks) + len(completed_tasks)) if pending_tasks or completed_tasks else 0
            }
        }
    
    # Default summary of all tasks with projects
    project_tasks = Task.query.filter(Task.project_id.isnot(None)).all()
    no_project_tasks = Task.query.filter(Task.project_id.is_(None)).all()
    
    return {
        'with_project_count': len(project_tasks),
        'no_project_count': len(no_project_tasks),
        'total_count': len(project_tasks) + len(no_project_tasks)
    }

def get_document_summary():
    """Get summary of documents
    
    Returns:
        Dictionary with document summary information
    """
    documents = Document.query.all()
    
    # Group documents by project
    project_docs = {}
    for doc in documents:
        project_id = doc.project_id
        if project_id not in project_docs:
            project_docs[project_id] = []
        
        project_docs[project_id].append({
            'id': doc.id,
            'filename': doc.filename,
            'file_type': doc.file_type,
            'created_at': doc.created_at.strftime('%Y-%m-%d'),
            'has_summary': bool(doc.summary)
        })
    
    # Format response
    result = {
        'total_count': len(documents),
        'by_project': []
    }
    
    for project_id, docs in project_docs.items():
        project = Project.query.get(project_id)
        if project:
            result['by_project'].append({
                'project_id': project_id,
                'project_name': project.name,
                'document_count': len(docs),
                'documents': docs
            })
    
    return result

def complete_task_by_identifier(identifier):
    """Mark a task as completed
    
    Args:
        identifier: Task ID or description text
        
    Returns:
        (success, message): Tuple with success flag and message
    """
    task = None
    
    # If identifier is a number, try to get task by ID
    if isinstance(identifier, int):
        task = Task.query.get(identifier)
    else:
        # Otherwise, search by description
        task = Task.query.filter(Task.description.ilike(f"%{identifier}%")).first()
    
    if not task:
        return (False, f"Task not found: {identifier}")
    
    # Mark task as completed
    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.utcnow()
    
    db.session.commit()
    
    return (True, f"Task marked as completed: {task.description}")

def generate_llm_response(message, context=None):
    """Generate a response using the LLM API
    
    Args:
        message: User's message
        context: Optional context information
        
    Returns:
        Response text from LLM
    """
    # Get API details from config
    api_key = current_app.config.get('LLM_API_KEY')
    api_url = current_app.config.get('LLM_API_URL')
    
    if not api_key or not api_url:
        logger.error("LLM API key or URL not configured")
        return "I'm sorry, I can't generate a natural language response right now. My API connection is not configured."
    
    # Prepare system prompt based on available context
    system_prompt = """You are an assistant for a task management system called kAIros.
You help users manage their tasks, calendar, and projects.
Respond in a helpful, friendly, and concise manner.
For task-related questions, you can access information about the user's tasks, calendar, and projects.
"""
    
    # Add context if provided
    if context:
        system_prompt += "\nHere is information about the user's current tasks and schedule:\n"
        for key, value in context.items():
            if value:
                system_prompt += f"\n{key}: {value}\n"
    
    # Get conversation history from session
    conversation_history = session.get('conversation_history', [])
    
    # Prepare messages for LLM
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add conversation history (up to last 5 exchanges)
    recent_history = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
    for entry in recent_history[:-1]:  # Exclude the current message
        if entry['role'] == 'user':
            messages.append({"role": "user", "content": entry['message']})
        else:
            messages.append({"role": "assistant", "content": entry['message']})
    
    # Add current user message
    messages.append({"role": "user", "content": message})
    
    # Prepare request
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": "deepseek-ai/deepseek-llm-7b-chat", # Default model
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 300
    }
    
    try:
        # Make request to LLM API
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        # Parse response
        result = response.json()
        
        # Extract response text
        response_text = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        
        if not response_text:
            raise ValueError("Empty response from LLM API")
        
        return response_text
    
    except Exception as e:
        logger.error(f"Error generating LLM response: {str(e)}")
        return "I'm sorry, I couldn't generate a specific response. Please try again or ask a different question."

def log_conversation(user_id, message, response, message_type):
    """Log a conversation exchange
    
    Args:
        user_id: Unique identifier for the user
        message: User's message
        response: System response
        message_type: Type of message
    """
    # In a future implementation, this could store conversations in the database
    # For now, just log to the application log
    logger.info(f"CHAT [{user_id}] [{message_type}] User: {message}")
    logger.info(f"CHAT [{user_id}] [{message_type}] System: {response}")

@chat_bp.route('/message', methods=['POST'])
def process_message():
    """API endpoint to process chat messages"""
    data = request.get_json()
    
    if not data or 'message' not in data:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400
    
    user_message = data['message']
    logger.info(f"Processing chat message: {user_message}")
    
    # Get or create user_id for session tracking
    user_id = session.get('user_id')
    if not user_id:
        user_id = str(uuid.uuid4())
        session['user_id'] = user_id
        session['conversation_history'] = []
    
    # Get conversation history from session
    conversation_history = session.get('conversation_history', [])
    
    # Add current message to history
    conversation_history.append({
        'role': 'user',
        'message': user_message,
        'timestamp': datetime.utcnow().isoformat()
    })
    
    # Keep only the last 10 messages to avoid session bloat
    if len(conversation_history) > 10:
        conversation_history = conversation_history[-10:]
    
    # Update session with new history
    session['conversation_history'] = conversation_history
    
    # Classify message to determine intent
    message_type, extracted_data = classify_message(user_message)
    
    # Process based on message type
    if message_type == MESSAGE_TYPES['TIME_AVAILABLE']:
        available_time = extracted_data
        suggestions = get_task_suggestions(available_time)
        
        # Format response based on suggestions
        if suggestions:
            response = {
                'status': 'success',
                'type': 'suggestions',
                'message': f"Here's what you could do with {available_time} minutes:",
                'suggestions': suggestions,
                'available_time': available_time
            }
        else:
            response = {
                'status': 'success',
                'type': 'info',
                'message': f"I couldn't find any tasks that fit in {available_time} minutes."
            }
        
    elif message_type == MESSAGE_TYPES['TASK_CREATION']:
        # Parse the task
        parser = TaskParser()
        task_data = parser.parse_task(user_message)
        
        if not task_data:
            response = {
                'status': 'error',
                'message': "I couldn't understand your task. Please try again with proper formatting, such as: 'Add task: Complete report #work @project [2h] due:friday'"
            }
        else:
            # Validate the parsed task
            missing_fields = parser.validate_task(task_data)
            
            # If missing required fields, prompt for them
            if missing_fields:
                response = {
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
                }
            else:
                # Create the task
                task, message = create_task_from_parsed_data(task_data)
                
                response = {
                    'status': 'success',
                    'type': 'task_added',
                    'message': message,
                    'task_id': task.id
                }
    
    elif message_type == MESSAGE_TYPES['CALENDAR_QUERY']:
        date_range = extracted_data
        
        # If no date range specified, default to today
        if not date_range:
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            date_range = (today, today + timedelta(days=1) - timedelta(seconds=1))
        
        # Get calendar summary
        summary = get_calendar_summary(date_range[0], date_range[1])
        
        # Format date range for display
        if date_range[0].date() == date_range[1].date():
            date_display = date_range[0].strftime('%A, %B %d')
        else:
            date_display = f"{date_range[0].strftime('%A, %B %d')} to {date_range[1].strftime('%A, %B %d')}"
        
        response = {
            'status': 'success',
            'type': 'calendar',
            'message': f"Calendar for {date_display}:",
            'summary': summary
        }
    
    elif message_type == MESSAGE_TYPES['DOMAIN_QUERY']:
        domain = extracted_data
        
        # Get tasks for the specified domain
        domain_tasks = Task.query.filter_by(domain=domain, status=TaskStatus.PENDING).all()
        
        # Format tasks for response
        formatted_tasks = []
        for task in domain_tasks:
            formatted_task = {
                'id': task.id,
                'description': task.description,
                'estimated_duration': task.estimated_duration
            }
            
            if task.project:
                formatted_task['project'] = task.project.name
            
            if task.deadline:
                formatted_task['deadline'] = task.deadline.strftime('%Y-%m-%d')
            
            formatted_tasks.append(formatted_task)
        
        # Get domain display name
        domain_names = {
            TaskDomain.WORK: 'Work',
            TaskDomain.LIFE_ADMIN: 'Life Admin',
            TaskDomain.GENERAL_LIFE: 'General Life'
        }
        domain_name = domain_names.get(domain, str(domain))
        
        response = {
            'status': 'success',
            'type': 'domain_tasks',
            'message': f"Here are your {domain_name} tasks:",
            'domain': domain.value,
            'tasks': formatted_tasks,
            'count': len(formatted_tasks)
        }
    
    elif message_type == MESSAGE_TYPES['PROJECT_QUERY']:
        project_name = extracted_data
        
        # Get project summary
        summary = get_project_summary(project_name)
        
        if 'error' in summary:
            response = {
                'status': 'error',
                'message': summary['error']
            }
        else:
            response = {
                'status': 'success',
                'type': 'project',
                'message': "Here's the project information you requested:",
                'summary': summary
            }
    
    elif message_type == MESSAGE_TYPES['DOCUMENT_QUERY']:
        # Get document summary
        summary = get_document_summary()
        
        response = {
            'status': 'success',
            'type': 'documents',
            'message': f"You have {summary['total_count']} documents across {len(summary['by_project'])} projects:",
            'summary': summary
        }
    
    elif message_type == MESSAGE_TYPES['TASK_COMPLETION']:
        # Complete the task
        success, message = complete_task_by_identifier(extracted_data)
        
        if success:
            response = {
                'status': 'success',
                'type': 'task_completed',
                'message': message
            }
        else:
            response = {
                'status': 'error',
                'message': message
            }
    
    elif message_type == MESSAGE_TYPES['HELP_REQUEST']:
        # Provide help information
        response = {
            'status': 'success',
            'type': 'help',
            'message': "Here's how you can interact with kAIros:",
            'help_sections': [
                {
                    'title': 'Task Management',
                    'items': [
                        "Add a task: 'Add task: Submit report #work @project [2h] due:friday'",
                        "Time query: 'What can I do in 30 minutes?'",
                        "Complete a task: 'Mark task 3 as completed'"
                    ]
                },
                {
                    'title': 'Project & Domain Management',
                    'items': [
                        "List projects: 'Show me all projects'",
                        "Project tasks: 'Show tasks in project Research'",
                        "Domain tasks: 'Show me my work tasks'"
                    ]
                },
                {
                    'title': 'Calendar Integration',
                    'items': [
                        "View calendar: 'What's on my calendar today?'",
                        "Check availability: 'What's my schedule for this week?'"
                    ]
                },
                {
                    'title': 'Document Management',
                    'items': [
                        "View documents: 'Show me my documents'"
                    ]
                }
            ]
        }
    
    elif message_type == MESSAGE_TYPES['GREETING']:
        # Respond to greeting with task summary
        domain_summary = get_domain_summary()
        
        next_task = recommend_next_task(Task.query.filter_by(status=TaskStatus.PENDING).all())
        next_task_info = None
        
        if next_task:
            next_task_info = {
                'id': next_task.id,
                'description': next_task.description,
                'estimated_duration': next_task.estimated_duration,
                'domain': next_task.domain.value
            }
            
            if next_task.project:
                next_task_info['project'] = next_task.project.name
            
            if next_task.deadline:
                next_task_info['deadline'] = next_task.deadline.strftime('%Y-%m-%d')
        
        response = {
            'status': 'success',
            'type': 'greeting',
            'message': f"Hello! You have {domain_summary['total_count']} tasks pending across all domains.",
            'domain_summary': domain_summary,
            'next_task': next_task_info
        }
    
    elif message_type == MESSAGE_TYPES['TASK_QUERY']:
        # General query about tasks - provide an overview
        pending_count = Task.query.filter_by(status=TaskStatus.PENDING).count()
        completed_count = Task.query.filter_by(status=TaskStatus.COMPLETED).count()
        
        # Get tasks with approaching deadlines
        today = datetime.utcnow()
        upcoming_deadline_tasks = Task.query.filter(
            Task.deadline.isnot(None),
            Task.deadline > today,
            Task.deadline <= today + timedelta(days=3),
            Task.status == TaskStatus.PENDING
        ).order_by(Task.deadline).all()
        
        # Format upcoming deadline tasks
        upcoming_tasks = []
        for task in upcoming_deadline_tasks:
            upcoming_tasks.append({
                'id': task.id,
                'description': task.description,
                'deadline': task.deadline.strftime('%Y-%m-%d'),
                'estimated_duration': task.estimated_duration,
                'domain': task.domain.value
            })
        
        # Get recommended next task
        next_task = recommend_next_task(Task.query.filter_by(status=TaskStatus.PENDING).all())
        next_task_info = None
        
        if next_task:
            next_task_info = {
                'id': next_task.id,
                'description': next_task.description,
                'estimated_duration': next_task.estimated_duration,
                'domain': next_task.domain.value
            }
        
        response = {
            'status': 'success',
            'type': 'task_overview',
            'message': f"You have {pending_count} pending tasks and have completed {completed_count} tasks.",
            'pending_count': pending_count,
            'completed_count': completed_count,
            'completion_rate': completed_count / (pending_count + completed_count) if (pending_count + completed_count) > 0 else 0,
            'upcoming_deadlines': upcoming_tasks,
            'next_task': next_task_info
        }
    
    else:  # General question or unrecognized intent
        # Get context for LLM
        context = {
            'Tasks': f"{Task.query.filter_by(status=TaskStatus.PENDING).count()} pending tasks",
            'Domains': f"Work: {Task.query.filter_by(domain=TaskDomain.WORK, status=TaskStatus.PENDING).count()}, " +
                      f"Life Admin: {Task.query.filter_by(domain=TaskDomain.LIFE_ADMIN, status=TaskStatus.PENDING).count()}, " +
                      f"General Life: {Task.query.filter_by(domain=TaskDomain.GENERAL_LIFE, status=TaskStatus.PENDING).count()}"
        }
        
        # Try to generate a natural language response with LLM
        response_text = generate_llm_response(user_message, context)
        
        response = {
            'status': 'success',
            'type': 'general_response',
            'message': response_text
        }
    
    # Log the conversation
    log_conversation(user_id, user_message, response.get('message', ''), message_type)
    
    # Add system response to conversation history
    conversation_history = session.get('conversation_history', [])
    conversation_history.append({
        'role': 'system',
        'message': response.get('message', ''),
        'timestamp': datetime.utcnow().isoformat()
    })
    
    # Keep only the last 10 messages to avoid session bloat
    if len(conversation_history) > 10:
        conversation_history = conversation_history[-10:]
    
    # Update session
    session['conversation_history'] = conversation_history
    
    return jsonify(response)

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
    return render_template('chat.html', title='kAIros Chat Interface')