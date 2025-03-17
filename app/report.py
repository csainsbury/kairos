# Reporting and Email Summary Module for kAIros

import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from flask import current_app, render_template_string
from app.models import TaskLog, Task, Subtask, TaskDomain
from app.utils import setup_logger, retry_with_backoff
from sqlalchemy import func

# Initialize logger
logger = setup_logger(__name__)

def generate_daily_report(date=None):
    """
    Generate a daily report of completed tasks for the specified date
    
    Args:
        date: The date to generate the report for, defaults to yesterday
        
    Returns:
        A dictionary containing the report data
    """
    # Default to yesterday if no date provided
    if date is None:
        date = datetime.utcnow().date() - timedelta(days=1)
    elif isinstance(date, str):
        date = datetime.strptime(date, '%Y-%m-%d').date()
    
    # Calculate start and end of day in UTC
    start_of_day = datetime.combine(date, datetime.min.time())
    end_of_day = datetime.combine(date, datetime.max.time())
    
    # Get all task logs for the date
    task_logs = TaskLog.query.filter(
        TaskLog.completed_at >= start_of_day,
        TaskLog.completed_at <= end_of_day
    ).all()
    
    # Organize by domain
    logs_by_domain = {
        'work': [],
        'life_admin': [],
        'general_life': []
    }
    
    for log in task_logs:
        domain_key = log.domain.value if log.domain else 'other'
        if domain_key in logs_by_domain:
            logs_by_domain[domain_key].append(log)
    
    # Calculate domain statistics
    stats = {}
    for domain, logs in logs_by_domain.items():
        if logs:
            estimated_total = sum(log.estimated_duration for log in logs)
            actual_total = sum(log.actual_duration for log in logs if log.actual_duration)
            
            # Calculate efficiency (actual/estimated)
            efficiency = (actual_total / estimated_total) if estimated_total > 0 else 0
            
            stats[domain] = {
                'count': len(logs),
                'estimated_duration': estimated_total,
                'actual_duration': actual_total,
                'efficiency': efficiency,
                'tasks': logs
            }
        else:
            stats[domain] = {
                'count': 0,
                'estimated_duration': 0,
                'actual_duration': 0,
                'efficiency': 0,
                'tasks': []
            }
    
    # Calculate totals
    total_count = sum(s['count'] for s in stats.values())
    total_estimated = sum(s['estimated_duration'] for s in stats.values())
    total_actual = sum(s['actual_duration'] for s in stats.values())
    total_efficiency = (total_actual / total_estimated) if total_estimated > 0 else 0
    
    # Get incomplete tasks with upcoming deadlines
    today = datetime.utcnow().date()
    upcoming_tasks = Task.query.filter(
        Task.deadline.isnot(None),
        Task.status != 'completed',
        Task.deadline >= today,
        Task.deadline <= (today + timedelta(days=7))
    ).order_by(Task.deadline).limit(5).all()
    
    # Generate report data
    report = {
        'date': date.strftime('%Y-%m-%d'),
        'formatted_date': date.strftime('%A, %B %d, %Y'),
        'total_tasks_completed': total_count,
        'total_estimated_duration': total_estimated,
        'total_actual_duration': total_actual,
        'efficiency': total_efficiency,
        'domains': stats,
        'upcoming_tasks': upcoming_tasks
    }
    
    # Add environment-specific debug info in development
    if os.environ.get('FLASK_ENV') != 'production':
        # Add some debug info for development reports
        report['is_debug'] = True
        report['query_info'] = {
            'start_time': start_of_day.isoformat(),
            'end_time': end_of_day.isoformat(),
            'log_count': len(task_logs)
        }
    
    return report

