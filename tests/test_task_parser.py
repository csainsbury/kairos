# Tests for the Task Parser module

import unittest
import sys
import os
from datetime import datetime
import dateparser

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.task_parser import TaskParser
from app.models import TaskDomain

class TaskParserTestCase(unittest.TestCase):
    """Test case for the task parser"""
    
    def setUp(self):
        """Set up test environment"""
        self.parser = TaskParser()
    
    def test_domain_parsing(self):
        """Test domain tag extraction"""
        # Test default domain
        domain, text = self.parser.parse_domain("Task with no domain tag")
        self.assertEqual(domain, TaskDomain.WORK)
        self.assertEqual(text, "Task with no domain tag")
        
        # Test work domain
        domain, text = self.parser.parse_domain("Task with #work tag")
        self.assertEqual(domain, TaskDomain.WORK)
        self.assertEqual(text, "Task with tag")
        
        # Test life_admin domain
        domain, text = self.parser.parse_domain("Task with #life_admin tag")
        self.assertEqual(domain, TaskDomain.LIFE_ADMIN)
        self.assertEqual(text, "Task with tag")
        
        # Test general_life domain
        domain, text = self.parser.parse_domain("Task with #general_life tag")
        self.assertEqual(domain, TaskDomain.GENERAL_LIFE)
        self.assertEqual(text, "Task with tag")
        
        # Test case insensitivity
        domain, text = self.parser.parse_domain("Task with #WORK tag")
        self.assertEqual(domain, TaskDomain.WORK)
        self.assertEqual(text, "Task with tag")
    
    def test_project_parsing(self):
        """Test project extraction"""
        # No project
        project, text = self.parser.parse_project("Task with no project")
        self.assertIsNone(project)
        self.assertEqual(text, "Task with no project")
        
        # With project
        project, text = self.parser.parse_project("Task for @projectX")
        self.assertEqual(project, "projectX")
        self.assertEqual(text, "Task for")
        
        # Multiple words after project
        project, text = self.parser.parse_project("Task for @projectX with details")
        self.assertEqual(project, "projectX")
        self.assertEqual(text, "Task for with details")
    
    def test_duration_parsing(self):
        """Test duration extraction"""
        # No duration
        duration, text = self.parser.parse_duration("Task with no duration")
        self.assertIsNone(duration)
        self.assertEqual(text, "Task with no duration")
        
        # Minutes only
        duration, text = self.parser.parse_duration("Task [30m] with minutes")
        self.assertEqual(duration, 30)
        self.assertEqual(text, "Task with minutes")
        
        # Hours only
        duration, text = self.parser.parse_duration("Task [2h] with hours")
        self.assertEqual(duration, 120)
        self.assertEqual(text, "Task with hours")
        
        # Hours and minutes
        duration, text = self.parser.parse_duration("Task [1h30m] with mixed time")
        self.assertEqual(duration, 90)
        self.assertEqual(text, "Task with mixed time")
    
    def test_deadline_parsing(self):
        """Test deadline extraction"""
        # No deadline
        deadline, text = self.parser.parse_deadline("Task with no deadline")
        self.assertIsNone(deadline)
        self.assertEqual(text, "Task with no deadline")
        
        # Specific date
        deadline, text = self.parser.parse_deadline("Task due:2023-12-31")
        expected_date = dateparser.parse("2023-12-31")
        self.assertEqual(deadline.date(), expected_date.date())
        self.assertEqual(text, "Task")
        
        # Relative date
        deadline, text = self.parser.parse_deadline("Task deadline:tomorrow")
        tomorrow = dateparser.parse("tomorrow")
        self.assertEqual(deadline.date(), tomorrow.date())
        self.assertEqual(text, "Task")
        
        # Alternative syntax
        deadline, text = self.parser.parse_deadline("Task by:friday")
        friday = dateparser.parse("friday")
        self.assertEqual(deadline.date(), friday.date())
        self.assertEqual(text, "Task")
    
    def test_full_task_parsing(self):
        """Test complete task parsing"""
        # Full example
        task_data = self.parser.parse_task(
            "Complete project report #work @reports [2h] due:friday"
        )
        
        self.assertEqual(task_data['domain'], TaskDomain.WORK)
        self.assertEqual(task_data['project'], "reports")
        self.assertEqual(task_data['estimated_duration'], 120)
        self.assertIsNotNone(task_data['deadline'])
        self.assertEqual(task_data['description'], "Complete project report")
        
        # Default domain
        task_data = self.parser.parse_task(
            "Review code @coding [45m] due:tomorrow"
        )
        
        self.assertEqual(task_data['domain'], TaskDomain.WORK)  # Default
        self.assertEqual(task_data['project'], "coding")
        self.assertEqual(task_data['estimated_duration'], 45)
        self.assertIsNotNone(task_data['deadline'])
        self.assertEqual(task_data['description'], "Review code")
        
        # Life admin domain
        task_data = self.parser.parse_task(
            "Pay electric bill #life_admin [10m] due:next monday"
        )
        
        self.assertEqual(task_data['domain'], TaskDomain.LIFE_ADMIN)
        self.assertIsNone(task_data['project'])
        self.assertEqual(task_data['estimated_duration'], 10)
        self.assertIsNotNone(task_data['deadline'])
        self.assertEqual(task_data['description'], "Pay electric bill")
    
    def test_task_validation(self):
        """Test task validation"""
        # Valid task
        task_data = {
            'description': 'Valid task',
            'estimated_duration': 30,
            'domain': TaskDomain.WORK
        }
        missing = self.parser.validate_task(task_data)
        self.assertEqual(missing, [])
        
        # Missing description
        task_data = {
            'estimated_duration': 30,
            'domain': TaskDomain.WORK
        }
        missing = self.parser.validate_task(task_data)
        self.assertIn('description', missing)
        
        # Missing duration
        task_data = {
            'description': 'Task with no duration',
            'domain': TaskDomain.WORK
        }
        missing = self.parser.validate_task(task_data)
        self.assertIn('estimated_duration', missing)
        
        # Empty description
        task_data = {
            'description': '',
            'estimated_duration': 30,
            'domain': TaskDomain.WORK
        }
        missing = self.parser.validate_task(task_data)
        self.assertIn('description', missing)

if __name__ == '__main__':
    unittest.main()