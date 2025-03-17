# Task Ranking Engine for kAIros

from datetime import datetime, timedelta
import os
from app.utils import setup_logger
from app.models import Task, TaskStatus, TaskDomain
from app.calendar import get_calendar_events
from typing import List, Dict, Any, Optional, Tuple
import math

# Setup module logger
logger = setup_logger(__name__)

# Default weights for domains from environment or defaults
def get_domain_weights() -> Dict[str, float]:
    """Get domain weights from environment or use defaults
    
    Returns:
        Dictionary mapping domain names to weight values
    """
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

def calculate_deadline_score(deadline: Optional[datetime]) -> float:
    """Calculate score component based on deadline urgency
    
    The deadline score follows a logarithmic urgency curve, where:
    - Overdue tasks have highest urgency (10.0)
    - Due today tasks have very high urgency (9.0)
    - Score decreases logarithmically with time until deadline
    - Tasks without deadlines get a moderate score (5.0)
    
    Args:
        deadline: Datetime object of the task deadline or None
        
    Returns:
        Float score value (higher for more urgent deadlines)
    """
    # If no deadline, return a moderate default score
    if deadline is None:
        return 5.0
    
    now = datetime.utcnow()
    
    if deadline < now:
        # Past due - highest urgency
        return 10.0
    
    # Calculate hours until deadline for finer granularity
    hours_until_deadline = (deadline - now).total_seconds() / 3600
    
    if hours_until_deadline <= 24:
        # Due within 24 hours - high urgency decreasing from 9.0
        return max(7.0, 9.0 - (hours_until_deadline / 24.0) * 2.0)
    elif hours_until_deadline <= 72:
        # Due within 3 days - high to medium urgency
        return max(6.0, 8.0 - (hours_until_deadline / 72.0) * 2.0)
    elif hours_until_deadline <= 168:  # 7 days
        # Due within a week
        return max(4.0, 7.0 - (hours_until_deadline / 168.0) * 3.0)
    elif hours_until_deadline <= 720:  # 30 days
        # Due within a month
        days = hours_until_deadline / 24.0
        return max(2.0, 5.0 - math.log10(days) * 1.5)
    else:
        # Due in more than a month - logarithmic decay
        days = hours_until_deadline / 24.0
        return max(1.0, 3.0 - math.log10(days) * 0.5)

def calculate_duration_score(estimated_minutes: int) -> float:
    """Calculate score component based on estimated duration
    
    Score is higher for shorter tasks, with a custom curve that:
    - Heavily prioritizes very quick tasks (5-15 minutes)
    - Gives diminishing returns as duration increases
    - Penalizes extremely long tasks
    
    Args:
        estimated_minutes: Estimated task duration in minutes
        
    Returns:
        Float score value (higher for shorter tasks)
    """
    # Edge case handling
    if estimated_minutes <= 0:
        return 5.0  # Assume very quick
    
    # Quick wins (very short tasks)
    if estimated_minutes <= 5:
        return 5.0
    elif estimated_minutes <= 15:
        return 4.7
    elif estimated_minutes <= 30:
        return 4.3
    elif estimated_minutes <= 45:
        return 4.0
    elif estimated_minutes <= 60:
        return 3.7  # 1 hour
    elif estimated_minutes <= 90:
        return 3.3
    elif estimated_minutes <= 120:
        return 3.0  # 2 hours
    elif estimated_minutes <= 180:
        return 2.7  # 3 hours
    elif estimated_minutes <= 240:
        return 2.3  # 4 hours
    elif estimated_minutes <= 360:
        return 2.0  # 6 hours (typical workday)
    else:
        # For very long tasks, score decreases logarithmically
        # but never below 1.0
        return max(1.0, 5.0 - math.log10(estimated_minutes/30) * 2.0)

def calculate_domain_priority_score(domain: TaskDomain, domain_weights: Dict[str, float],
                                   time_of_day: Optional[datetime] = None) -> float:
    """Calculate score component based on task domain and time of day
    
    Different domains can have different priorities depending on the time of day.
    For example, work tasks might be prioritized during work hours.
    
    Args:
        domain: Task domain enum
        domain_weights: Dictionary of domain weights
        time_of_day: Optional datetime to consider for time-based weighting
        
    Returns:
        Float score value for domain priority
    """
    if time_of_day is None:
        time_of_day = datetime.utcnow()
    
    # Get base weight for the domain
    domain_value = domain.value if hasattr(domain, 'value') else str(domain)
    base_weight = domain_weights.get(domain_value, 0.5)
    
    # Adjust based on time of day
    hour = time_of_day.hour
    weekday = time_of_day.weekday()  # 0-6, Monday is 0
    
    # Boost work tasks during typical work hours on weekdays
    if domain_value == 'work' and weekday < 5 and 9 <= hour <= 17:
        return base_weight * 1.5
    
    # Boost life_admin tasks during evening hours or weekends
    elif domain_value == 'life_admin' and (hour >= 17 or hour <= 8 or weekday >= 5):
        return base_weight * 1.3
    
    # Boost general_life tasks during evening and weekends
    elif domain_value == 'general_life' and (hour >= 18 or weekday >= 5):
        return base_weight * 1.2
    
    return base_weight

