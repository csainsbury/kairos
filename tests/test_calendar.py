import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from app import create_app
from app.models import db, Task, Project, TaskDomain, TaskStatus
from app.calendar import get_calendar_events, add_calendar_event, sync_task_to_calendar

@pytest.fixture
def app():
    app = create_app('testing')
    
    # Setup test database
    with app.app_context():
        db.create_all()
        
        # Create test project
        project = Project(
            name="Test Project",
            domain=TaskDomain.WORK,
            description="A test project"
        )
        db.session.add(project)
        db.session.commit()
        
        # Create test task with deadline
        task = Task(
            description="Test task with deadline",
            deadline=datetime.utcnow() + timedelta(days=1),
            estimated_duration=60,  # 60 minutes
            domain=TaskDomain.WORK,
            project_id=project.id,
            status=TaskStatus.PENDING
        )
        db.session.add(task)
        db.session.commit()
    
    yield app
    
    # Teardown - remove test database
    with app.app_context():
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

class TestCalendarApi:
    
    @patch('app.calendar.get_calendar_service')
    def test_get_calendar_events(self, mock_get_service, app):
        # Mock the calendar service
        mock_service = MagicMock()
        mock_events_result = {
            'items': [
                {
                    'id': 'event1',
                    'summary': 'Test Event 1',
                    'start': {'dateTime': '2023-05-01T10:00:00Z'},
                    'end': {'dateTime': '2023-05-01T11:00:00Z'},
                    'description': 'Test description'
                }
            ]
        }
        
        mock_service.events().list().execute.return_value = mock_events_result
        mock_get_service.return_value = mock_service
        
        with app.app_context():
            result = get_calendar_events(
                start_time=datetime(2023, 5, 1),
                end_time=datetime(2023, 5, 2)
            )
            
            assert len(result) == 1
            assert result[0]['id'] == 'event1'
            assert result[0]['title'] == 'Test Event 1'
    
    @patch('app.calendar.get_calendar_service')
    def test_add_calendar_event(self, mock_get_service, app):
        # Mock the calendar service
        mock_service = MagicMock()
        mock_created_event = {'id': 'new_event_id'}
        
        mock_service.events().insert().execute.return_value = mock_created_event
        mock_get_service.return_value = mock_service
        
        with app.app_context():
            result = add_calendar_event(
                title="Test Event",
                start_time=datetime(2023, 5, 1, 10, 0),
                end_time=datetime(2023, 5, 1, 11, 0),
                description="Test description"
            )
            
            assert result == 'new_event_id'
            
            # Verify the service was called correctly
            mock_service.events().insert.assert_called_once()
            call_args = mock_service.events().insert.call_args[1]
            assert call_args['calendarId'] == 'primary'
            
            event_body = call_args['body']
            assert event_body['summary'] == 'Test Event'
            assert 'Test description' in event_body['description']
    
    @patch('app.calendar.add_calendar_event')
    def test_sync_task_to_calendar(self, mock_add_event, app):
        mock_add_event.return_value = 'task_event_id'
        
        with app.app_context():
            # Get test task
            task = Task.query.filter_by(description="Test task with deadline").first()
            
            # Test sync task
            result = sync_task_to_calendar(task.id)
            
            assert result == 'task_event_id'
            
            # Verify add_calendar_event was called correctly
            mock_add_event.assert_called_once()
            call_args = mock_add_event.call_args[1]
            
            assert call_args['title'] == task.description
            assert 'Domain: work' in call_args['description']
            assert 'Estimated duration: 60 minutes' in call_args['description']

class TestCalendarRoutes:
    
    @patch('app.calendar.get_calendar_service')
    def test_list_events_route(self, mock_get_service, client):
        # Mock the calendar service
        mock_service = MagicMock()
        mock_events_result = {
            'items': [
                {
                    'id': 'event1',
                    'summary': 'Test Event 1',
                    'start': {'dateTime': '2023-05-01T10:00:00Z'},
                    'end': {'dateTime': '2023-05-01T11:00:00Z'},
                }
            ]
        }
        
        mock_service.events().list().execute.return_value = mock_events_result
        mock_get_service.return_value = mock_service
        
        # Test the endpoint
        response = client.get('/calendar/events')
        data = json.loads(response.data)
        
        assert response.status_code == 200
        assert 'events' in data
        assert len(data['events']) == 1
        assert data['events'][0]['id'] == 'event1'
    
    def test_calendar_page_route(self, client):
        # Test the calendar page route
        response = client.get('/calendar')
        
        assert response.status_code == 200
        assert b'kAIros Calendar Management' in response.data
        assert b'Google Calendar Authentication' in response.data
    
    def test_api_tasks_with_deadlines(self, client):
        # Test the API endpoint for tasks with deadlines
        response = client.get('/api/tasks/with-deadlines')
        data = json.loads(response.data)
        
        assert response.status_code == 200
        assert 'tasks' in data
        assert len(data['tasks']) == 1
        assert data['tasks'][0]['description'] == 'Test task with deadline'
        assert 'deadline' in data['tasks'][0]
        assert data['tasks'][0]['estimated_duration'] == 60
        assert data['tasks'][0]['domain'] == 'work'