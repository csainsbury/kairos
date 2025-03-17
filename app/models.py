# Database models for kAIros

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import enum

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

# Main data models will be defined here