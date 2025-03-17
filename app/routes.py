# Routes for kAIros application

from flask import Blueprint, jsonify, render_template, current_app, request
from app.models import Project, Task, Document, TaskStatus, TaskDomain, TaskLog, Subtask, db
from app.ranking import rank_tasks, recommend_next_task, get_ranked_tasks_by_domain
from app.report import generate_daily_report, format_report_as_html, send_email_report, generate_and_send_report
from datetime import datetime, timedelta

bp = Blueprint('main', __name__)

@bp.route('/', methods=['GET'])
def index():
    """Main landing page - redirects to projects page"""
    return render_template('projects.html', title='kAIros - Projects', projects=Project.query.all())

@bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for monitoring and container orchestration"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "environment": current_app.config.get('ENV', 'development'),
        "checks": {}
    }
    
    # Check database connection
    try:
        # Perform a simple query to check DB connection
        db.session.execute("SELECT 1").fetchall()
        health_status["checks"]["database"] = "healthy"
    except Exception as e:
        health_status["checks"]["database"] = "unhealthy"
        health_status["checks"]["database_error"] = str(e)
        health_status["status"] = "degraded"
    
    # Check Redis if configured
    redis_url = current_app.config.get('REDIS_URL')
    if redis_url:
        try:
            import redis
            r = redis.from_url(redis_url)
            r.ping()
            health_status["checks"]["redis"] = "healthy"
        except Exception as e:
            health_status["checks"]["redis"] = "unhealthy"
            health_status["checks"]["redis_error"] = str(e)
            health_status["status"] = "degraded"
    
    # Check file system access
    upload_dir = current_app.config.get('UPLOAD_FOLDER')
    try:
        import os
        if os.path.exists(upload_dir) and os.access(upload_dir, os.W_OK):
            health_status["checks"]["file_system"] = "healthy"
        else:
            health_status["checks"]["file_system"] = "unhealthy"
            health_status["checks"]["file_system_error"] = "Upload directory not accessible"
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["checks"]["file_system"] = "unhealthy"
        health_status["checks"]["file_system_error"] = str(e)
        health_status["status"] = "degraded"
    
    # Return appropriate HTTP status code based on health
    http_status = 200 if health_status["status"] == "healthy" else 503
    return jsonify(health_status), http_status

@bp.route('/api/projects', methods=['GET'])
def get_projects():
    """API endpoint to get all projects"""
    projects = Project.query.all()
    result = []
    
    for project in projects:
        result.append({
            'id': project.id,
            'name': project.name,
            'domain': project.domain.value if project.domain else None
        })
    
    return jsonify({
        'projects': result
    })

@bp.route('/api/tasks', methods=['GET'])
def get_tasks():
    """API endpoint to get all tasks, with optional filtering"""
    # Handle query parameters for filtering
    domain = request.args.get('domain')
    status = request.args.get('status', 'pending')
    project_id = request.args.get('project_id')
    
    # Start with a base query
    query = Task.query
    
    # Apply filters
    if domain:
        try:
            domain_enum = TaskDomain[domain.upper()]
            query = query.filter(Task.domain == domain_enum)
        except KeyError:
            return jsonify({'status': 'error', 'message': f'Invalid domain: {domain}'}), 400
    
    if status:
        try:
            status_enum = TaskStatus[status.upper()]
            query = query.filter(Task.status == status_enum)
        except KeyError:
            return jsonify({'status': 'error', 'message': f'Invalid status: {status}'}), 400
    
    if project_id:
        try:
            project_id = int(project_id)
            query = query.filter(Task.project_id == project_id)
        except ValueError:
            return jsonify({'status': 'error', 'message': f'Invalid project ID: {project_id}'}), 400
    
    # Get results
    tasks = query.all()
    
    # Format for response
    result = []
    for task in tasks:
        result.append({
            'id': task.id,
            'description': task.description,
            'deadline': task.deadline.isoformat() if task.deadline else None,
            'estimated_duration': task.estimated_duration,
            'domain': task.domain.value if task.domain else None,
            'status': task.status.value if task.status else None,
            'project_id': task.project_id,
            'project_name': task.project.name if task.project else None
        })
    
    return jsonify({
        'tasks': result
    })

