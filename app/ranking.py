# Task Ranking Engine for kAIros

from datetime import datetime, timedelta
import os
from app.utils import setup_logger

# Setup module logger
logger = setup_logger(__name__)

# Default weights for domains from environment or defaults
def get_domain_weights():
    """Get domain weights from environment or use defaults"""
    weights_str = os.environ.get('DEFAULT_DOMAIN_WEIGHTS', 'work:1.0,life_admin:0.8,general_life:0.6')
    weights = {}
    
    try:
        # Parse weights string in format 'domain:weight,domain:weight'
        for item in weights_str.split(','):
            domain, weight = item.split(':')
            weights[domain] = float(weight)
        
        return weights
    except Exception as e:
        logger.error(f"Error parsing domain weights: {str(e)}")
        # Fall back to defaults
        return {
            'work': 1.0,
            'life_admin': 0.8,
            'general_life': 0.6
        }

def calculate_deadline_score(deadline):
    """Calculate score component based on deadline urgency
    
    Args:
        deadline: Datetime object of the task deadline
        
    Returns:
        Float score value (higher for more urgent deadlines)
    """
    # Placeholder - Will be implemented in Task 6
    now = datetime.now()
    
    if deadline < now:
        # Past due - highest urgency
        return 10.0
    
    # Calculate days until deadline
    days_until_deadline = (deadline - now).days
    
    if days_until_deadline == 0:
        # Due today
        return 9.0
    elif days_until_deadline == 1:
        # Due tomorrow
        return 8.0
    elif days_until_deadline < 7:
        # Due this week
        return 7.0 - (days_until_deadline / 10.0)
    elif days_until_deadline < 30:
        # Due this month
        return 5.0 - (days_until_deadline / 30.0)
    else:
        # Due later
        return max(1.0, 3.0 - (days_until_deadline / 100.0))

def calculate_duration_score(estimated_minutes):
    """Calculate score component based on estimated duration
    
    Args:
        estimated_minutes: Estimated task duration in minutes
        
    Returns:
        Float score value (higher for shorter tasks)
    """
    # Placeholder - Will be implemented in Task 6
    # Higher score for shorter tasks, with diminishing returns
    if estimated_minutes <= 5:
        return 5.0  # Quick wins
    elif estimated_minutes <= 15:
        return 4.5
    elif estimated_minutes <= 30:
        return 4.0
    elif estimated_minutes <= 60:
        return 3.5
    elif estimated_minutes <= 120:
        return 3.0
    else:
        return max(1.0, 5.0 - (estimated_minutes / 120.0))

def rank_tasks(tasks, available_time=None):
    """Rank tasks by calculated priority score
    
    Args:
        tasks: List of task objects
        available_time: Optional time constraint in minutes
        
    Returns:
        List of tasks sorted by ranking score
    """
    # Placeholder - Will be implemented in Task 6
    logger.info(f"Ranking {len(tasks)} tasks with {available_time} minutes available")
    
    domain_weights = get_domain_weights()
    ranked_tasks = []
    
    for task in tasks:
        # Calculate component scores
        deadline_score = calculate_deadline_score(task.deadline)
        duration_score = calculate_duration_score(task.estimated_duration)
        domain_score = domain_weights.get(task.domain, 0.5)  # Default if domain unknown
        
        # Calculate total score
        total_score = (deadline_score * 0.6) + (duration_score * 0.3) + (domain_score * 0.1)
        
        ranked_tasks.append({
            'task': task,
            'score': total_score
        })
    
    # Sort by score (highest first)
    ranked_tasks.sort(key=lambda x: x['score'], reverse=True)
    
    # If time available is specified, filter for tasks that fit
    if available_time is not None:
        filtered_tasks = []
        remaining_time = available_time
        
        for task_entry in ranked_tasks:
            task = task_entry['task']
            if task.estimated_duration <= remaining_time:
                filtered_tasks.append(task_entry)
                remaining_time -= task.estimated_duration
        
        return [t['task'] for t in filtered_tasks]
    
    # Return sorted task objects
    return [t['task'] for t in ranked_tasks]