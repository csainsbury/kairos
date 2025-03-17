# Google Calendar Integration for kAIros

import os
import json
from flask import Blueprint, request, jsonify, current_app, redirect, url_for, session
from datetime import datetime, timedelta
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors

from app.utils import setup_logger, retry_with_backoff
from app.models import Task, db

# Setup module logger
logger = setup_logger(__name__)

# Create blueprint for Calendar integration
calendar_bp = Blueprint('calendar', __name__, url_prefix='/calendar')

# Google Calendar API scopes
SCOPES = ['https://www.googleapis.com/auth/calendar']

# If modifying these REDIRECT_URI, delete the file token.json.
REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:5000/calendar/oauth2callback')

def get_credentials_from_session():
    """Get Google credentials from session."""
    if 'credentials' not in session:
        return None

    return google.oauth2.credentials.Credentials(
        **session['credentials']
    )

def save_credentials_to_session(credentials):
    """Save credentials to session."""
    session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

def get_calendar_service():
    """Get an authorized Google Calendar API service instance."""
    credentials = get_credentials_from_session()
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(google.auth.transport.requests.Request())
            save_credentials_to_session(credentials)
        else:
            return None

    return googleapiclient.discovery.build('calendar', 'v3', credentials=credentials)

@calendar_bp.route('/authorize')
def authorize():
    """Authorize the application to access Google Calendar."""
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        {
            "web": {
                "client_id": current_app.config.get('GOOGLE_CLIENT_ID'),
                "client_secret": current_app.config.get('GOOGLE_CLIENT_SECRET'),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI]
            }
        },
        scopes=SCOPES
    )
    
    flow.redirect_uri = REDIRECT_URI
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    
    session['state'] = state
    
    return redirect(authorization_url)

@calendar_bp.route('/oauth2callback')
def oauth2callback():
    """Handle the OAuth2 callback from Google."""
    state = session.get('state')
    
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        {
            "web": {
                "client_id": current_app.config.get('GOOGLE_CLIENT_ID'),
                "client_secret": current_app.config.get('GOOGLE_CLIENT_SECRET'),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI]
            }
        },
        scopes=SCOPES,
        state=state
    )
    flow.redirect_uri = REDIRECT_URI
    
    # Use the authorization server's response to fetch the OAuth 2.0 tokens
    authorization_response = request.url
    flow.fetch_token(authorization_response=authorization_response)
    
    # Store the credentials in the session
    credentials = flow.credentials
    save_credentials_to_session(credentials)
    
    return redirect(url_for('calendar.calendar_success'))

@calendar_bp.route('/success')
def calendar_success():
    """Show success page after successful calendar authentication."""
    return jsonify({'status': 'success', 'message': 'Google Calendar authenticated successfully'})

@retry_with_backoff(max_retries=3)
def get_calendar_events(start_time=None, end_time=None):
    """Retrieve calendar events
    
    Args:
        start_time: Start time for events range
        end_time: End time for events range
        
    Returns:
        List of calendar events
    """
    try:
        service = get_calendar_service()
        if not service:
            logger.error("Calendar service not available - authentication required")
            return []

        # Set default time range if not provided
        if not start_time:
            start_time = datetime.utcnow()
        if not end_time:
            end_time = start_time + timedelta(days=7)  # Default to one week ahead
            
        # Format time for Google Calendar API
        time_min = start_time.isoformat() + 'Z'  # 'Z' indicates UTC time
        time_max = end_time.isoformat() + 'Z'
            
        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        
        # Format events for our application
        formatted_events = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            
            formatted_events.append({
                'id': event['id'],
                'title': event['summary'],
                'start': start,
                'end': end,
                'description': event.get('description', ''),
                'location': event.get('location', '')
            })
        
        logger.info(f"Retrieved {len(formatted_events)} calendar events from {start_time} to {end_time}")
        return formatted_events
    
    except googleapiclient.errors.HttpError as error:
        logger.error(f"Failed to retrieve calendar events: {error}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving calendar events: {str(e)}")
        raise