@bp.route('/api/tasks/with-deadlines', methods=['GET'])
def get_tasks_with_deadlines():
    """API endpoint to get all tasks with deadlines"""
    tasks = Task.query.filter(
        Task.deadline.isnot(None),
        Task.status != TaskStatus.COMPLETED
    ).order_by(Task.deadline).all()
    
    result = []
    for task in tasks:
        result.append({
            'id': task.id,
            'description': task.description,
            'deadline': task.deadline.isoformat() if task.deadline else None,
            'estimated_duration': task.estimated_duration,
            'domain': task.domain.value if task.domain else None,
            'project_id': task.project_id,
            'project_name': task.project.name if task.project else None
        })
    
    return jsonify({
        'tasks': result
    })

@bp.route('/api/ranked-tasks', methods=['GET'])
def get_ranked_tasks():
    """API endpoint to get ranked tasks based on priority
    
    Query parameters:
    - domain: Filter by domain (work, life_admin, general_life)
    - available_time: Available time in minutes
    - time_start: Start time for availability calculation (ISO format)
    - time_end: End time for availability calculation (ISO format)
    """
    # Get all pending tasks
    base_query = Task.query.filter(Task.status != TaskStatus.COMPLETED)
    
    # Apply domain filter if provided
    domain = request.args.get('domain')
    if domain:
        try:
            domain_enum = TaskDomain[domain.upper()]
            tasks = base_query.filter(Task.domain == domain_enum).all()
        except KeyError:
            return jsonify({'status': 'error', 'message': f'Invalid domain: {domain}'}), 400
    else:
        tasks = base_query.all()
    
    # Get parameters for ranking
    available_time = request.args.get('available_time')
    time_start = request.args.get('time_start')
    time_end = request.args.get('time_end')
    
    # Parse available_time
    if available_time:
        try:
            available_time = int(available_time)
        except ValueError:
            return jsonify({'status': 'error', 'message': 'available_time must be an integer'}), 400
    
    # Parse time range if provided
    time_period = None
    if time_start and time_end:
        try:
            start_time = datetime.fromisoformat(time_start.replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(time_end.replace('Z', '+00:00'))
            time_period = (start_time, end_time)
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Invalid time format. Use ISO 8601.'}), 400
    
    # Get current task if any
    current_task_id = request.args.get('current_task_id')
    current_task = None
    if current_task_id:
        try:
            current_task = Task.query.get(int(current_task_id))
        except ValueError:
            return jsonify({'status': 'error', 'message': 'current_task_id must be an integer'}), 400
    
    # Rank the tasks
    ranked_tasks = rank_tasks(tasks, available_time, current_task, time_period)
    
    # Format for response
    result = []
    for idx, task in enumerate(ranked_tasks):
        result.append({
            'id': task.id,
            'rank': idx + 1,
            'description': task.description,
            'deadline': task.deadline.isoformat() if task.deadline else None,
            'estimated_duration': task.estimated_duration,
            'domain': task.domain.value if task.domain else None,
            'project_id': task.project_id,
            'project_name': task.project.name if task.project else None
        })
    
    return jsonify({
        'tasks': result,
        'total_duration': sum(task.estimated_duration for task in ranked_tasks)
    })

@bp.route('/api/next-task', methods=['GET'])
def get_next_task():
    """API endpoint to get the recommended next task
    
    Query parameters:
    - domain: Filter by domain (work, life_admin, general_life)
    - available_time: Available time in minutes
    """
    # Get all pending tasks
    base_query = Task.query.filter(Task.status != TaskStatus.COMPLETED)
    
    # Apply domain filter if provided
    domain = request.args.get('domain')
    if domain:
        try:
            domain_enum = TaskDomain[domain.upper()]
            tasks = base_query.filter(Task.domain == domain_enum).all()
        except KeyError:
            return jsonify({'status': 'error', 'message': f'Invalid domain: {domain}'}), 400
    else:
        tasks = base_query.all()
    
    # Get available time if provided
    available_time = request.args.get('available_time')
    if available_time:
        try:
            available_time = int(available_time)
        except ValueError:
            return jsonify({'status': 'error', 'message': 'available_time must be an integer'}), 400
    
    # Get current task if any
    current_task_id = request.args.get('current_task_id')
    current_task = None
    if current_task_id:
        try:
            current_task = Task.query.get(int(current_task_id))
        except ValueError:
            return jsonify({'status': 'error', 'message': 'current_task_id must be an integer'}), 400
    
    # Get the recommended next task
    next_task = recommend_next_task(tasks, available_time, current_task)
    
    if next_task:
        return jsonify({
            'status': 'success',
            'task': {
                'id': next_task.id,
                'description': next_task.description,
                'deadline': next_task.deadline.isoformat() if next_task.deadline else None,
                'estimated_duration': next_task.estimated_duration,
                'domain': next_task.domain.value if next_task.domain else None,
                'project_id': next_task.project_id,
                'project_name': next_task.project.name if next_task.project else None
            }
        })
    else:
        return jsonify({
            'status': 'success',
            'message': 'No suitable task found',
            'task': None
        })

@bp.route('/api/tasks-for-today', methods=['GET'])
def get_tasks_for_today():
    """API endpoint to get optimized tasks for today
    
    Finds the best tasks to do today based on available time and priorities
    """
    # Calculate today's time range
    now = datetime.utcnow()
    end_of_day = datetime(now.year, now.month, now.day, 23, 59, 59)
    
    # Get working hours time parameter if provided
    working_hours = request.args.get('working_hours', '8')
    try:
        available_minutes = int(float(working_hours) * 60)
    except ValueError:
        return jsonify({'status': 'error', 'message': 'working_hours must be a number'}), 400
    
    # Get domain weights parameter
    domain_weight = request.args.get('domain_focus')
    
    # Get all pending tasks
    tasks = Task.query.filter(Task.status != TaskStatus.COMPLETED).all()
    
    # Rank the tasks with time constraint
    ranked_tasks = rank_tasks(tasks, available_time=available_minutes)
    
    # Format for response
    result = []
    total_duration = 0
    
    for idx, task in enumerate(ranked_tasks):
        total_duration += task.estimated_duration
        
        result.append({
            'id': task.id,
            'rank': idx + 1,
            'description': task.description,
            'deadline': task.deadline.isoformat() if task.deadline else None,
            'estimated_duration': task.estimated_duration,
            'domain': task.domain.value if task.domain else None,
            'project_id': task.project_id,
            'project_name': task.project.name if task.project else None
        })
    
    return jsonify({
        'date': now.date().isoformat(),
        'available_minutes': available_minutes,
        'scheduled_minutes': total_duration,
        'remaining_minutes': max(0, available_minutes - total_duration),
        'tasks': result
    })

@bp.route('/api/tasks-by-domain', methods=['GET'])
def get_tasks_by_domain():
    """API endpoint to get tasks organized by domain"""
    # Get all pending tasks
    all_tasks = Task.query.filter(Task.status != TaskStatus.COMPLETED).all()
    
    # Organize by domain
    work_tasks = [t for t in all_tasks if t.domain == TaskDomain.WORK]
    life_admin_tasks = [t for t in all_tasks if t.domain == TaskDomain.LIFE_ADMIN]
    general_life_tasks = [t for t in all_tasks if t.domain == TaskDomain.GENERAL_LIFE]
    
    # Calculate total estimated time per domain
    work_time = sum(t.estimated_duration for t in work_tasks)
    life_admin_time = sum(t.estimated_duration for t in life_admin_tasks)
    general_life_time = sum(t.estimated_duration for t in general_life_tasks)
    
    # Format response
    def format_task_list(tasks):
        return [{
            'id': t.id,
            'description': t.description,
            'deadline': t.deadline.isoformat() if t.deadline else None,
            'estimated_duration': t.estimated_duration,
            'project_id': t.project_id,
            'project_name': t.project.name if t.project else None
        } for t in tasks]
    
    return jsonify({
        'domains': {
            'work': {
                'count': len(work_tasks),
                'total_minutes': work_time,
                'tasks': format_task_list(work_tasks)
            },
            'life_admin': {
                'count': len(life_admin_tasks),
                'total_minutes': life_admin_time,
                'tasks': format_task_list(life_admin_tasks)
            },
            'general_life': {
                'count': len(general_life_tasks),
                'total_minutes': general_life_time,
                'tasks': format_task_list(general_life_tasks)
            }
        },
        'total_tasks': len(all_tasks),
        'total_minutes': work_time + life_admin_time + general_life_time
    })

@bp.route('/upload', methods=['GET'])
def upload_page():
    """Render the document upload page"""
    return render_template('upload.html', title='Upload Document - kAIros')

@bp.route('/projects', methods=['GET'])
def projects_overview():
    """Render the projects overview page"""
    projects = Project.query.all()
    return render_template('projects.html', title='Projects - kAIros', projects=projects)

@bp.route('/calendar', methods=['GET'])
def calendar_page():
    """Render the calendar management page"""
    return render_template('calendar.html', title='Calendar Management - kAIros')

@bp.route('/tasks', methods=['GET'])
def tasks_page():
    """Render the tasks management page"""
    return render_template('tasks.html', title='Tasks - kAIros')

@bp.route('/api/tasks/<int:task_id>/complete', methods=['POST'])
def complete_task(task_id):
    """API endpoint to mark a task as completed and log it"""
    task = Task.query.get_or_404(task_id)
    
    # Check if already completed
    if task.status == TaskStatus.COMPLETED:
        return jsonify({
            'status': 'error',
            'message': 'Task is already marked as completed'
        }), 400
    
    # Get actual duration from request if provided
    actual_duration = request.json.get('actual_duration') if request.is_json else None
    if actual_duration is None:
        actual_duration = task.estimated_duration  # Default to estimated duration
    
    # Update task status
    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.utcnow()
    
    # Create log entry
    log_entry = TaskLog(
        task_id=task.id,
        description=task.description,
        domain=task.domain,
        estimated_duration=task.estimated_duration,
        actual_duration=actual_duration,
        completed_at=task.completed_at
    )
    
    # Save changes
    db.session.add(log_entry)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'Task marked as completed and logged',
        'task': {
            'id': task.id,
            'description': task.description,
            'estimated_duration': task.estimated_duration,
            'actual_duration': actual_duration,
            'completed_at': task.completed_at.isoformat() if task.completed_at else None
        }
    })