def calculate_context_switch_score(current_task: Optional[Task], new_task: Task) -> float:
    """Calculate score bonus/penalty for context switching between tasks
    
    Tasks in the same project or domain get a bonus to minimize context switching.
    
    Args:
        current_task: Current task (or None if no current task)
        new_task: Potential next task
        
    Returns:
        Float score adjustment (positive for bonus, negative for penalty)
    """
    if current_task is None:
        return 0.0  # No context switch consideration if no current task
    
    # Same project bonus (strongest)
    if current_task.project_id and current_task.project_id == new_task.project_id:
        return 1.0
    
    # Same domain bonus (moderate)
    if current_task.domain == new_task.domain:
        return 0.5
    
    # Different domain and project (slight penalty)
    return -0.2

def get_available_time_slots(start_time: datetime, end_time: datetime) -> List[Tuple[datetime, datetime]]:
    """Find available time slots by checking calendar events
    
    Args:
        start_time: Start of the time period to check
        end_time: End of the time period to check
        
    Returns:
        List of tuples with start and end times for available slots
    """
    try:
        # Get calendar events for the specified period
        events = get_calendar_events(start_time, end_time)
        
        # If no events or calendar not authenticated, consider whole period available
        if not events:
            return [(start_time, end_time)]
        
        # Sort events by start time
        sorted_events = sorted(events, key=lambda e: e['start'])
        
        # Find gaps between events
        available_slots = []
        current_time = start_time
        
        for event in sorted_events:
            event_start = datetime.fromisoformat(event['start'].replace('Z', '+00:00'))
            event_end = datetime.fromisoformat(event['end'].replace('Z', '+00:00'))
            
            # Adjust event times if they extend beyond our search period
            if event_start < start_time:
                event_start = start_time
            if event_end > end_time:
                event_end = end_time
            
            # If there's a gap before this event, add it
            if current_time < event_start:
                available_slots.append((current_time, event_start))
            
            # Move current time to end of this event
            current_time = max(current_time, event_end)
        
        # Add final slot if there's time after the last event
        if current_time < end_time:
            available_slots.append((current_time, end_time))
        
        return available_slots
        
    except Exception as e:
        logger.error(f"Error getting available time slots: {str(e)}")
        # If there's an error, return the whole period as available
        return [(start_time, end_time)]

def get_total_available_minutes(start_time: datetime, end_time: datetime) -> int:
    """Calculate total available minutes within time period
    
    Args:
        start_time: Start of the time period
        end_time: End of the time period
        
    Returns:
        Total available minutes
    """
    slots = get_available_time_slots(start_time, end_time)
    total_minutes = 0
    
    for slot_start, slot_end in slots:
        total_minutes += int((slot_end - slot_start).total_seconds() / 60)
    
    return total_minutes

