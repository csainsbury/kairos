import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.models import TaskDomain, Task, TaskStatus
from app.ranking import (
    calculate_deadline_score,
    calculate_duration_score,
    calculate_domain_priority_score,
    calculate_context_switch_score,
    rank_tasks,
    get_domain_weights,
    knapsack_task_selection,
    get_available_time_slots,
    get_total_available_minutes,
    recommend_next_task,
    get_ranked_tasks_by_domain
)

class TestDeadlineScore:
    """Tests for the deadline score calculation function."""
    
    def test_past_deadline(self):
        """Test that past deadlines get highest score."""
        past_deadline = datetime.utcnow() - timedelta(days=1)
        score = calculate_deadline_score(past_deadline)
        assert score == 10.0
    
    def test_today_deadline(self):
        """Test that deadlines today get very high score."""
        today_deadline = datetime.utcnow() + timedelta(hours=5)
        score = calculate_deadline_score(today_deadline)
        # Score should be between 7 and 9 for a deadline today
        assert 7.0 <= score <= 9.0
    
    def test_week_deadline(self):
        """Test that deadlines within a week get moderate score."""
        week_deadline = datetime.utcnow() + timedelta(days=5)
        score = calculate_deadline_score(week_deadline)
        # Score should be moderate for a deadline this week
        assert 4.0 <= score <= 7.0
    
    def test_month_deadline(self):
        """Test that deadlines within a month get lower score."""
        month_deadline = datetime.utcnow() + timedelta(days=20)
        score = calculate_deadline_score(month_deadline)
        # Score should be lower for a deadline within a month
        assert 2.0 <= score <= 5.0
    
    def test_far_deadline(self):
        """Test that far future deadlines get lowest score."""
        far_deadline = datetime.utcnow() + timedelta(days=100)
        score = calculate_deadline_score(far_deadline)
        # Score should be low for a far deadline
        assert 1.0 <= score <= 3.0
    
    def test_none_deadline(self):
        """Test that None deadlines get a moderate score."""
        score = calculate_deadline_score(None)
        assert score == 5.0

class TestDurationScore:
    """Tests for the duration score calculation function."""
    
    def test_very_short_task(self):
        """Test that very short tasks get highest score."""
        score = calculate_duration_score(5)
        assert score == 5.0
    
    def test_short_task(self):
        """Test that short tasks get high score."""
        score = calculate_duration_score(15)
        assert 4.5 <= score <= 5.0
    
    def test_medium_task(self):
        """Test that medium tasks get moderate score."""
        score = calculate_duration_score(60)
        assert 3.5 <= score <= 4.0
    
    def test_long_task(self):
        """Test that long tasks get lower score."""
        score = calculate_duration_score(180)
        assert 2.5 <= score <= 3.0
    
    def test_very_long_task(self):
        """Test that very long tasks get lowest score."""
        score = calculate_duration_score(480)
        assert 1.0 <= score <= 2.0
    
    def test_zero_duration(self):
        """Test that zero duration gets highest score."""
        score = calculate_duration_score(0)
        assert score == 5.0
    
    def test_negative_duration(self):
        """Test that negative duration is handled."""
        score = calculate_duration_score(-10)
        assert score == 5.0  # Should be treated like a very quick task

