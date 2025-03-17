# Unit tests for database models

import unittest
import os
import sys
import datetime
from datetime import timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import db, Project, Task, Subtask, Document, TaskLog, User, TaskStatus, TaskDomain

class ModelsTestCase(unittest.TestCase):
    """Test case for the database models"""
    
    def setUp(self):
        """Set up test environment"""
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
    
    def tearDown(self):
        """Clean up test environment"""
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
    
    def test_project_model(self):
        """Test Project model"""
        # Create a project
        project = Project(name="Test Project", domain=TaskDomain.WORK, description="Test description")
        db.session.add(project)
        db.session.commit()
        
        # Retrieve and verify
        saved_project = Project.query.first()
        self.assertEqual(saved_project.name, "Test Project")
        self.assertEqual(saved_project.domain, TaskDomain.WORK)
        self.assertEqual(saved_project.description, "Test description")
        self.assertIsNotNone(saved_project.created_at)
    
    def test_task_model(self):
        """Test Task model"""
        # Create a project first
        project = Project(name="Test Project", domain=TaskDomain.WORK)
        db.session.add(project)
        db.session.commit()
        
        # Create a task
        deadline = datetime.datetime.utcnow() + timedelta(days=7)
        task = Task(
            description="Test Task",
            deadline=deadline,
            estimated_duration=60,
            domain=TaskDomain.WORK,
            project_id=project.id
        )
        db.session.add(task)
        db.session.commit()
        
        # Retrieve and verify
        saved_task = Task.query.first()
        self.assertEqual(saved_task.description, "Test Task")
        self.assertEqual(saved_task.estimated_duration, 60)
        self.assertEqual(saved_task.domain, TaskDomain.WORK)
        self.assertEqual(saved_task.project_id, project.id)
        self.assertEqual(saved_task.status, TaskStatus.PENDING)
        self.assertFalse(saved_task.is_completed)
        
        # Test time_until_deadline property
        self.assertGreater(saved_task.time_until_deadline, 6.5 * 24)  # Should be approximately 7 days (in hours)
        
        # Test relationship with project
        self.assertEqual(saved_task.project.name, "Test Project")
    
    def test_subtask_model(self):
        """Test Subtask model"""
        # Create parent task first
        project = Project(name="Test Project", domain=TaskDomain.WORK)
        db.session.add(project)
        db.session.commit()
        
        task = Task(
            description="Parent Task",
            estimated_duration=120,
            domain=TaskDomain.WORK,
            project_id=project.id
        )
        db.session.add(task)
        db.session.commit()
        
        # Create subtask
        subtask = Subtask(
            description="Test Subtask",
            parent_task_id=task.id,
            estimated_duration=30
        )
        db.session.add(subtask)
        db.session.commit()
        
        # Retrieve and verify
        saved_subtask = Subtask.query.first()
        self.assertEqual(saved_subtask.description, "Test Subtask")
        self.assertEqual(saved_subtask.estimated_duration, 30)
        self.assertEqual(saved_subtask.parent_task_id, task.id)
        self.assertEqual(saved_subtask.status, TaskStatus.PENDING)
        
        # Test relationship with parent task
        self.assertEqual(saved_subtask.parent_task.description, "Parent Task")
    
    def test_task_completion(self):
        """Test task completion logic"""
        # Create a task
        task = Task(
            description="Test Task",
            estimated_duration=30,
            domain=TaskDomain.WORK
        )
        db.session.add(task)
        db.session.commit()
        
        # Complete the task
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.datetime.utcnow()
        db.session.commit()
        
        # Verify
        saved_task = Task.query.first()
        self.assertEqual(saved_task.status, TaskStatus.COMPLETED)
        self.assertTrue(saved_task.is_completed)
        self.assertIsNotNone(saved_task.completed_at)
    
    def test_document_model(self):
        """Test Document model"""
        # Create a project
        project = Project(name="Test Project", domain=TaskDomain.WORK)
        db.session.add(project)
        db.session.commit()
        
        # Create a document
        document = Document(
            filename="test_doc.pdf",
            file_path="/path/to/test_doc.pdf",
            file_type="application/pdf",
            project_id=project.id,
            summary="This is a test document summary"
        )
        db.session.add(document)
        db.session.commit()
        
        # Retrieve and verify
        saved_doc = Document.query.first()
        self.assertEqual(saved_doc.filename, "test_doc.pdf")
        self.assertEqual(saved_doc.file_type, "application/pdf")
        self.assertEqual(saved_doc.project_id, project.id)
        self.assertEqual(saved_doc.summary, "This is a test document summary")
        
        # Test relationship with project
        self.assertEqual(saved_doc.project.name, "Test Project")

if __name__ == '__main__':
    unittest.main()