def rank_tasks(tasks: List[Task], available_time: Optional[int] = None,
              current_task: Optional[Task] = None,
              time_period: Optional[Tuple[datetime, datetime]] = None) -> List[Task]:
    """Rank tasks by calculated priority score
    
    This ranking algorithm takes multiple factors into account:
    - Deadline urgency
    - Task duration
    - Domain priority
    - Context switching
    - Available time
    
    Args:
        tasks: List of task objects
        available_time: Optional manually specified available time in minutes
        current_task: Optional currently active task (for context switching)
        time_period: Optional tuple of (start_time, end_time) to check calendar
        
    Returns:
        List of tasks sorted by ranking score
    """
    if not tasks:
        return []
    
    logger.info(f"Ranking {len(tasks)} tasks")
    
    # Get available time either from parameter or by checking calendar
    actual_available_time = available_time
    if actual_available_time is None and time_period:
        actual_available_time = get_total_available_minutes(time_period[0], time_period[1])
        logger.info(f"Detected {actual_available_time} available minutes from calendar")
    
    # Get domain weights
    domain_weights = get_domain_weights()
    time_now = datetime.utcnow()
    
    # Calculate scores for each task
    ranked_tasks = []
    for task in tasks:
        # Skip completed tasks
        if task.status == TaskStatus.COMPLETED:
            continue
        
        # Calculate component scores
        deadline_score = calculate_deadline_score(task.deadline)
        duration_score = calculate_duration_score(task.estimated_duration)
        domain_score = calculate_domain_priority_score(task.domain, domain_weights, time_now)
        context_score = calculate_context_switch_score(current_task, task)
        
        # Apply urgency override if present
        urgency_modifier = 0
        if task.urgency_override is not None:
            urgency_modifier = task.urgency_override
        
        # Calculate total score with weighted components
        # Deadline is most important, followed by duration and domain
        total_score = (
            (deadline_score * 0.5) +
            (duration_score * 0.25) +
            (domain_score * 0.15) +
            (context_score * 0.1) +
            urgency_modifier
        )
        
        ranked_tasks.append({
            'task': task,
            'score': total_score,
            'deadline_score': deadline_score,
            'duration_score': duration_score,
            'domain_score': domain_score,
            'context_score': context_score
        })
    
    # Sort by score (highest first)
    ranked_tasks.sort(key=lambda x: x['score'], reverse=True)
    
    # If time available is specified, optimize for tasks that fit
    if actual_available_time is not None:
        # Try to optimize task selection within available time
        # using a greedy algorithm with preprocessing
        
        # First sort by score-to-duration ratio (value per minute)
        value_sorted = sorted(
            ranked_tasks, 
            key=lambda x: x['score'] / max(1, x['task'].estimated_duration),
            reverse=True
        )
        
        # Then use dynamic programming approach for knapsack problem
        selected_tasks = knapsack_task_selection(value_sorted, actual_available_time)
        return selected_tasks
    
    # Return sorted task objects
    return [t['task'] for t in ranked_tasks]

def knapsack_task_selection(ranked_tasks: List[Dict[str, Any]], available_time: int) -> List[Task]:
    """Select optimal tasks to fit within available time using knapsack approach
    
    Args:
        ranked_tasks: List of task dicts with score and task object
        available_time: Available time in minutes
        
    Returns:
        List of selected tasks
    """
    # Special cases
    if not ranked_tasks:
        return []
    if available_time <= 0:
        return []
    
    # Create a table of max values
    n = len(ranked_tasks)
    dp = [[0 for _ in range(available_time + 1)] for _ in range(n + 1)]
    
    # Fill the table
    for i in range(1, n + 1):
        for w in range(1, available_time + 1):
            task = ranked_tasks[i-1]['task']
            duration = task.estimated_duration
            value = ranked_tasks[i-1]['score']
            
            if duration <= w:
                dp[i][w] = max(dp[i-1][w], dp[i-1][w-duration] + value)
            else:
                dp[i][w] = dp[i-1][w]
    
    # Backtrack to find the selected items
    selected_indices = []
    w = available_time
    for i in range(n, 0, -1):
        if dp[i][w] != dp[i-1][w]:
            selected_indices.append(i-1)
            w -= ranked_tasks[i-1]['task'].estimated_duration
    
    # Reverse to get tasks in score order
    selected_indices.reverse()
    return [ranked_tasks[i]['task'] for i in selected_indices]

def get_ranked_tasks_by_domain(tasks: List[Task], domain: TaskDomain, 
                              available_time: Optional[int] = None,
                              current_task: Optional[Task] = None) -> List[Task]:
    """Get ranked tasks filtered by domain
    
    Args:
        tasks: List of task objects
        domain: Domain to filter for
        available_time: Optional time constraint in minutes
        current_task: Optional currently active task
        
    Returns:
        List of tasks in the specified domain, ranked by priority
    """
    # Filter for the specified domain and not completed
    domain_tasks = [t for t in tasks if t.domain == domain and t.status != TaskStatus.COMPLETED]
    
    # Rank the domain-specific tasks
    return rank_tasks(domain_tasks, available_time, current_task)

def recommend_next_task(tasks: List[Task], available_time: Optional[int] = None,
                       current_task: Optional[Task] = None) -> Optional[Task]:
    """Recommend a single next task based on ranking
    
    Args:
        tasks: List of task objects
        available_time: Optional time constraint in minutes
        current_task: Optional currently active task
        
    Returns:
        Single highest ranked task that fits in available time
    """
    ranked = rank_tasks(tasks, available_time, current_task)
    return ranked[0] if ranked else None