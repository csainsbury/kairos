import pytest
import json
import os
import sys
import datetime
from unittest.mock import patch, MagicMock
from flask import Flask, url_for

# Add parent directory to path so imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models import db, Task, Subtask, Project, Document, TaskLog
from app.utils import setup_logger

logger = setup_logger(__name__)

class MockResponse:
    """Mock API response for testing"""
    def __init__(self, json_data, status_code):
        self.json_data = json_data
        self.status_code = status_code
        self.text = json.dumps(json_data)
        
    def json(self):
        return self.json_data
        
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP Error: {self.status_code}")

# Shared fixtures for integration tests
@pytest.fixture
def app():
    """Create and configure a Flask app for testing"""
    from app import create_app
    
    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.app_context():
        db.create_all()
        # Create test data
        create_test_data()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    """Test client for the Flask app"""
    return app.test_client()

@pytest.fixture
def runner(app):
    """CLI runner for the Flask app"""
    return app.test_cli_runner()

def create_test_data():
    """Create sample data for tests"""
    # Create test domains
    work_project = Project(name="Work Project", domain="work")
    life_admin_project = Project(name="Life Admin Project", domain="life_admin")
    general_life_project = Project(name="General Life Project", domain="general_life")
    
    # Create test tasks
    urgent_task = Task(
        description="Urgent work task",
        deadline=datetime.datetime.now() + datetime.timedelta(days=1),
        estimated_duration=60,
        domain="work",
        project=work_project,
        status="pending"
    )
    
    normal_task = Task(
        description="Normal life admin task",
        deadline=datetime.datetime.now() + datetime.timedelta(days=3),
        estimated_duration=30,
        domain="life_admin",
        project=life_admin_project,
        status="pending"
    )
    
    long_term_task = Task(
        description="Long-term life goal",
        deadline=datetime.datetime.now() + datetime.timedelta(days=90),
        estimated_duration=120,
        domain="general_life",
        project=general_life_project,
        status="pending"
    )
    
    # Create subtasks
    subtask1 = Subtask(
        description="First step of urgent task",
        task=urgent_task,
        status="pending",
        estimated_duration=20
    )
    
    subtask2 = Subtask(
        description="Second step of urgent task",
        task=urgent_task,
        status="pending",
        estimated_duration=40
    )
    
    # Add document to project
    document = Document(
        filename="test_document.txt",
        file_path="/tmp/test_document.txt",
        file_type="text/plain",
        summary="This is a test document summary",
        project=work_project
    )
    
    # Add all objects to session
    db.session.add_all([
        work_project, life_admin_project, general_life_project,
        urgent_task, normal_task, long_term_task,
        subtask1, subtask2, document
    ])
    db.session.commit()

# Todoist webhook integration test
@patch('app.todoist.requests.post')
def test_todoist_webhook_integration(mock_post, client):
    """Test the Todoist webhook integration creates tasks correctly"""
    # Mock the Todoist API response
    mock_post.return_value = MockResponse({"id": "12345"}, 200)
    
    # Sample webhook payload
    webhook_data = {
        "event_name": "item:added",
        "user_id": "12345",
        "event_data": {
            "content": "New task from webhook @Work Project [30m] #work",
            "description": "This is a test task from Todoist webhook",
            "due": {
                "date": (datetime.datetime.now() + datetime.timedelta(days=2)).strftime("%Y-%m-%d")
            },
            "id": "54321"
        }
    }
    
    # Send webhook request
    response = client.post('/api/todoist/webhook', 
                          data=json.dumps(webhook_data),
                          content_type='application/json')
    
    assert response.status_code == 200
    assert json.loads(response.data)['status'] == 'success'
    
    # Verify task was created with correct data
    task = Task.query.filter_by(description="New task from webhook").first()
    assert task is not None
    assert task.domain == "work"
    assert task.estimated_duration == 30
    assert task.project.name == "Work Project"
    
    # Verify Todoist sync - webhook should call our API to update Todoist
    mock_post.assert_called_once()

# Direct task input test with prompts for missing data
@patch('app.todoist.requests.post')  # Skip actual Todoist API calls
def test_direct_task_input_with_missing_data(mock_post, client):
    """Test direct task input with missing data prompts"""
    # First submit incomplete task (missing deadline)
    response = client.post('/api/tasks', 
                          data=json.dumps({
                              "description": "Incomplete task",
                              "estimated_duration": 60,
                              "domain": "work"
                          }),
                          content_type='application/json')
    
    # Should get a response asking for more info
    assert response.status_code == 400
    assert 'missing' in json.loads(response.data)['message'].lower()
    assert 'deadline' in json.loads(response.data)['message'].lower()
    
    # Now provide complete data
    response = client.post('/api/tasks', 
                          data=json.dumps({
                              "description": "Complete task",
                              "estimated_duration": 60,
                              "domain": "work",
                              "deadline": (datetime.datetime.now() + datetime.timedelta(days=5)).strftime("%Y-%m-%d"),
                              "project_id": 1  # From test data creation
                          }),
                          content_type='application/json')
    
    assert response.status_code == 200
    assert json.loads(response.data)['status'] == 'success'
    
    # Verify task created correctly
    task = Task.query.filter_by(description="Complete task").first()
    assert task is not None
    assert task.domain == "work"
    assert task.estimated_duration == 60