@bp.route('/api/subtasks/<int:subtask_id>/complete', methods=['POST'])
def complete_subtask(subtask_id):
    """API endpoint to mark a subtask as completed and log it"""
    subtask = Subtask.query.get_or_404(subtask_id)
    
    # Check if already completed
    if subtask.status == TaskStatus.COMPLETED:
        return jsonify({
            'status': 'error',
            'message': 'Subtask is already marked as completed'
        }), 400
    
    # Get actual duration from request if provided
    actual_duration = request.json.get('actual_duration') if request.is_json else None
    if actual_duration is None:
        actual_duration = subtask.estimated_duration  # Default to estimated duration
    
    # Update subtask status
    subtask.status = TaskStatus.COMPLETED
    subtask.completed_at = datetime.utcnow()
    subtask.actual_duration = actual_duration
    
    # Create log entry
    log_entry = TaskLog(
        subtask_id=subtask.id,
        description=subtask.description,
        domain=subtask.parent_task.domain,
        estimated_duration=subtask.estimated_duration,
        actual_duration=actual_duration,
        completed_at=subtask.completed_at
    )
    
    # Save changes
    db.session.add(log_entry)
    db.session.commit()
    
    # Check if all subtasks of parent task are completed
    parent_task = subtask.parent_task
    all_subtasks_completed = all(s.status == TaskStatus.COMPLETED for s in parent_task.subtasks)
    
    if all_subtasks_completed and parent_task.subtasks:
        parent_task.status = TaskStatus.COMPLETED
        parent_task.completed_at = datetime.utcnow()
        db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'Subtask marked as completed and logged',
        'subtask': {
            'id': subtask.id,
            'description': subtask.description,
            'estimated_duration': subtask.estimated_duration,
            'actual_duration': actual_duration,
            'completed_at': subtask.completed_at.isoformat() if subtask.completed_at else None
        },
        'parent_task_completed': parent_task.status == TaskStatus.COMPLETED
    })

