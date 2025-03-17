# Tests for Todoist Integration

import unittest
import sys
import os
import json
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from flask import url_for

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import db, Task, Project, TaskStatus, TaskDomain

class TodoistWebhookTestCase(unittest.TestCase):
    """Test case for Todoist webhook integration"""
    
    def setUp(self):
        """Set up test environment"""
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.app.config['TODOIST_CLIENT_SECRET'] = 'test-secret'
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()
        db.create_all()
    
    def tearDown(self):
        """Clean up test environment"""
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
    
    def test_webhook_invalid_payload(self):
        """Test webhook with invalid payload"""
        response = self.client.post('/todoist/webhook', 
                                 data='invalid',
                                 content_type='application/json')
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'error')
    
    def test_webhook_task_added(self):
        """Test webhook for task added event"""
        # Sample webhook payload
        payload = {
            'event_name': 'item:added',
            'event_data': {
                'id': '12345',
                'content': 'Test task #work @TestProject [30m]',
                'project_id': '67890',
                'due': {
                    'date': (datetime.utcnow() + timedelta(days=1)).isoformat()
                }
            }
        }
        
        # Send webhook request
        response = self.client.post('/todoist/webhook',
                                data=json.dumps(payload),
                                content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        
        # Verify task was created
        task = Task.query.filter_by(external_id='12345').first()
        self.assertIsNotNone(task)
        self.assertEqual(task.description, 'Test task')
        self.assertEqual(task.domain, TaskDomain.WORK)
        self.assertEqual(task.estimated_duration, 30)
        
        # Verify project was created
        project = Project.query.filter_by(name='Todoist-67890').first()
        self.assertIsNotNone(project)
        self.assertEqual(task.project_id, project.id)
    
    def test_webhook_task_completed(self):
        """Test webhook for task completed event"""
        # Create a task
        project = Project(name='Test Project', domain=TaskDomain.WORK)
        db.session.add(project)
        
        task = Task(
            description='Test task',
            external_id='12345',
            domain=TaskDomain.WORK,
            project_id=project.id,
            estimated_duration=30,
            status=TaskStatus.PENDING
        )
        db.session.add(task)
        db.session.commit()
        
        # Sample webhook payload
        payload = {
            'event_name': 'item:completed',
            'event_data': {
                'id': '12345'
            }
        }
        
        # Send webhook request
        response = self.client.post('/todoist/webhook',
                                data=json.dumps(payload),
                                content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        
        # Verify task was updated
        task = Task.query.filter_by(external_id='12345').first()
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertIsNotNone(task.completed_at)
    
    def test_webhook_task_updated(self):
        """Test webhook for task updated event"""
        # Create a task
        project = Project(name='Test Project', domain=TaskDomain.WORK)
        db.session.add(project)
        
        task = Task(
            description='Original description',
            external_id='12345',
            domain=TaskDomain.WORK,
            project_id=project.id,
            estimated_duration=30
        )
        db.session.add(task)
        db.session.commit()
        
        # Sample webhook payload
        payload = {
            'event_name': 'item:updated',
            'event_data': {
                'id': '12345',
                'content': 'Updated description #life_admin [60m]'
            }
        }
        
        # Send webhook request
        response = self.client.post('/todoist/webhook',
                                data=json.dumps(payload),
                                content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        
        # Verify task was updated
        task = Task.query.filter_by(external_id='12345').first()
        self.assertEqual(task.description, 'Updated description')
        self.assertEqual(task.domain, TaskDomain.LIFE_ADMIN)
        self.assertEqual(task.estimated_duration, 60)
    
    def test_webhook_task_deleted(self):
        """Test webhook for task deleted event"""
        # Create a task
        project = Project(name='Test Project', domain=TaskDomain.WORK)
        db.session.add(project)
        
        task = Task(
            description='To be deleted',
            external_id='12345',
            domain=TaskDomain.WORK,
            project_id=project.id,
            estimated_duration=30
        )
        db.session.add(task)
        db.session.commit()
        
        # Sample webhook payload
        payload = {
            'event_name': 'item:deleted',
            'event_data': {
                'id': '12345'
            }
        }
        
        # Send webhook request
        response = self.client.post('/todoist/webhook',
                                data=json.dumps(payload),
                                content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        
        # Verify task was deleted
        task = Task.query.filter_by(external_id='12345').first()
        self.assertIsNone(task)
    
    def test_parse_task_endpoint(self):
        """Test manual task parsing endpoint"""
        # Task text
        task_text = "Write documentation #work @docs [90m] due:tomorrow"
        
        # Send parse request
        response = self.client.post('/todoist/parse',
                                data=json.dumps({'text': task_text}),
                                content_type='application/json')
        
        self.assertEqual(response.status_code, 201)
        
        # Verify task was created
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        task_id = data['task_id']
        
        task = Task.query.get(task_id)
        self.assertIsNotNone(task)
        self.assertEqual(task.description, 'Write documentation')
        self.assertEqual(task.domain, TaskDomain.WORK)
        self.assertEqual(task.estimated_duration, 90)
        
        # Verify project was created
        project = Project.query.filter_by(name='docs').first()
        self.assertIsNotNone(project)
        self.assertEqual(task.project_id, project.id)
    
    def test_parse_task_incomplete(self):
        """Test task parsing with missing required fields"""
        # Task text without duration
        task_text = "Incomplete task without duration #work"
        
        # Send parse request
        response = self.client.post('/todoist/parse',
                                data=json.dumps({'text': task_text}),
                                content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        
        # Verify response indicates missing fields
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'incomplete')
        self.assertIn('missing_fields', data)
        self.assertIn('estimated_duration', data['missing_fields'])

if __name__ == '__main__':
    unittest.main()