# Document upload and summarization test
@patch('app.document.requests.post')  # Mock LLM API
def test_document_upload_and_summary(mock_post, client, tmp_path):
    """Test document upload and LLM summarization"""
    # Mock the LLM API response
    mock_post.return_value = MockResponse({
        "summary": "This is an automatically generated summary of the test document"
    }, 200)
    
    # Create a test file
    test_file_path = os.path.join(tmp_path, "test_doc.txt")
    with open(test_file_path, "w") as f:
        f.write("This is a test document content for summarization.")
    
    # Upload the document
    with open(test_file_path, "rb") as f:
        response = client.post(
            '/api/documents/upload',
            data={
                'file': (f, 'test_doc.txt'),
                'project_id': 1,  # From test data creation
                'description': 'Test document upload'
            },
            content_type='multipart/form-data'
        )
    
    assert response.status_code == 200
    assert json.loads(response.data)['status'] == 'success'
    
    # Verify document was created and summarized
    document = Document.query.filter_by(filename="test_doc.txt").first()
    assert document is not None
    assert "automatically generated summary" in document.summary
    assert document.project_id == 1

# Calendar integration test
@patch('app.calendar.build')  # Mock Google API client build
def test_calendar_event_creation(mock_build, client):
    """Test calendar event creation and synchronization"""
    # Create mock calendar API
    mock_events = MagicMock()
    mock_events.insert.return_value.execute.return_value = {
        "id": "event123",
        "htmlLink": "https://calendar.google.com/event?id=event123"
    }
    
    mock_calendar = MagicMock()
    mock_calendar.events.return_value = mock_events
    
    mock_build.return_value.calendar.return_value = mock_calendar
    
    # Create a calendar event for a task
    response = client.post(
        '/api/calendar/events',
        data=json.dumps({
            'task_id': 1,  # From test data creation
            'start_time': '14:00',
            'end_time': '15:00',
            'date': datetime.datetime.now().strftime("%Y-%m-%d")
        }),
        content_type='application/json'
    )
    
    assert response.status_code == 200
    assert json.loads(response.data)['status'] == 'success'
    
    # Verify the Google Calendar API was called correctly
    mock_events.insert.assert_called_once()
    # Check it was called with task description in the summary
    call_args = mock_events.insert.call_args[1]
    assert "Urgent work task" in call_args['body']['summary']

# Task ranking integration test
def test_ranking_algorithm(client):
    """Test the task ranking algorithm returns correctly sorted tasks"""
    response = client.get('/api/tasks/ranked')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    
    # Verify tasks are returned in correct order (urgent first)
    tasks = data['tasks']
    assert len(tasks) >= 3
    assert tasks[0]['description'] == "Urgent work task"  # Due tomorrow
    
    # Check domain-specific ranking
    response = client.get('/api/tasks/ranked?domain=life_admin')
    assert response.status_code == 200
    data = json.loads(response.data)
    
    # Should only have life_admin tasks
    tasks = data['tasks']
    assert all(task['domain'] == 'life_admin' for task in tasks)

# Chat interface integration test
def test_chat_interface_responses(client):
    """Test chat interface provides appropriate responses"""
    # Test a time-based query
    response = client.post(
        '/api/chat',
        data=json.dumps({
            'message': 'I have 30 minutes, what should I do?'
        }),
        content_type='application/json'
    )
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['response'] is not None
    
    # Response should include some tasks
    assert 'task' in data['response'].lower()
    
    # Test task creation via chat
    response = client.post(
        '/api/chat',
        data=json.dumps({
            'message': 'Add task "Chat created task" with deadline tomorrow'
        }),
        content_type='application/json'
    )
    
    assert response.status_code == 200
    
    # Verify task was created
    task = Task.query.filter_by(description="Chat created task").first()
    assert task is not None

# Email reporting integration test
@patch('app.report.smtplib.SMTP')
def test_email_report_generation(mock_smtp, client):
    """Test email report generation and sending"""
    # Mock the SMTP connection
    mock_smtp_instance = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_smtp_instance
    
    # Add some task logs to report on
    with client.application.app_context():
        task = Task.query.first()
        task_log = TaskLog(
            task_id=task.id,
            completion_time=datetime.datetime.now(),
            actual_duration=45,
            domain=task.domain
        )
        db.session.add(task_log)
        db.session.commit()
    
    # Request a report
    response = client.post(
        '/api/reports/send-email',
        data=json.dumps({
            'recipient_email': 'test@example.com',
            'date': datetime.datetime.now().strftime("%Y-%m-%d")
        }),
        content_type='application/json'
    )
    
    assert response.status_code == 200
    assert json.loads(response.data)['status'] == 'success'
    
    # Verify email was sent
    mock_smtp_instance.send_message.assert_called_once()
    
    # Check report content
    call_args = mock_smtp_instance.send_message.call_args[0]
    email = call_args[0]
    assert "Daily Task Report" in email['Subject']
    
    # Check HTML report endpoint
    response = client.get(
        f'/api/reports/daily/html?date={datetime.datetime.now().strftime("%Y-%m-%d")}'
    )
    assert response.status_code == 200
    assert b'<html' in response.data
    assert b'completed tasks' in response.data.lower()