class TestDomainPriorityScore:
    """Tests for the domain priority score calculation function."""
    
    @patch('app.ranking.get_domain_weights')
    def test_work_domain_weekday(self, mock_get_weights):
        """Test that work domain gets boost during work hours."""
        mock_get_weights.return_value = {'work': 1.0, 'life_admin': 0.8, 'general_life': 0.6}
        
        # Monday at 10 AM
        monday_morning = datetime(2023, 5, 1, 10, 0)  # A Monday
        score = calculate_domain_priority_score(TaskDomain.WORK, mock_get_weights.return_value, monday_morning)
        
        # Should be boosted during work hours
        assert score > 1.0
    
    @patch('app.ranking.get_domain_weights')
    def test_life_admin_evening(self, mock_get_weights):
        """Test that life_admin gets boost during evening hours."""
        mock_get_weights.return_value = {'work': 1.0, 'life_admin': 0.8, 'general_life': 0.6}
        
        # Weekday evening
        weekday_evening = datetime(2023, 5, 1, 19, 0)  # Monday 7 PM
        score = calculate_domain_priority_score(TaskDomain.LIFE_ADMIN, mock_get_weights.return_value, weekday_evening)
        
        # Should be boosted during evening hours
        assert score > 0.8
    
    @patch('app.ranking.get_domain_weights')
    def test_general_life_weekend(self, mock_get_weights):
        """Test that general_life gets boost during weekend."""
        mock_get_weights.return_value = {'work': 1.0, 'life_admin': 0.8, 'general_life': 0.6}
        
        # Weekend
        weekend = datetime(2023, 5, 6, 12, 0)  # A Saturday
        score = calculate_domain_priority_score(TaskDomain.GENERAL_LIFE, mock_get_weights.return_value, weekend)
        
        # Should be boosted during weekend
        assert score > 0.6
    
    @patch('app.ranking.get_domain_weights')
    def test_unknown_domain(self, mock_get_weights):
        """Test handling of unknown domain."""
        mock_get_weights.return_value = {'work': 1.0, 'life_admin': 0.8, 'general_life': 0.6}
        
        # Create a mock domain that's not in the weights
        class MockDomain:
            value = 'unknown'
        
        score = calculate_domain_priority_score(MockDomain(), mock_get_weights.return_value)
        
        # Should use default for unknown domain
        assert score == 0.5

class TestContextSwitchScore:
    """Tests for the context switch score calculation function."""
    
    def test_same_project(self):
        """Test that same project tasks get highest bonus."""
        current_task = MagicMock(spec=Task)
        current_task.project_id = 1
        current_task.domain = TaskDomain.WORK
        
        new_task = MagicMock(spec=Task)
        new_task.project_id = 1
        new_task.domain = TaskDomain.WORK
        
        score = calculate_context_switch_score(current_task, new_task)
        assert score == 1.0
    
    def test_same_domain_different_project(self):
        """Test that same domain but different project tasks get moderate bonus."""
        current_task = MagicMock(spec=Task)
        current_task.project_id = 1
        current_task.domain = TaskDomain.WORK
        
        new_task = MagicMock(spec=Task)
        new_task.project_id = 2
        new_task.domain = TaskDomain.WORK
        
        score = calculate_context_switch_score(current_task, new_task)
        assert score == 0.5
    
    def test_different_domain_and_project(self):
        """Test that different domain and project tasks get penalty."""
        current_task = MagicMock(spec=Task)
        current_task.project_id = 1
        current_task.domain = TaskDomain.WORK
        
        new_task = MagicMock(spec=Task)
        new_task.project_id = 2
        new_task.domain = TaskDomain.LIFE_ADMIN
        
        score = calculate_context_switch_score(current_task, new_task)
        assert score < 0
    
    def test_no_current_task(self):
        """Test that no context switch score is applied when there's no current task."""
        new_task = MagicMock(spec=Task)
        new_task.project_id = 1
        new_task.domain = TaskDomain.WORK
        
        score = calculate_context_switch_score(None, new_task)
        assert score == 0.0