@bp.route('/reports', methods=['GET'])
def reports_page():
    """Render the reports page"""
    return render_template('reports.html', title='Reports - kAIros')

@bp.route('/api/reports/daily', methods=['GET'])
def get_daily_report():
    """API endpoint to get daily report data"""
    date = request.args.get('date')
    
    try:
        report_data = generate_daily_report(date)
        return jsonify({
            'status': 'success',
            'report': report_data
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to generate report: {str(e)}'
        }), 500

@bp.route('/api/reports/daily/html', methods=['GET'])
def get_daily_report_html():
    """API endpoint to get daily report as HTML"""
    date = request.args.get('date')
    
    try:
        report_data = generate_daily_report(date)
        html = format_report_as_html(report_data)
        return html
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to generate report: {str(e)}'
        }), 500

@bp.route('/api/reports/send-email', methods=['POST'])
def send_email_report_api():
    """API endpoint to send a report by email"""
    if not request.is_json:
        return jsonify({
            'status': 'error',
            'message': 'Request must be JSON'
        }), 400
        
    date = request.json.get('date')
    recipient_email = request.json.get('email')
    
    if not recipient_email:
        return jsonify({
            'status': 'error',
            'message': 'Email address is required'
        }), 400
    
    try:
        report_data, send_success = generate_and_send_report(date, recipient_email)
        
        if send_success:
            return jsonify({
                'status': 'success',
                'message': f'Report sent to {recipient_email}',
                'report': report_data
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to send email, please check server logs',
                'report': report_data
            }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error: {str(e)}'
        }), 500