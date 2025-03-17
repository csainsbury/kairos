# Database models for kAIros

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Enum, Text, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid

db = SQLAlchemy()

# Enums for various model fields
class TaskStatus(enum.Enum):
    PENDING = 'pending'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'

class TaskDomain(enum.Enum):
    WORK = 'work'
    LIFE_ADMIN = 'life_admin'
    GENERAL_LIFE = 'general_life'

# Helper function to generate unique IDs
def generate_uuid():
    return str(uuid.uuid4())

# Project model
class Project(db.Model):
    __tablename__ = 'projects'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    domain = Column(Enum(TaskDomain), nullable=False, default=TaskDomain.WORK)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tasks = relationship('Task', back_populates='project', cascade='all, delete-orphan')
    documents = relationship('Document', back_populates='project', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f"<Project {self.name}>"

# Task model
class Task(db.Model):
    __tablename__ = 'tasks'
    
    id = Column(Integer, primary_key=True)
    external_id = Column(String(64), nullable=True, unique=True)  # For Todoist integration
    description = Column(String(255), nullable=False)
    deadline = Column(DateTime, nullable=True)
    estimated_duration = Column(Integer, nullable=False)  # Minutes
    domain = Column(Enum(TaskDomain), nullable=False)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=True)
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    urgency_override = Column(Float, nullable=True)
    
    # Relationships
    project = relationship('Project', back_populates='tasks')
    subtasks = relationship('Subtask', back_populates='parent_task', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f"<Task {self.description[:20]}...>"
    
    @property
    def is_completed(self):
        return self.status == TaskStatus.COMPLETED
    
    @property
    def time_until_deadline(self):
        if not self.deadline:
            return None
        return (self.deadline - datetime.utcnow()).total_seconds() / 3600  # Hours

# Subtask model
class Subtask(db.Model):
    __tablename__ = 'subtasks'
    
    id = Column(Integer, primary_key=True)
    description = Column(String(255), nullable=False)
    parent_task_id = Column(Integer, ForeignKey('tasks.id'), nullable=False)
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.PENDING)
    estimated_duration = Column(Integer, nullable=False)  # Minutes
    actual_duration = Column(Integer, nullable=True)  # Minutes, filled upon completion
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    parent_task = relationship('Task', back_populates='subtasks')
    
    def __repr__(self):
        return f"<Subtask {self.description[:20]}...>"

# Document model
class Document(db.Model):
    __tablename__ = 'documents'
    
    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_type = Column(String(50), nullable=False)  # MIME type
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False)
    summary = Column(Text, nullable=True)  # LLM-generated summary
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    project = relationship('Project', back_populates='documents')
    
    def __repr__(self):
        return f"<Document {self.filename}>"

# Log model for task completion and metrics
class TaskLog(db.Model):
    __tablename__ = 'task_logs'
    
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('tasks.id'), nullable=True)
    subtask_id = Column(Integer, ForeignKey('subtasks.id'), nullable=True)
    description = Column(String(255), nullable=False)
    domain = Column(Enum(TaskDomain), nullable=False)
    estimated_duration = Column(Integer, nullable=False)  # Minutes
    actual_duration = Column(Integer, nullable=True)  # Minutes
    completed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<TaskLog {self.description[:20]}... completed at {self.completed_at}>"

# User model (for future OAuth support)
class User(db.Model):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=True)  # For non-OAuth authentication
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<User {self.username}>"