class TestGetAvailableTimeSlots:
    """Tests for the available time slots calculation function."""
    
    @patch('app.ranking.get_calendar_events')
    def test_no_events(self, mock_get_events):
        """Test that entire period is available when there are no events."""
        mock_get_events.return_value = []
        
        start_time = datetime(2023, 5, 1, 9, 0)
        end_time = datetime(2023, 5, 1, 17, 0)
        slots = get_available_time_slots(start_time, end_time)
        
        assert len(slots) == 1
        assert slots[0] == (start_time, end_time)
    
    @patch('app.ranking.get_calendar_events')
    def test_one_event_middle(self, mock_get_events):
        """Test that correct slots are found with one event in the middle."""
        mock_get_events.return_value = [
            {
                'id': 'event1',
                'start': '2023-05-01T12:00:00Z',
                'end': '2023-05-01T13:00:00Z'
            }
        ]
        
        start_time = datetime(2023, 5, 1, 9, 0)
        end_time = datetime(2023, 5, 1, 17, 0)
        slots = get_available_time_slots(start_time, end_time)
        
        assert len(slots) == 2
        assert slots[0][0] == start_time
        assert slots[0][1].hour == 12
        assert slots[1][0].hour == 13
        assert slots[1][1] == end_time
    
    @patch('app.ranking.get_calendar_events')
    def test_multiple_events(self, mock_get_events):
        """Test that correct slots are found with multiple events."""
        mock_get_events.return_value = [
            {
                'id': 'event1',
                'start': '2023-05-01T10:00:00Z',
                'end': '2023-05-01T11:00:00Z'
            },
            {
                'id': 'event2',
                'start': '2023-05-01T13:00:00Z',
                'end': '2023-05-01T14:30:00Z'
            }
        ]
        
        start_time = datetime(2023, 5, 1, 9, 0)
        end_time = datetime(2023, 5, 1, 17, 0)
        slots = get_available_time_slots(start_time, end_time)
        
        assert len(slots) == 3
    
    @patch('app.ranking.get_calendar_events')
    def test_overlapping_events(self, mock_get_events):
        """Test that overlapping events are handled correctly."""
        mock_get_events.return_value = [
            {
                'id': 'event1',
                'start': '2023-05-01T10:00:00Z',
                'end': '2023-05-01T12:00:00Z'
            },
            {
                'id': 'event2',
                'start': '2023-05-01T11:00:00Z',
                'end': '2023-05-01T13:00:00Z'
            }
        ]
        
        start_time = datetime(2023, 5, 1, 9, 0)
        end_time = datetime(2023, 5, 1, 17, 0)
        slots = get_available_time_slots(start_time, end_time)
        
        # Should have 2 slots (before first event and after last event)
        assert len(slots) == 2
    
    @patch('app.ranking.get_calendar_events')
    def test_error_handling(self, mock_get_events):
        """Test that errors in getting calendar events are handled gracefully."""
        mock_get_events.side_effect = Exception("Calendar API error")
        
        start_time = datetime(2023, 5, 1, 9, 0)
        end_time = datetime(2023, 5, 1, 17, 0)
        slots = get_available_time_slots(start_time, end_time)
        
        # Should return whole period as available on error
        assert len(slots) == 1
        assert slots[0] == (start_time, end_time)

class TestGetTotalAvailableMinutes:
    """Tests for the total available minutes calculation function."""
    
    @patch('app.ranking.get_available_time_slots')
    def test_single_slot(self, mock_get_slots):
        """Test that correct minutes are calculated for a single slot."""
        # 8 hour slot
        mock_get_slots.return_value = [
            (datetime(2023, 5, 1, 9, 0), datetime(2023, 5, 1, 17, 0))
        ]
        
        start_time = datetime(2023, 5, 1, 9, 0)
        end_time = datetime(2023, 5, 1, 17, 0)
        minutes = get_total_available_minutes(start_time, end_time)
        
        assert minutes == 8 * 60  # 8 hours = 480 minutes
    
    @patch('app.ranking.get_available_time_slots')
    def test_multiple_slots(self, mock_get_slots):
        """Test that correct minutes are calculated for multiple slots."""
        # Two 2-hour slots
        mock_get_slots.return_value = [
            (datetime(2023, 5, 1, 9, 0), datetime(2023, 5, 1, 11, 0)),
            (datetime(2023, 5, 1, 13, 0), datetime(2023, 5, 1, 15, 0))
        ]
        
        start_time = datetime(2023, 5, 1, 9, 0)
        end_time = datetime(2023, 5, 1, 17, 0)
        minutes = get_total_available_minutes(start_time, end_time)
        
        assert minutes == 4 * 60  # 4 hours = 240 minutes
    
    @patch('app.ranking.get_available_time_slots')
    def test_no_slots(self, mock_get_slots):
        """Test that zero is returned when there are no available slots."""
        mock_get_slots.return_value = []
        
        start_time = datetime(2023, 5, 1, 9, 0)
        end_time = datetime(2023, 5, 1, 17, 0)
        minutes = get_total_available_minutes(start_time, end_time)
        
        assert minutes == 0