@retry_with_backoff(max_retries=3)
def add_calendar_event(title, start_time, end_time, description=None, location=None):
    """Add a calendar event
    
    Args:
        title: Event title
        start_time: Event start time (datetime)
        end_time: Event end time (datetime)
        description: Optional event description
        location: Optional event location
        
    Returns:
        Event ID if successful
    """
    try:
        service = get_calendar_service()
        if not service:
            logger.error("Calendar service not available - authentication required")
            return None

        # Format start and end time
        start_iso = start_time.isoformat()
        end_iso = end_time.isoformat()
        
        event = {
            'summary': title,
            'start': {
                'dateTime': start_iso,
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_iso,
                'timeZone': 'UTC',
            }
        }
        
        if description:
            event['description'] = description
            
        if location:
            event['location'] = location
            
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        
        logger.info(f"Created calendar event: {title} with ID {created_event['id']}")
        return created_event['id']
    
    except googleapiclient.errors.HttpError as error:
        logger.error(f"Failed to create calendar event: {error}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating calendar event: {str(e)}")
        raise

@retry_with_backoff(max_retries=3)
def update_calendar_event(event_id, title=None, start_time=None, end_time=None, description=None, location=None):
    """Update an existing calendar event
    
    Args:
        event_id: The ID of the event to update
        title: New event title (optional)
        start_time: New event start time (optional)
        end_time: New event end time (optional)
        description: New event description (optional)
        location: New event location (optional)
        
    Returns:
        Updated event if successful
    """
    try:
        service = get_calendar_service()
        if not service:
            logger.error("Calendar service not available - authentication required")
            return None

        # First get the existing event
        event = service.events().get(calendarId='primary', eventId=event_id).execute()
        
        # Update fields that were provided
        if title:
            event['summary'] = title
            
        if start_time:
            event['start']['dateTime'] = start_time.isoformat()
            
        if end_time:
            event['end']['dateTime'] = end_time.isoformat()
            
        if description:
            event['description'] = description
            
        if location:
            event['location'] = location
            
        updated_event = service.events().update(
            calendarId='primary', 
            eventId=event_id, 
            body=event
        ).execute()
        
        logger.info(f"Updated calendar event with ID {event_id}")
        return updated_event
    
    except googleapiclient.errors.HttpError as error:
        logger.error(f"Failed to update calendar event: {error}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating calendar event: {str(e)}")
        raise

@retry_with_backoff(max_retries=3)
def delete_calendar_event(event_id):
    """Delete a calendar event
    
    Args:
        event_id: The ID of the event to delete
        
    Returns:
        True if deletion was successful
    """
    try:
        service = get_calendar_service()
        if not service:
            logger.error("Calendar service not available - authentication required")
            return False

        service.events().delete(calendarId='primary', eventId=event_id).execute()
        logger.info(f"Deleted calendar event with ID {event_id}")
        return True
    
    except googleapiclient.errors.HttpError as error:
        logger.error(f"Failed to delete calendar event: {error}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting calendar event: {str(e)}")
        raise

def sync_task_to_calendar(task_id):
    """Sync a task to Google Calendar
    
    Args:
        task_id: ID of the task to sync
        
    Returns:
        Event ID if successful, None otherwise
    """
    try:
        task = Task.query.get(task_id)
        if not task:
            logger.error(f"Task not found: {task_id}")
            return None
            
        if not task.deadline:
            logger.warning(f"Task has no deadline, cannot sync to calendar: {task_id}")
            return None
            
        # Calculate event time based on task duration and deadline
        end_time = task.deadline
        start_time = end_time - timedelta(minutes=task.estimated_duration)
        
        # Create description with task details
        description = f"Task: {task.description}\n"
        if task.project:
            description += f"Project: {task.project.name}\n"
        description += f"Domain: {task.domain.value}\n"
        description += f"Estimated duration: {task.estimated_duration} minutes\n"
        description += f"Added from kAIros"
        
        # Add event to calendar
        event_id = add_calendar_event(
            title=task.description,
            start_time=start_time,
            end_time=end_time,
            description=description
        )
        
        logger.info(f"Synced task {task_id} to calendar with event ID {event_id}")
        return event_id
        
    except Exception as e:
        logger.error(f"Failed to sync task to calendar: {str(e)}")
        return None

