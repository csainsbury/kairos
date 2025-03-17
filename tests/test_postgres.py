# Tests for PostgreSQL compatibility
# Note: This test requires a running PostgreSQL database

import unittest
import os
import sys
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import db, Project, Task, TaskDomain
from config import ProductionConfig

# Skip these tests if no PostgreSQL connection is available
try:
    # Try to connect to PostgreSQL - modify connection string if needed for CI/CD
    engine = create_engine(os.environ.get(
        'TEST_POSTGRES_URL', 
        'postgresql://postgres:postgres@localhost:5432/kairos_test'
    ))
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))
    POSTGRES_AVAILABLE = True
except OperationalError:
    POSTGRES_AVAILABLE = False

@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL is not available")
class PostgresTestCase(unittest.TestCase):
    """Test case for PostgreSQL compatibility"""

    def setUp(self):
        """Set up test environment"""
        # Override config to use test PostgreSQL database
        class TestProductionConfig(ProductionConfig):
            SQLALCHEMY_DATABASE_URI = os.environ.get(
                'TEST_POSTGRES_URL', 
                'postgresql://postgres:postgres@localhost:5432/kairos_test'
            )
            TESTING = True
        
        self.app = create_app('production')
        self.app.config.from_object(TestProductionConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        
        # Clear any existing data
        db.drop_all()
        db.create_all()
    
    def tearDown(self):
        """Clean up test environment"""
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
    
    def test_postgresql_connection(self):
        """Test basic PostgreSQL connection and operations"""
        # Create a project
        project = Project(name="Postgres Test Project", domain=TaskDomain.WORK)
        db.session.add(project)
        db.session.commit()
        
        # Verify project was saved
        saved_project = Project.query.first()
        self.assertEqual(saved_project.name, "Postgres Test Project")
        
        # Test task creation
        task = Task(
            description="Postgres Test Task",
            estimated_duration=45,
            domain=TaskDomain.WORK,
            project_id=saved_project.id
        )
        db.session.add(task)
        db.session.commit()
        
        # Verify task was saved
        saved_task = Task.query.first()
        self.assertEqual(saved_task.description, "Postgres Test Task")
        
        # Test relationship
        self.assertEqual(saved_task.project.name, "Postgres Test Project")
        
        # Test enum handling in PostgreSQL
        self.assertEqual(saved_task.domain.value, "work")
    
    def test_postgres_transaction(self):
        """Test PostgreSQL transactions"""
        try:
            # Start transaction
            project1 = Project(name="Project One", domain=TaskDomain.WORK)
            db.session.add(project1)
            db.session.flush()
            
            # Create task with foreign key to project
            task1 = Task(
                description="Task One",
                estimated_duration=30,
                domain=TaskDomain.WORK,
                project_id=project1.id
            )
            db.session.add(task1)
            
            # This should fail - can't have null domain
            task2 = Task(
                description="Task Two",
                estimated_duration=60,
                domain=None,  # This should cause an error
                project_id=project1.id
            )
            db.session.add(task2)
            
            # Commit should fail
            db.session.commit()
            self.fail("Expected database constraint error")
        except:
            # Expected error - roll back
            db.session.rollback()
        
        # Verify transaction was rolled back - no projects should exist
        self.assertEqual(Project.query.count(), 0)
        self.assertEqual(Task.query.count(), 0)

if __name__ == '__main__':
    unittest.main()