# Environment-specific test configuration
def test_environment_specific_behavior(client):
    """Test environment-specific configurations are properly applied"""
    app = client.application
    
    # Should be in testing environment
    assert app.config['TESTING'] is True
    
    # Test environment-specific error detail in development vs production
    with patch.dict('os.environ', {'FLASK_ENV': 'development'}):
        response = client.get('/nonexistent_endpoint')
        assert response.status_code == 404
        data = json.loads(response.data)
        # Development error should be detailed
        assert 'resource was not found' in data['error']['message'].lower()
    
    with patch.dict('os.environ', {'FLASK_ENV': 'production'}):
        response = client.get('/nonexistent_endpoint')
        assert response.status_code == 404
        data = json.loads(response.data)
        # Production error should be sanitized
        assert 'internal server error' not in data['error']['message'].lower()

# Full end-to-end workflow test
def test_end_to_end_workflow(client):
    """Test the complete workflow from task creation to completion"""
    # 1. Create a new task via direct input
    task_data = {
        "description": "E2E workflow test task",
        "estimated_duration": 30,
        "domain": "work",
        "project_id": 1,  # From test data
        "deadline": (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    }
    
    response = client.post(
        '/api/tasks',
        data=json.dumps(task_data),
        content_type='application/json'
    )
    assert response.status_code == 200
    task_id = json.loads(response.data)['task_id']
    
    # 2. Create subtask for the main task
    subtask_data = {
        "description": "E2E subtask",
        "estimated_duration": 15,
        "task_id": task_id
    }
    
    response = client.post(
        '/api/subtasks',
        data=json.dumps(subtask_data),
        content_type='application/json'
    )
    assert response.status_code == 200
    subtask_id = json.loads(response.data)['subtask_id']
    
    # 3. Upload a document and associate with project
    with patch('app.document.requests.post') as mock_post:
        # Mock LLM response
        mock_post.return_value = MockResponse({
            "summary": "E2E test document summary"
        }, 200)
        
        # Create a temporary test file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.txt') as tmp:
            tmp.write(b"E2E test document content")
            tmp.flush()
            
            with open(tmp.name, "rb") as f:
                response = client.post(
                    '/api/documents/upload',
                    data={
                        'file': (f, 'e2e_test.txt'),
                        'project_id': 1,
                        'description': 'E2E test document'
                    },
                    content_type='multipart/form-data'
                )
            
        assert response.status_code == 200
    
    # 4. Create calendar event for the task
    with patch('app.calendar.build') as mock_build:
        # Mock Google Calendar API
        mock_events = MagicMock()
        mock_events.insert.return_value.execute.return_value = {
            "id": "e2e_event",
            "htmlLink": "https://calendar.google.com/event?id=e2e_event"
        }
        
        mock_calendar = MagicMock()
        mock_calendar.events.return_value = mock_events
        
        mock_build.return_value.calendar.return_value = mock_calendar
        
        response = client.post(
            '/api/calendar/events',
            data=json.dumps({
                'task_id': task_id,
                'start_time': '10:00',
                'end_time': '10:30',
                'date': datetime.datetime.now().strftime("%Y-%m-%d")
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 200
    
    # 5. Get ranked tasks to see our task
    response = client.get('/api/tasks/ranked')
    assert response.status_code == 200
    tasks = json.loads(response.data)['tasks']
    
    # Our task should be in the list
    e2e_task = next((t for t in tasks if t['description'] == "E2E workflow test task"), None)
    assert e2e_task is not None
    
    # 6. Complete the subtask and then the main task
    response = client.post(
        f'/api/subtasks/{subtask_id}/complete',
        data=json.dumps({'actual_duration': 15}),
        content_type='application/json'
    )
    assert response.status_code == 200
    
    response = client.post(
        f'/api/tasks/{task_id}/complete',
        data=json.dumps({'actual_duration': 30}),
        content_type='application/json'
    )
    assert response.status_code == 200
    
    # 7. Generate a report including our completed task
    with patch('app.report.smtplib.SMTP') as mock_smtp:
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_smtp_instance
        
        response = client.post(
            '/api/reports/send-email',
            data=json.dumps({
                'recipient_email': 'e2e@example.com',
                'date': datetime.datetime.now().strftime("%Y-%m-%d")
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        
        # Verify our completed task is in the report
        report_response = client.get(
            f'/api/reports/daily?date={datetime.datetime.now().strftime("%Y-%m-%d")}'
        )
        
        report_data = json.loads(report_response.data)
        domain_data = report_data.get('domains', {}).get('work', {})
        completed_tasks = domain_data.get('completed_tasks', [])
        
        # Find our task in the report
        e2e_task_in_report = any(
            task['description'] == "E2E workflow test task" 
            for task in completed_tasks
        )
        assert e2e_task_in_report

if __name__ == '__main__':
    pytest.main(['-xvs', __file__])