@calendar_bp.route('/events', methods=['GET'])
def list_events():
    """API endpoint to list calendar events"""
    try:
        # Parse date range parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        start_time = None
        end_time = None
        
        if start_date:
            start_time = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        
        if end_date:
            end_time = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            
        events = get_calendar_events(start_time, end_time)
        return jsonify({'events': events})
        
    except ValueError as e:
        logger.error(f"Invalid date format: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)'}), 400
    except Exception as e:
        logger.error(f"Error retrieving calendar events: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@calendar_bp.route('/events', methods=['POST'])
def create_event():
    """API endpoint to create a calendar event"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not all(key in data for key in ['title', 'start_time', 'end_time']):
            return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400
            
        # Parse datetime strings
        start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
        end_time = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
        
        # Create event
        event_id = add_calendar_event(
            title=data['title'],
            start_time=start_time,
            end_time=end_time,
            description=data.get('description'),
            location=data.get('location')
        )
        
        if not event_id:
            return jsonify({'status': 'error', 'message': 'Failed to create event, authentication may be required'}), 401
            
        return jsonify({'status': 'success', 'event_id': event_id})
        
    except ValueError as e:
        logger.error(f"Invalid date format: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)'}), 400
    except Exception as e:
        logger.error(f"Error creating calendar event: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@calendar_bp.route('/events/<event_id>', methods=['PUT'])
def update_event(event_id):
    """API endpoint to update a calendar event"""
    try:
        data = request.get_json()
        
        # Parse datetime strings if provided
        start_time = None
        end_time = None
        
        if 'start_time' in data:
            start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
            
        if 'end_time' in data:
            end_time = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
            
        # Update event
        updated_event = update_calendar_event(
            event_id=event_id,
            title=data.get('title'),
            start_time=start_time,
            end_time=end_time,
            description=data.get('description'),
            location=data.get('location')
        )
        
        if not updated_event:
            return jsonify({'status': 'error', 'message': 'Failed to update event, authentication may be required'}), 401
            
        return jsonify({'status': 'success', 'event': updated_event})
        
    except ValueError as e:
        logger.error(f"Invalid date format: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)'}), 400
    except Exception as e:
        logger.error(f"Error updating calendar event: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@calendar_bp.route('/events/<event_id>', methods=['DELETE'])
def delete_event(event_id):
    """API endpoint to delete a calendar event"""
    try:
        success = delete_calendar_event(event_id)
        
        if not success:
            return jsonify({'status': 'error', 'message': 'Failed to delete event, authentication may be required'}), 401
            
        return jsonify({'status': 'success', 'message': 'Event deleted successfully'})
        
    except Exception as e:
        logger.error(f"Error deleting calendar event: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@calendar_bp.route('/sync/task/<int:task_id>', methods=['POST'])
def sync_task(task_id):
    """API endpoint to sync a task to Google Calendar"""
    try:
        event_id = sync_task_to_calendar(task_id)
        
        if not event_id:
            return jsonify({'status': 'error', 'message': 'Failed to sync task to calendar'}), 400
            
        return jsonify({'status': 'success', 'event_id': event_id})
        
    except Exception as e:
        logger.error(f"Error syncing task to calendar: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@calendar_bp.route('/sync/tasks', methods=['POST'])
def sync_all_tasks():
    """API endpoint to sync multiple tasks to Google Calendar"""
    try:
        data = request.get_json()
        task_ids = data.get('task_ids', [])
        
        if not task_ids:
            return jsonify({'status': 'error', 'message': 'No task IDs provided'}), 400
            
        results = {}
        for task_id in task_ids:
            event_id = sync_task_to_calendar(task_id)
            results[task_id] = event_id if event_id else "Failed"
            
        return jsonify({'status': 'success', 'results': results})
        
    except Exception as e:
        logger.error(f"Error syncing tasks to calendar: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500