def format_report_as_html(report_data):
    """
    Format report data as an HTML email
    
    Args:
        report_data: The report data dictionary
        
    Returns:
        HTML formatted report
    """
    # Simple HTML template for the report
    template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>kAIros Daily Report - {{ report.formatted_date }}</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
            }
            
            .report-header {
                background-color: #4285f4;
                color: white;
                padding: 20px;
                border-radius: 5px 5px 0 0;
                margin-bottom: 0;
            }
            
            .report-body {
                background-color: #f9f9f9;
                padding: 20px;
                border-radius: 0 0 5px 5px;
                margin-top: 0;
            }
            
            .domain-section {
                margin-top: 25px;
                padding: 15px;
                border-radius: 5px;
            }
            
            .work-section {
                background-color: rgba(66, 133, 244, 0.1);
                border-left: 3px solid #4285f4;
            }
            
            .life-admin-section {
                background-color: rgba(234, 67, 53, 0.1);
                border-left: 3px solid #ea4335;
            }
            
            .general-life-section {
                background-color: rgba(52, 168, 83, 0.1);
                border-left: 3px solid #34a853;
            }
            
            .summary-box {
                background-color: #f1f1f1;
                padding: 15px;
                border-radius: 5px;
                margin: 20px 0;
            }
            
            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 10px;
            }
            
            th, td {
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }
            
            th {
                background-color: #f2f2f2;
            }
            
            .upcoming-tasks {
                margin-top: 25px;
                padding: 15px;
                background-color: rgba(251, 188, 5, 0.1);
                border-left: 3px solid #fbbc05;
                border-radius: 5px;
            }
            
            .footer {
                margin-top: 30px;
                font-size: 12px;
                color: #999;
                text-align: center;
            }
            
            .debug-info {
                margin-top: 30px;
                padding: 15px;
                background-color: #f8f8f8;
                border: 1px dashed #ccc;
                font-family: monospace;
                font-size: 12px;
            }
        </style>
    </head>
    <body>
        <div class="report-header">
            <h1>kAIros Daily Report</h1>
            <h2>{{ report.formatted_date }}</h2>
        </div>
        
        <div class="report-body">
            <div class="summary-box">
                <h3>Daily Summary</h3>
                <p><strong>{{ report.total_tasks_completed }}</strong> tasks completed</p>
                <p><strong>Estimated Time:</strong> {{ report.total_estimated_duration }} minutes</p>
                <p><strong>Actual Time:</strong> {{ report.total_actual_duration }} minutes</p>
                <p><strong>Efficiency:</strong> {{ (report.efficiency * 100)|round|int }}%</p>
            </div>
            
            {% for domain_name, domain_data in report.domains.items() %}
                {% if domain_data.count > 0 %}
                    <div class="domain-section {{ domain_name }}-section">
                        <h3>{{ domain_name|replace('_', ' ')|title }}</h3>
                        <p>{{ domain_data.count }} tasks completed</p>
                        <p>Estimated: {{ domain_data.estimated_duration }} minutes | 
                           Actual: {{ domain_data.actual_duration }} minutes | 
                           Efficiency: {{ (domain_data.efficiency * 100)|round|int }}%</p>
                        
                        <table>
                            <thead>
                                <tr>
                                    <th>Task</th>
                                    <th>Estimated (min)</th>
                                    <th>Actual (min)</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for task in domain_data.tasks %}
                                <tr>
                                    <td>{{ task.description }}</td>
                                    <td>{{ task.estimated_duration }}</td>
                                    <td>{{ task.actual_duration }}</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                {% endif %}
            {% endfor %}
            
            <div class="upcoming-tasks">
                <h3>Upcoming Deadlines</h3>
                {% if report.upcoming_tasks %}
                    <table>
                        <thead>
                            <tr>
                                <th>Task</th>
                                <th>Deadline</th>
                                <th>Domain</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for task in report.upcoming_tasks %}
                            <tr>
                                <td>{{ task.description }}</td>
                                <td>{{ task.deadline.strftime('%Y-%m-%d') }}</td>
                                <td>{{ task.domain.value|replace('_', ' ')|title }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                {% else %}
                    <p>No upcoming deadlines in the next 7 days.</p>
                {% endif %}
            </div>
            
            {% if report.is_debug %}
            <div class="debug-info">
                <h4>Debug Information</h4>
                <p>Generated for timeframe: {{ report.query_info.start_time }} to {{ report.query_info.end_time }}</p>
                <p>Found {{ report.query_info.log_count }} task logs</p>
            </div>
            {% endif %}
            
            <div class="footer">
                <p>This report was automatically generated by kAIros. © 2023</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Render the template with the report data
    return render_template_string(template, report=report_data)

def format_report_as_text(report_data):
    """
    Format report data as plain text for email
    
    Args:
        report_data: The report data dictionary
        
    Returns:
        Plain text formatted report
    """
    # Simple text template for the report
    text = f"""
kAIros Daily Report - {report_data['formatted_date']}
{'=' * 50}

DAILY SUMMARY
-------------
Tasks Completed: {report_data['total_tasks_completed']}
Estimated Time: {report_data['total_estimated_duration']} minutes
Actual Time: {report_data['total_actual_duration']} minutes
Efficiency: {int(report_data['efficiency'] * 100)}%

"""
    
    # Add domain sections
    for domain_name, domain_data in report_data['domains'].items():
        if domain_data['count'] > 0:
            domain_title = domain_name.replace('_', ' ').upper()
            text += f"""
{domain_title}
{'-' * len(domain_title)}
Tasks Completed: {domain_data['count']}
Estimated: {domain_data['estimated_duration']} min | Actual: {domain_data['actual_duration']} min | Efficiency: {int(domain_data['efficiency'] * 100)}%

Completed Tasks:
"""
            
            for task in domain_data['tasks']:
                text += f"- {task.description} (Est: {task.estimated_duration} min, Act: {task.actual_duration or 'N/A'} min)\n"
    
    # Add upcoming tasks
    text += f"""
UPCOMING DEADLINES
-----------------
"""
    if report_data['upcoming_tasks']:
        for task in report_data['upcoming_tasks']:
            deadline = task.deadline.strftime('%Y-%m-%d') if task.deadline else 'No deadline'
            domain = task.domain.value.replace('_', ' ').title() if task.domain else 'No domain'
            text += f"- {task.description} (Due: {deadline}, Domain: {domain})\n"
    else:
        text += "No upcoming deadlines in the next 7 days.\n"
    
    # Add footer
    text += f"""
{'=' * 50}
This report was automatically generated by kAIros. © 2023
"""
    
    return text

@retry_with_backoff(max_retries=3)
def send_email_report(report_data, recipient_email):
    """
    Send the report via email
    
    Args:
        report_data: The report data dictionary
        recipient_email: The recipient's email address
        
    Returns:
        Boolean indicating success
    """
    # Get email configuration from app config or environment variables
    smtp_server = current_app.config.get('SMTP_SERVER') or os.environ.get('SMTP_SERVER')
    smtp_port = int(current_app.config.get('SMTP_PORT') or os.environ.get('SMTP_PORT', 587))
    smtp_username = current_app.config.get('SMTP_USERNAME') or os.environ.get('SMTP_USERNAME')
    smtp_password = current_app.config.get('SMTP_PASSWORD') or os.environ.get('SMTP_PASSWORD')
    sender_email = current_app.config.get('SENDER_EMAIL') or os.environ.get('SENDER_EMAIL')
    
    # Validate configuration
    if not all([smtp_server, smtp_port, smtp_username, smtp_password, sender_email]):
        logger.error("Email configuration is incomplete. Please check SMTP settings.")
        return False
    
    try:
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"kAIros Daily Report - {report_data['formatted_date']}"
        msg['From'] = sender_email
        msg['To'] = recipient_email
        
        # Create plain text and HTML versions of the message
        text_content = format_report_as_text(report_data)
        html_content = format_report_as_html(report_data)
        
        # Attach parts
        msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))
        
        # Connect to server and send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()  # Secure the connection
            server.login(smtp_username, smtp_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        
        logger.info(f"Daily report sent to {recipient_email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email report: {str(e)}")
        # Reraise for retry decorator
        raise
    
def schedule_daily_report():
    """Set up scheduling for daily reports"""
    # This would be integrated with a proper job scheduler in production
    # For this MVP, we'll pretend this is scheduled and just provide 
    # the capability to generate and send the report
    
    # Example implementation using APScheduler could be added here
    pass

# API for manual report generation (useful for testing)
def generate_and_send_report(date=None, recipient_email=None):
    """
    Generate and send a report for the specified date
    
    Args:
        date: The date to generate the report for (YYYY-MM-DD string or None for yesterday)
        recipient_email: The recipient's email address, uses default if None
        
    Returns:
        Report data and send status
    """
    # Generate the report data
    report_data = generate_daily_report(date)
    
    # Use default recipient if none provided
    if not recipient_email:
        recipient_email = current_app.config.get('DEFAULT_REPORT_EMAIL') or os.environ.get('DEFAULT_REPORT_EMAIL')
        
    if not recipient_email:
        logger.error("No recipient email provided and no default configured")
        return report_data, False
    
    # Send the email
    send_success = send_email_report(report_data, recipient_email)
    
    return report_data, send_success