# Task Input Parser for kAIros

import re
from datetime import datetime, timedelta
import dateparser
from app.utils import setup_logger
from app.models import TaskDomain

# Setup logger
logger = setup_logger(__name__)

class TaskParser:
    """Parser for natural language task inputs"""
    
    def __init__(self):
        # Domain tag patterns (e.g., #work, #life_admin, #general_life)
        self.domain_patterns = {
            r'#work\b': TaskDomain.WORK,
            r'#life_admin\b': TaskDomain.LIFE_ADMIN,
            r'#general_life\b': TaskDomain.GENERAL_LIFE,
        }
        
        # Project pattern (e.g., @project_name)
        self.project_pattern = r'@(\w+)'
        
        # Duration pattern (e.g., [30m], [1h], [1h30m])
        self.duration_patterns = [
            (r'\[(\d+)m\]', lambda m: int(m.group(1))),  # minutes
            (r'\[(\d+)h\]', lambda m: int(m.group(1)) * 60),  # hours to minutes
            (r'\[(\d+)h(\d+)m\]', lambda m: int(m.group(1)) * 60 + int(m.group(2)))  # hours and minutes
        ]
        
        # Deadline patterns (e.g., due:tomorrow, due:friday)
        self.deadline_patterns = [
            (r'due:(\S+)', lambda m: dateparser.parse(m.group(1))),
            (r'deadline:(\S+)', lambda m: dateparser.parse(m.group(1))),
            (r'by:(\S+)', lambda m: dateparser.parse(m.group(1)))
        ]
    
    def parse_domain(self, text):
        """Extract domain from task text
        
        Args:
            text: Task description text
            
        Returns:
            (TaskDomain, cleaned_text): Domain enum and text without domain tag
        """
        domain = TaskDomain.WORK  # Default to work domain
        cleaned_text = text
        
        for pattern, domain_enum in self.domain_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                domain = domain_enum
                # Remove the domain tag from the text
                cleaned_text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()
                break
        
        return domain, cleaned_text
    
    def parse_project(self, text):
        """Extract project from task text
        
        Args:
            text: Task description text
            
        Returns:
            (project_name, cleaned_text): Project name and text without project tag
        """
        project = None
        cleaned_text = text
        
        match = re.search(self.project_pattern, text)
        if match:
            project = match.group(1)
            # Remove the project tag from the text
            cleaned_text = re.sub(self.project_pattern, '', text).strip()
        
        return project, cleaned_text
    
    def parse_duration(self, text):
        """Extract estimated duration from task text
        
        Args:
            text: Task description text
            
        Returns:
            (duration_minutes, cleaned_text): Duration in minutes and text without duration tag
        """
        duration = None
        cleaned_text = text
        
        for pattern, extractor in self.duration_patterns:
            match = re.search(pattern, text)
            if match:
                duration = extractor(match)
                # Remove the duration tag from the text
                cleaned_text = re.sub(pattern, '', text).strip()
                break
        
        return duration, cleaned_text
    
    def parse_deadline(self, text):
        """Extract deadline from task text
        
        Args:
            text: Task description text
            
        Returns:
            (deadline, cleaned_text): Deadline datetime and text without deadline tag
        """
        deadline = None
        cleaned_text = text
        
        for pattern, extractor in self.deadline_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    date_text = match.group(1)
                    deadline = extractor(match)
                    if deadline is None:
                        logger.warning(f"Could not parse deadline from '{date_text}'")
                    else:
                        # Remove the deadline tag from the text
                        cleaned_text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()
                        break
                except Exception as e:
                    logger.error(f"Error parsing deadline: {str(e)}")
        
        return deadline, cleaned_text
    
    def parse_task(self, text):
        """Parse task information from text
        
        Args:
            text: Natural language task description
        
        Returns:
            Dictionary with parsed task attributes
        """
        # Ensure we have some text to work with
        if not text or not text.strip():
            return None
        
        # Parse all components
        domain, text_without_domain = self.parse_domain(text)
        project, text_without_project = self.parse_project(text_without_domain)
        duration, text_without_duration = self.parse_duration(text_without_project)
        deadline, text_without_deadline = self.parse_deadline(text_without_duration)
        
        # The remaining text is the task description
        description = text_without_deadline.strip()
        
        # Log the parsed task
        logger.info(f"Parsed task: domain={domain.value}, " +
                    f"project={project}, duration={duration}, " +
                    f"deadline={deadline}, description={description}")
        
        # Return parsed data
        return {
            'domain': domain,
            'project': project,
            'estimated_duration': duration,
            'deadline': deadline,
            'description': description,
            'raw_text': text
        }
    
    def validate_task(self, task_data):
        """Validate parsed task data, returning missing fields
        
        Args:
            task_data: Dictionary with parsed task attributes
            
        Returns:
            List of missing required fields, empty if all required fields are present
        """
        missing_fields = []
        
        # Description is required
        if not task_data.get('description'):
            missing_fields.append('description')
        
        # Duration is required
        if task_data.get('estimated_duration') is None:
            missing_fields.append('estimated_duration')
        
        # Domain is auto-defaulted, so will never be missing
        
        return missing_fields