class TestRankTasks:
    """Tests for the main task ranking function."""
    
    def create_test_tasks(self):
        """Helper to create a list of test tasks with varying properties."""
        # Task with deadline today
        task1 = MagicMock(spec=Task)
        task1.id = 1
        task1.description = "Urgent task"
        task1.deadline = datetime.utcnow() + timedelta(hours=3)
        task1.estimated_duration = 30
        task1.domain = TaskDomain.WORK
        task1.status = TaskStatus.PENDING
        task1.project_id = 1
        task1.urgency_override = None
        
        # Task with deadline tomorrow
        task2 = MagicMock(spec=Task)
        task2.id = 2
        task2.description = "Important task"
        task2.deadline = datetime.utcnow() + timedelta(days=1)
        task2.estimated_duration = 60
        task2.domain = TaskDomain.WORK
        task2.status = TaskStatus.PENDING
        task2.project_id = 1
        task2.urgency_override = None
        
        # Task with deadline next week
        task3 = MagicMock(spec=Task)
        task3.id = 3
        task3.description = "Long-term task"
        task3.deadline = datetime.utcnow() + timedelta(days=7)
        task3.estimated_duration = 120
        task3.domain = TaskDomain.LIFE_ADMIN
        task3.status = TaskStatus.PENDING
        task3.project_id = 2
        task3.urgency_override = None
        
        # Quick task without deadline
        task4 = MagicMock(spec=Task)
        task4.id = 4
        task4.description = "Quick win"
        task4.deadline = None
        task4.estimated_duration = 5
        task4.domain = TaskDomain.GENERAL_LIFE
        task4.status = TaskStatus.PENDING
        task4.project_id = 3
        task4.urgency_override = None
        
        # Completed task (should be excluded)
        task5 = MagicMock(spec=Task)
        task5.id = 5
        task5.description = "Completed task"
        task5.deadline = datetime.utcnow() - timedelta(days=1)
        task5.estimated_duration = 15
        task5.domain = TaskDomain.WORK
        task5.status = TaskStatus.COMPLETED
        task5.project_id = 1
        task5.urgency_override = None
        
        return [task1, task2, task3, task4, task5]
    
    @patch('app.ranking.get_domain_weights')
    def test_rank_tasks_by_priority(self, mock_get_weights):
        """Test that tasks are ranked correctly by priority."""
        mock_get_weights.return_value = {'work': 1.0, 'life_admin': 0.8, 'general_life': 0.6}
        
        tasks = self.create_test_tasks()
        ranked_tasks = rank_tasks(tasks)
        
        # Should exclude completed tasks
        assert len(ranked_tasks) == 4
        
        # Urgency should be the primary factor, so task1 (deadline today) should be first
        assert ranked_tasks[0].id == 1
        
        # Task with deadline tomorrow should be second
        assert ranked_tasks[1].id == 2
    
    @patch('app.ranking.get_domain_weights')
    def test_rank_tasks_with_time_constraint(self, mock_get_weights):
        """Test that tasks are ranked with time constraint."""
        mock_get_weights.return_value = {'work': 1.0, 'life_admin': 0.8, 'general_life': 0.6}
        
        tasks = self.create_test_tasks()
        ranked_tasks = rank_tasks(tasks, available_time=60)
        
        # With 60 minutes available, should select 2 tasks: task1 (30 min) and task4 (5 min)
        # or a different optimal combination
        assert len(ranked_tasks) <= 2
        
        # Total duration should not exceed available time
        total_duration = sum(task.estimated_duration for task in ranked_tasks)
        assert total_duration <= 60
    
    @patch('app.ranking.get_domain_weights')
    def test_rank_tasks_with_current_task(self, mock_get_weights):
        """Test that context switching is considered with current task."""
        mock_get_weights.return_value = {'work': 1.0, 'life_admin': 0.8, 'general_life': 0.6}
        
        tasks = self.create_test_tasks()
        current_task = tasks[1]  # Task from project 1, domain WORK
        
        ranked_tasks = rank_tasks(tasks, current_task=current_task)
        
        # Given equal priority, tasks from same project/domain should rank higher
        # But deadline is more important, so task1 should still be first
        assert ranked_tasks[0].id == 1  # Urgent task from same project
    
    @patch('app.ranking.get_domain_weights')
    @patch('app.ranking.get_total_available_minutes')
    def test_rank_tasks_with_time_period(self, mock_get_minutes, mock_get_weights):
        """Test that time period is used to determine available time."""
        mock_get_weights.return_value = {'work': 1.0, 'life_admin': 0.8, 'general_life': 0.6}
        mock_get_minutes.return_value = 90
        
        tasks = self.create_test_tasks()
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=3)
        
        ranked_tasks = rank_tasks(tasks, time_period=(start_time, end_time))
        
        # With 90 minutes available, should select at most 2 tasks
        # Task1 (30 min) and either Task2 (60 min) or Task4 (5 min) + Task3 (120 min, but too long)
        assert len(ranked_tasks) <= 3
        
        # Mock should have been called
        mock_get_minutes.assert_called_once_with(start_time, end_time)
    
    def test_empty_task_list(self):
        """Test handling of empty task list."""
        ranked_tasks = rank_tasks([])
        assert ranked_tasks == []

class TestKnapsackTaskSelection:
    """Tests for the knapsack task selection algorithm."""
    
    def test_knapsack_basic(self):
        """Test basic knapsack selection."""
        # Create tasks with different durations and scores
        task1 = MagicMock(spec=Task)
        task1.estimated_duration = 30
        ranked_task1 = {'task': task1, 'score': 8.0}
        
        task2 = MagicMock(spec=Task)
        task2.estimated_duration = 45
        ranked_task2 = {'task': task2, 'score': 7.0}
        
        task3 = MagicMock(spec=Task)
        task3.estimated_duration = 60
        ranked_task3 = {'task': task3, 'score': 6.0}
        
        ranked_tasks = [ranked_task1, ranked_task2, ranked_task3]
        
        # With 90 minutes, should select tasks 1 and 2 (best value)
        selected = knapsack_task_selection(ranked_tasks, 90)
        assert len(selected) == 2
        assert task1 in selected
        assert task2 in selected
    
    def test_knapsack_exact_fit(self):
        """Test knapsack with exact time fit."""
        task1 = MagicMock(spec=Task)
        task1.estimated_duration = 30
        ranked_task1 = {'task': task1, 'score': 8.0}
        
        task2 = MagicMock(spec=Task)
        task2.estimated_duration = 30
        ranked_task2 = {'task': task2, 'score': 7.0}
        
        ranked_tasks = [ranked_task1, ranked_task2]
        
        # With 60 minutes, should select both tasks
        selected = knapsack_task_selection(ranked_tasks, 60)
        assert len(selected) == 2
        assert task1 in selected
        assert task2 in selected
    
    def test_knapsack_no_fit(self):
        """Test knapsack when no tasks fit."""
        task1 = MagicMock(spec=Task)
        task1.estimated_duration = 30
        ranked_task1 = {'task': task1, 'score': 8.0}
        
        ranked_tasks = [ranked_task1]
        
        # With 20 minutes, no tasks should fit
        selected = knapsack_task_selection(ranked_tasks, 20)
        assert len(selected) == 0
    
    def test_knapsack_empty_input(self):
        """Test knapsack with empty input."""
        selected = knapsack_task_selection([], 60)
        assert len(selected) == 0

class TestGetRankedTasksByDomain:
    """Tests for the domain-specific task ranking function."""
    
    @patch('app.ranking.rank_tasks')
    def test_filter_by_domain(self, mock_rank_tasks):
        """Test that tasks are filtered by domain before ranking."""
        mock_rank_tasks.return_value = ["ranked tasks"]
        
        task1 = MagicMock(spec=Task)
        task1.domain = TaskDomain.WORK
        task1.status = TaskStatus.PENDING
        
        task2 = MagicMock(spec=Task)
        task2.domain = TaskDomain.LIFE_ADMIN
        task2.status = TaskStatus.PENDING
        
        tasks = [task1, task2]
        result = get_ranked_tasks_by_domain(tasks, TaskDomain.WORK)
        
        # Should filter for WORK domain only
        mock_rank_tasks.assert_called_once()
        args, _ = mock_rank_tasks.call_args
        assert len(args[0]) == 1
        assert args[0][0].domain == TaskDomain.WORK

class TestRecommendNextTask:
    """Tests for the next task recommendation function."""
    
    @patch('app.ranking.rank_tasks')
    def test_recommend_next_task(self, mock_rank_tasks):
        """Test that the highest ranked task is recommended."""
        task1 = MagicMock(spec=Task)
        task1.id = 1
        
        task2 = MagicMock(spec=Task)
        task2.id = 2
        
        mock_rank_tasks.return_value = [task1, task2]
        
        tasks = [task1, task2]
        next_task = recommend_next_task(tasks)
        
        assert next_task == task1
    
    @patch('app.ranking.rank_tasks')
    def test_recommend_next_task_empty(self, mock_rank_tasks):
        """Test recommendation when no tasks are available."""
        mock_rank_tasks.return_value = []
        
        next_task = recommend_next_task([])
        
        assert next_task is None