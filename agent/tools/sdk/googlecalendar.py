# agent/tools/sdk/googlecalendar.py

import datetime
import json
import uuid
from typing import List, Optional, Dict, Any

import pytz
from agno.tools import Toolkit
from agno.utils.log import logger
from googleapiclient.errors import HttpError

# Fix the import path
from agent.tools.sdk.googleauth import GoogleAuth


def print_event(event: Dict[str, Any]) -> str:
    """
    Simple function to format a single event for debugging/readable display

    Args:
        event: Google Calendar event object

    Returns:
        str: Nicely formatted event string
    """
    try:
        # Extract basic info
        title = event.get('summary', 'No Title')
        location = event.get('location', '')

        # Format datetime
        start_info = event.get('start', {})
        end_info = event.get('end', {})

        if 'dateTime' in start_info:
            # Regular event with time
            start_dt = datetime.datetime.fromisoformat(start_info['dateTime'].replace('Z', '+00:00'))
            end_dt = datetime.datetime.fromisoformat(end_info['dateTime'].replace('Z', '+00:00'))

            date_str = start_dt.strftime('%B %d, %Y')
            time_str = f"{start_dt.strftime('%I:%M %p')} - {end_dt.strftime('%I:%M %p')}"

        elif 'date' in start_info:
            # All-day event
            start_date = datetime.datetime.fromisoformat(start_info['date'])
            date_str = start_date.strftime('%B %d, %Y')
            time_str = "All day"
        else:
            date_str = "Unknown date"
            time_str = ""

        # Build the formatted string
        formatted = f"📅 {title} | {date_str} | {time_str}"

        if location:
            # Clean up location (remove Unicode markers)
            clean_location = location.replace('\u200f', '').strip()[:50]
            formatted += f" | 📍 {clean_location}"

        return formatted

    except Exception as e:
        return f"❌ Error formatting event: {str(e)}"


class GoogleCalendarTools(Toolkit):
    def __init__(self, user_id: str, **kwargs):
        """
        Google Calendar Tool with Clean Authentication

        Args:
            user_id: Unique identifier for the user (e.g., Telegram user ID)
        """
        super().__init__(name="google_calendar_tools", **kwargs)

        self.user_id = user_id
        self.auth = GoogleAuth(user_id=user_id)
        self.service = None

        # Register available methods
        self.register(self.list_calendars)
        self.register(self.list_events)
        self.register(self.create_event)
        self.register(self.update_event)
        self.register(self.delete_event)
        self.register(self.get_event)
        self.register(self.find_free_time)
        self.register(self.list_day_events)
        self.register(self.test_timezone_detection)
        self.register(self.create_calendar)
        self.register(self.update_calendar)
        self.register(self.delete_calendar)
        self.register(self.move_event)
        self.register(self.move_multiple_events)

    def _ensure_authenticated(self):
        """
        Ensure we have a valid Google Calendar service
        """
        if not self.service:
            try:
                logger.info(f"Authenticating Google Calendar for user {self.user_id}")
                self.service = self.auth.login()
            except Exception as e:
                logger.error(f"Failed to authenticate Google Calendar: {str(e)}")
                raise Exception(f"Google Calendar authentication failed: {str(e)}")

    # ========================= HELPERS ======================

    def _get_user_timezone(self) -> str:
        """
        Get the user's timezone from their Google Calendar settings
        This should NEVER fail - always returns a valid timezone
        """
        try:
            # Get the user's primary calendar info which includes timezone
            calendar_info = self.service.calendars().get(calendarId='primary').execute()
            user_timezone = calendar_info.get('timeZone')

            if user_timezone:
                logger.info(f"✅ Auto-detected user timezone: {user_timezone}")
                return user_timezone
            else:
                logger.warning("No timezone in calendar info, using UTC")
                return 'UTC'

        except Exception as e:
            logger.error(f"Failed to detect timezone: {e}, using UTC")
            return 'UTC'

    def _validate_calendar_access(self, calendar_id: str) -> bool:
        """
        Check if user has access to a specific calendar
        """
        try:
            # Try to get calendar info - will fail if no access
            self.service.calendars().get(calendarId=calendar_id).execute()
            return True
        except HttpError as e:
            if e.resp.status in [403, 404]:
                return False
            raise e

    def test_timezone_detection(self) -> str:
        """
        Test if timezone detection is working
        """
        try:
            self._ensure_authenticated()

            # Test the timezone detection
            detected_tz = self._get_user_timezone()

            # Also get calendar info to see what's available
            calendar_info = self.service.calendars().get(calendarId='primary').execute()

            return json.dumps({
                "detected_timezone": detected_tz,
                "calendar_timezone": calendar_info.get('timeZone', 'NOT_FOUND'),
                "calendar_summary": calendar_info.get('summary', 'Unknown'),
                "test_status": "SUCCESS"
            })

        except Exception as e:
            logger.error(f"Timezone test error: {e}")
            return json.dumps({
                "error": str(e),
                "test_status": "FAILED"
            })

    # ========================= CALENDAR MANAGEMENT ======================

    def list_calendars(self) -> str:
        """
        List all calendars accessible to the user.

        This allows the agent to discover available calendars and their IDs.

        Returns:
            JSON string with list of calendars containing:
            - id: Calendar ID (use this in other functions)
            - summary: Calendar name/title
            - description: Calendar description
            - accessRole: User's access level (owner, reader, writer, etc.)
            - primary: Whether this is the primary calendar

        Agent Usage:
            calendars = list_calendars()
            # Agent can then use calendar IDs in other functions
        """
        try:
            self._ensure_authenticated()

            logger.info(f"Fetching calendar list for user {self.user_id}")

            # Get calendar list
            calendar_list = self.service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])

            # Extract useful information
            calendar_info = []
            for calendar in calendars:
                info = {
                    'id': calendar.get('id'),
                    'summary': calendar.get('summary', 'Unknown Calendar'),
                    'description': calendar.get('description', ''),
                    'accessRole': calendar.get('accessRole', 'unknown'),
                    'primary': calendar.get('primary', False),
                    'selected': calendar.get('selected', False),
                    'backgroundColor': calendar.get('backgroundColor', ''),
                    'timeZone': calendar.get('timeZone', '')
                }
                calendar_info.append(info)

            logger.info(f"Found {len(calendar_info)} calendars for user {self.user_id}")

            return json.dumps({
                "message": f"Found {len(calendar_info)} accessible calendars",
                "calendars": calendar_info
            })

        except HttpError as error:
            logger.error(f"Google Calendar API error: {error}")
            return json.dumps({"error": f"Google Calendar API error: {error}"})
        except Exception as error:
            logger.error(f"Unexpected error in list_calendars: {error}")
            return json.dumps({"error": f"Failed to list calendars: {error}"})

    def create_calendar(
            self,
            summary: str,
            description: Optional[str] = None,
            location: Optional[str] = None,
            timezone: Optional[str] = None
    ) -> str:
        """
        Create a new calendar with AUTOMATIC timezone detection.

        Args:
            summary (str): Calendar name/title (required)
            description (str): Calendar description (optional)
            location (str): Calendar location (optional)
            timezone (str): Calendar timezone (optional, will auto-detect if not provided)

        Returns:
            JSON string with created calendar information

        Agent Usage Examples:
            # Create basic calendar
            create_calendar(summary="Work Calendar")

            # Create detailed calendar
            create_calendar(summary="Project Alpha", description="Tasks for Project Alpha", location="Office")
        """
        try:
            self._ensure_authenticated()

            # Auto-detect timezone if not provided
            if not timezone:
                timezone = self._get_user_timezone()
                logger.info(f"Auto-detected timezone for new calendar: {timezone}")

            # Build calendar object
            calendar_body = {
                'summary': summary,
                'timeZone': timezone
            }

            if description:
                calendar_body['description'] = description
            if location:
                calendar_body['location'] = location

            logger.info(f"Creating calendar '{summary}' for user {self.user_id}")

            # Create the calendar
            created_calendar = self.service.calendars().insert(body=calendar_body).execute()

            logger.info(f"✅ Calendar '{summary}' created successfully with ID: {created_calendar['id']}")

            return json.dumps({
                "message": f"Calendar '{summary}' created successfully",
                "calendar": {
                    "id": created_calendar['id'],
                    "summary": created_calendar['summary'],
                    "description": created_calendar.get('description', ''),
                    "location": created_calendar.get('location', ''),
                    "timeZone": created_calendar['timeZone']
                }
            })

        except HttpError as error:
            logger.error(f"Google Calendar API error: {error}")
            return json.dumps({"error": f"Google Calendar API error: {error}"})
        except Exception as error:
            logger.error(f"Unexpected error in create_calendar: {error}")
            return json.dumps({"error": f"Failed to create calendar: {error}"})

    def update_calendar(
            self,
            calendar_id: str,
            summary: Optional[str] = None,
            description: Optional[str] = None,
            location: Optional[str] = None,
            timezone: Optional[str] = None
    ) -> str:
        """
        Update an existing calendar's properties.

        Args:
            calendar_id (str): ID of the calendar to update (required)
            summary (str): New calendar name/title (optional)
            description (str): New calendar description (optional)
            location (str): New calendar location (optional)
            timezone (str): New calendar timezone (optional)

        Returns:
            JSON string with updated calendar information

        Agent Usage Examples:
            # Update calendar name
            update_calendar(calendar_id="calendar123@group.calendar.google.com", summary="Updated Work Calendar")

            # Update multiple properties
            update_calendar(calendar_id="calendar123@group.calendar.google.com",
                           summary="Project Beta", description="Updated project tasks")
        """
        try:
            self._ensure_authenticated()

            # Validate calendar access
            if not self._validate_calendar_access(calendar_id):
                return json.dumps({"error": f"No access to calendar: {calendar_id}"})

            # Get existing calendar to preserve unchanged fields
            try:
                existing_calendar = self.service.calendars().get(calendarId=calendar_id).execute()
            except HttpError as e:
                if e.resp.status == 404:
                    return json.dumps({"error": f"Calendar with ID {calendar_id} not found"})
                else:
                    return json.dumps({"error": f"Failed to fetch calendar: {str(e)}"})

            # Update only provided fields
            if summary is not None:
                existing_calendar['summary'] = summary
            if description is not None:
                existing_calendar['description'] = description
            if location is not None:
                existing_calendar['location'] = location
            if timezone is not None:
                existing_calendar['timeZone'] = timezone

            logger.info(f"Updating calendar {calendar_id} for user {self.user_id}")

            # Update the calendar
            updated_calendar = self.service.calendars().update(
                calendarId=calendar_id,
                body=existing_calendar
            ).execute()

            logger.info(f"✅ Calendar {calendar_id} updated successfully")

            return json.dumps({
                "message": f"Calendar updated successfully",
                "calendar": {
                    "id": updated_calendar['id'],
                    "summary": updated_calendar['summary'],
                    "description": updated_calendar.get('description', ''),
                    "location": updated_calendar.get('location', ''),
                    "timeZone": updated_calendar['timeZone']
                }
            })

        except HttpError as error:
            logger.error(f"Google Calendar API error: {error}")
            return json.dumps({"error": f"Google Calendar API error: {error}"})
        except Exception as error:
            logger.error(f"Unexpected error in update_calendar: {error}")
            return json.dumps({"error": f"Failed to update calendar: {error}"})

    def delete_calendar(self, calendar_id: str) -> str:
        """
        Delete a calendar. WARNING: This permanently deletes the calendar and all its events.

        Args:
            calendar_id (str): ID of the calendar to delete (required)
                              Note: Cannot delete primary calendar

        Returns:
            JSON string with deletion confirmation

        Agent Usage Examples:
            # Delete a secondary calendar
            delete_calendar(calendar_id="calendar123@group.calendar.google.com")

        Important Notes:
            - Cannot delete the primary calendar (calendar_id="primary")
            - This action is irreversible - all events in the calendar will be lost
            - Only calendars owned by the user can be deleted
        """
        try:
            self._ensure_authenticated()

            # Prevent deletion of primary calendar
            if calendar_id == "primary":
                return json.dumps({
                    "error": "Cannot delete primary calendar. Only secondary calendars can be deleted."
                })

            # Validate calendar access
            if not self._validate_calendar_access(calendar_id):
                return json.dumps({"error": f"No access to calendar: {calendar_id}"})

            # Get calendar info before deletion for confirmation message
            try:
                calendar_info = self.service.calendars().get(calendarId=calendar_id).execute()
                calendar_name = calendar_info.get('summary', calendar_id)
            except HttpError as e:
                if e.resp.status == 404:
                    return json.dumps({"error": f"Calendar with ID {calendar_id} not found"})
                else:
                    return json.dumps({"error": f"Failed to fetch calendar info: {str(e)}"})

            logger.info(f"Deleting calendar {calendar_id} ({calendar_name}) for user {self.user_id}")

            # Delete the calendar
            self.service.calendars().delete(calendarId=calendar_id).execute()

            logger.info(f"✅ Calendar {calendar_id} ({calendar_name}) deleted successfully")

            return json.dumps({
                "message": f"Calendar '{calendar_name}' deleted successfully",
                "deleted_calendar": {
                    "id": calendar_id,
                    "name": calendar_name
                },
                "warning": "This action is irreversible. All events in this calendar have been permanently deleted."
            })

        except HttpError as error:
            if error.resp.status == 404:
                logger.warning(f"Calendar {calendar_id} not found")
                return json.dumps({"error": f"Calendar with ID {calendar_id} not found"})
            elif error.resp.status == 403:
                logger.warning(f"No permission to delete calendar {calendar_id}")
                return json.dumps({
                                      "error": f"No permission to delete calendar {calendar_id}. You can only delete calendars you own."})
            else:
                logger.error(f"Google Calendar API error: {error}")
                return json.dumps({"error": f"Google Calendar API error: {error}"})
        except Exception as error:
            logger.error(f"Unexpected error in delete_calendar: {error}")
            return json.dumps({"error": f"Failed to delete calendar: {error}"})

    def move_event(
            self,
            event_id: str,
            source_calendar_id: str = "primary",
            destination_calendar_id: str = "primary"
    ) -> str:
        """
        Move an event from one calendar to another using Google Calendar's move API.

        Args:
            event_id (str): ID of the event to move (required)
            source_calendar_id (str): Calendar containing the event (default: "primary")
            destination_calendar_id (str): Calendar to move the event to (required)

        Returns:
            JSON string with moved event information

        Agent Usage Examples:
            # Move event from primary to specific calendar
            move_event(event_id="abc123", destination_calendar_id="work@company.com")

            # Move event between specific calendars
            move_event(event_id="abc123", source_calendar_id="personal@gmail.com",
                      destination_calendar_id="work@company.com")
        """
        try:
            self._ensure_authenticated()

            # Validate access to both calendars
            if not self._validate_calendar_access(source_calendar_id):
                return json.dumps({"error": f"No access to source calendar: {source_calendar_id}"})

            if not self._validate_calendar_access(destination_calendar_id):
                return json.dumps({"error": f"No access to destination calendar: {destination_calendar_id}"})

            # Check if the event exists in the source calendar
            try:
                original_event = self.service.events().get(
                    calendarId=source_calendar_id,
                    eventId=event_id
                ).execute()
            except HttpError as e:
                if e.resp.status == 404:
                    return json.dumps({"error": f"Event with ID {event_id} not found in calendar {source_calendar_id}"})
                else:
                    return json.dumps({"error": f"Failed to fetch event: {str(e)}"})

            logger.info(
                f"Moving event {event_id} from {source_calendar_id} to {destination_calendar_id} for user {self.user_id}")

            # Use Google Calendar's move API
            moved_event = self.service.events().move(
                calendarId=source_calendar_id,
                eventId=event_id,
                destination=destination_calendar_id
            ).execute()

            logger.info(f"✅ Event {event_id} moved successfully from {source_calendar_id} to {destination_calendar_id}")

            return json.dumps({
                "message": f"Event '{original_event.get('summary', 'Untitled')}' moved successfully",
                "event": moved_event,
                "source_calendar": source_calendar_id,
                "destination_calendar": destination_calendar_id
            })

        except HttpError as error:
            if error.resp.status == 404:
                logger.warning(f"Event {event_id} not found in source calendar {source_calendar_id}")
                return json.dumps({"error": f"Event with ID {event_id} not found in calendar {source_calendar_id}"})
            elif error.resp.status == 403:
                logger.warning(f"No permission to move event {event_id}")
                return json.dumps({"error": f"No permission to move event {event_id}. Check calendar permissions."})
            else:
                logger.error(f"Google Calendar API error: {error}")
                return json.dumps({"error": f"Google Calendar API error: {error}"})
        except Exception as error:
            logger.error(f"Unexpected error in move_event: {error}")
            return json.dumps({"error": f"Failed to move event: {error}"})

    def move_multiple_events(
            self,
            event_ids: List[str],
            source_calendar_id: str = "primary",
            destination_calendar_id: str = "primary"
    ) -> str:
        """
        Move multiple events from one calendar to another.

        Args:
            event_ids (List[str]): List of event IDs to move (required)
            source_calendar_id (str): Calendar containing the events (default: "primary")
            destination_calendar_id (str): Calendar to move the events to (required)

        Returns:
            JSON string with results for each moved event

        Agent Usage Examples:
            # Move multiple events to Events calendar
            move_multiple_events(event_ids=["abc123", "def456"],
                                destination_calendar_id="events@group.calendar.google.com")
        """
        try:
            self._ensure_authenticated()

            # Validate access to both calendars
            if not self._validate_calendar_access(source_calendar_id):
                return json.dumps({"error": f"No access to source calendar: {source_calendar_id}"})

            if not self._validate_calendar_access(destination_calendar_id):
                return json.dumps({"error": f"No access to destination calendar: {destination_calendar_id}"})

            results = []
            successful_moves = 0
            failed_moves = 0

            logger.info(
                f"Moving {len(event_ids)} events from {source_calendar_id} to {destination_calendar_id} for user {self.user_id}")

            for event_id in event_ids:
                try:
                    # Get event details before moving
                    original_event = self.service.events().get(
                        calendarId=source_calendar_id,
                        eventId=event_id
                    ).execute()

                    # Move the event
                    moved_event = self.service.events().move(
                        calendarId=source_calendar_id,
                        eventId=event_id,
                        destination=destination_calendar_id
                    ).execute()

                    results.append({
                        "event_id": event_id,
                        "title": original_event.get('summary', 'Untitled'),
                        "status": "success",
                        "message": "Moved successfully"
                    })
                    successful_moves += 1

                except HttpError as e:
                    error_msg = f"API error: {str(e)}"
                    if e.resp.status == 404:
                        error_msg = "Event not found"
                    elif e.resp.status == 403:
                        error_msg = "Permission denied"

                    results.append({
                        "event_id": event_id,
                        "status": "failed",
                        "error": error_msg
                    })
                    failed_moves += 1
                    logger.warning(f"Failed to move event {event_id}: {error_msg}")

                except Exception as e:
                    results.append({
                        "event_id": event_id,
                        "status": "failed",
                        "error": f"Unexpected error: {str(e)}"
                    })
                    failed_moves += 1
                    logger.error(f"Unexpected error moving event {event_id}: {str(e)}")

            logger.info(f"✅ Batch move completed: {successful_moves} successful, {failed_moves} failed")

            return json.dumps({
                "message": f"Batch move completed: {successful_moves} successful, {failed_moves} failed",
                "successful_moves": successful_moves,
                "failed_moves": failed_moves,
                "results": results,
                "source_calendar": source_calendar_id,
                "destination_calendar": destination_calendar_id
            })

        except Exception as error:
            logger.error(f"Unexpected error in move_multiple_events: {error}")
            return json.dumps({"error": f"Failed to move events: {error}"})

    # ========================= EVENTS ======================

    def list_events(
            self,
            limit: int = 10,
            date_from: str = datetime.date.today().isoformat(),
            calendar_id: str = "primary",
            calendar_ids: Optional[List[str]] = None
    ) -> str:
        """
        List events from one or multiple calendars within a DATE RANGE.

        Args:
            limit (int): Number of events to return per calendar, default is 10
            date_from (str): Start date in ISO format (YYYY-MM-DD)
            calendar_id (str): Single calendar ID to query (default: "primary")
            calendar_ids (List[str], optional): Multiple calendar IDs to query
                                               If provided, overrides calendar_id

        Returns:
            JSON string with events from specified calendar(s)

        Agent Usage Examples:
            # Current behavior (unchanged)
            list_events()

            # Specific calendar
            list_events(calendar_id="work@company.com")

            # Multiple calendars
            list_events(calendar_ids=["primary", "work@company.com"])
        """
        try:
            self._ensure_authenticated()

            # Handle date formatting
            if date_from is None:
                date_from = datetime.datetime.now(datetime.timezone.utc).isoformat()
            elif isinstance(date_from, str):
                try:
                    date_from = datetime.datetime.fromisoformat(date_from).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                except ValueError:
                    logger.warning(f"Invalid date format: {date_from}, using today")
                    date_from = datetime.datetime.now(datetime.timezone.utc).isoformat()

            # Determine which calendars to query
            if calendar_ids:
                calendars_to_query = calendar_ids
                logger.info(f"Querying multiple calendars: {calendar_ids}")
            else:
                calendars_to_query = [calendar_id]
                logger.info(f"Querying single calendar: {calendar_id}")

            all_events = []
            calendar_info = {}

            # Query each calendar
            for cal_id in calendars_to_query:
                try:
                    # Validate access to calendar
                    if not self._validate_calendar_access(cal_id):
                        logger.warning(f"No access to calendar: {cal_id}")
                        calendar_info[cal_id] = {"error": "No access to this calendar"}
                        continue

                    logger.info(f"Fetching {limit} events from {date_from} for calendar {cal_id}")

                    events_result = (
                        self.service.events()
                        .list(
                            calendarId=cal_id,
                            timeMin=date_from,
                            maxResults=limit,
                            singleEvents=True,
                            orderBy="startTime",
                        )
                        .execute()
                    )

                    events = events_result.get("items", [])

                    # Add calendar info to each event for multi-calendar queries
                    for event in events:
                        event['_calendar_id'] = cal_id

                    all_events.extend(events)
                    calendar_info[cal_id] = {
                        "event_count": len(events),
                        "calendar_name": events_result.get("summary", cal_id)
                    }

                except HttpError as e:
                    logger.error(f"Error accessing calendar {cal_id}: {e}")
                    calendar_info[cal_id] = {"error": f"Calendar API error: {str(e)}"}

            # Sort all events by start time if multiple calendars
            if len(calendars_to_query) > 1:
                all_events.sort(key=lambda x: x.get('start', {}).get('dateTime', x.get('start', {}).get('date', '')))

            if not all_events:
                logger.info(f"No upcoming events found for user {self.user_id}")
                return json.dumps({
                    "message": "No upcoming events found",
                    "events": [],
                    "calendar_info": calendar_info
                })

            logger.info(f"Found {len(all_events)} total events for user {self.user_id}")
            return json.dumps({
                "message": f"Found {len(all_events)} events",
                "events": all_events,
                "calendar_info": calendar_info
            })

        except HttpError as error:
            logger.error(f"Google Calendar API error: {error}")
            return json.dumps({"error": f"Google Calendar API error: {error}"})
        except Exception as error:
            logger.error(f"Unexpected error in list_events: {error}")
            return json.dumps({"error": f"Failed to list events: {error}"})

    def create_event(
            self,
            start_datetime: str,
            end_datetime: str,
            title: Optional[str] = None,
            description: Optional[str] = None,
            location: Optional[str] = None,
            calendar_id: str = "primary",
            timezone: Optional[str] = None,  # IGNORED - we always auto-detect
            attendees: List[str] = [],
            send_updates: Optional[str] = "all",
            add_google_meet_link: Optional[bool] = False,
    ) -> str:
        """
        Create event in a specific calendar with AUTOMATIC timezone detection.

        Args:
            start_datetime (str): Event start time
            end_datetime (str): Event end time
            title (str): Event title
            description (str): Event description
            location (str): Event location
            calendar_id (str): Calendar ID to create event in (default: "primary")
            attendees (List[str]): List of attendee email addresses
            send_updates (str): Send updates to attendees
            add_google_meet_link (bool): Add Google Meet link

        Agent Usage Examples:
            # Create in primary calendar (unchanged behavior)
            create_event(start_datetime="2025-05-30T09:00:00", end_datetime="2025-05-30T10:00:00", title="Meeting")

            # Create in specific calendar
            create_event(start_datetime="2025-05-30T09:00:00", end_datetime="2025-05-30T10:00:00",
                        title="Work Meeting", calendar_id="work@company.com")
        """
        try:
            self._ensure_authenticated()

            # Validate calendar access
            if not self._validate_calendar_access(calendar_id):
                return json.dumps({"error": f"No access to calendar: {calendar_id}"})

            # ALWAYS auto-detect timezone - ignore any passed parameter
            user_timezone = self._get_user_timezone()
            logger.info(f"Auto-detected timezone: {user_timezone}")

            # Prepare attendees
            attendees_list = [{"email": attendee} for attendee in attendees] if attendees else []

            # Format datetime strings
            try:
                start_time = datetime.datetime.fromisoformat(start_datetime).strftime("%Y-%m-%dT%H:%M:%S")
                end_time = datetime.datetime.fromisoformat(end_datetime).strftime("%Y-%m-%dT%H:%M:%S")
            except ValueError as e:
                return json.dumps({"error": f"Invalid datetime format: {str(e)}"})

            # Build event with auto-detected timezone
            event = {
                "summary": title or "New Event",
                "location": location,
                "description": description,
                "start": {"dateTime": start_time, "timeZone": user_timezone},
                "end": {"dateTime": end_time, "timeZone": user_timezone},
                "attendees": attendees_list,
            }

            if add_google_meet_link:
                event["conferenceData"] = {
                    "createRequest": {
                        "requestId": str(uuid.uuid4()),
                        "conferenceSolutionKey": {"type": "hangoutsMeet"}
                    }
                }

            # Create the event in specified calendar
            event_result = (
                self.service.events()
                .insert(
                    calendarId=calendar_id,
                    body=event,
                    sendUpdates=send_updates,
                    conferenceDataVersion=1 if add_google_meet_link else 0,
                )
                .execute()
            )

            logger.info(f"✅ Event created in calendar {calendar_id} with timezone {user_timezone}")
            return json.dumps({
                "message": "Event created successfully",
                "event": event_result,
                "calendar_id": calendar_id
            })

        except HttpError as error:
            logger.error(f"Google Calendar API error: {error}")
            return json.dumps({"error": f"Google Calendar API error: {error}"})
        except Exception as error:
            logger.error(f"Unexpected error in create_event: {error}")
            return json.dumps({"error": f"Failed to create event: {error}"})

    def update_event(
            self,
            event_id: str,
            title: Optional[str] = None,
            description: Optional[str] = None,
            location: Optional[str] = None,
            start_datetime: Optional[str] = None,
            end_datetime: Optional[str] = None,
            calendar_id: str = "primary",
            timezone: Optional[str] = None,  # IGNORED - we always auto-detect
            attendees: Optional[List[str]] = None,
            send_updates: Optional[str] = "all",
    ) -> str:
        """
        Update event in a specific calendar with AUTOMATIC timezone detection.

        Args:
            event_id (str): ID of event to update
            calendar_id (str): Calendar containing the event (default: "primary")
            Other parameters: Fields to update (optional)

        Agent Usage Examples:
            # Update event in primary calendar (unchanged behavior)
            update_event(event_id="abc123", title="New Title")

            # Update event in specific calendar
            update_event(event_id="abc123", title="New Title", calendar_id="work@company.com")
        """
        try:
            self._ensure_authenticated()

            # Validate calendar access
            if not self._validate_calendar_access(calendar_id):
                return json.dumps({"error": f"No access to calendar: {calendar_id}"})

            # Get existing event from specified calendar
            try:
                existing_event = self.service.events().get(
                    calendarId=calendar_id,
                    eventId=event_id
                ).execute()
            except HttpError as e:
                if e.resp.status == 404:
                    return json.dumps({"error": f"Event with ID {event_id} not found in calendar {calendar_id}"})
                else:
                    return json.dumps({"error": f"Failed to fetch event: {str(e)}"})

            # ALWAYS auto-detect timezone - ignore any passed parameter
            user_timezone = self._get_user_timezone()
            logger.info(f"Auto-detected timezone for update: {user_timezone}")

            # Update fields that were provided
            if title is not None:
                existing_event['summary'] = title
            if description is not None:
                existing_event['description'] = description
            if location is not None:
                existing_event['location'] = location
            if attendees is not None:
                existing_event['attendees'] = [{"email": attendee} for attendee in attendees]

            # Handle datetime updates with auto-detected timezone
            if start_datetime is not None and end_datetime is not None:
                try:
                    start_time = datetime.datetime.fromisoformat(start_datetime).strftime("%Y-%m-%dT%H:%M:%S")
                    end_time = datetime.datetime.fromisoformat(end_datetime).strftime("%Y-%m-%dT%H:%M:%S")

                    # Use auto-detected timezone
                    existing_event['start'] = {"dateTime": start_time, "timeZone": user_timezone}
                    existing_event['end'] = {"dateTime": end_time, "timeZone": user_timezone}

                except ValueError as e:
                    return json.dumps({"error": f"Invalid datetime format: {str(e)}"})

            # Update the event in specified calendar
            updated_event = (
                self.service.events()
                .update(
                    calendarId=calendar_id,
                    eventId=event_id,
                    body=existing_event,
                    sendUpdates=send_updates,
                )
                .execute()
            )

            logger.info(f"✅ Event updated in calendar {calendar_id} with timezone {user_timezone}")
            return json.dumps({
                "message": "Event updated successfully",
                "event": updated_event,
                "calendar_id": calendar_id
            })

        except HttpError as error:
            logger.error(f"Google Calendar API error: {error}")
            return json.dumps({"error": f"Google Calendar API error: {error}"})
        except Exception as error:
            logger.error(f"Unexpected error in update_event: {error}")
            return json.dumps({"error": f"Failed to update event: {error}"})

    def delete_event(
            self,
            event_id: str,
            calendar_id: str = "primary",
            send_updates: Optional[str] = "all"
    ) -> str:
        """
        Delete an event from a specific calendar.

        Args:
            event_id (str): ID of the event to delete
            calendar_id (str): Calendar containing the event (default: "primary")
            send_updates (str): Whether to send updates to attendees

        Agent Usage Examples:
            # Delete from primary calendar (unchanged behavior)
            delete_event(event_id="abc123")

            # Delete from specific calendar
            delete_event(event_id="abc123", calendar_id="work@company.com")
        """
        try:
            self._ensure_authenticated()

            # Validate calendar access
            if not self._validate_calendar_access(calendar_id):
                return json.dumps({"error": f"No access to calendar: {calendar_id}"})

            logger.info(f"Deleting event {event_id} from calendar {calendar_id} for user {self.user_id}")

            # Delete the event from specified calendar
            self.service.events().delete(
                calendarId=calendar_id,
                eventId=event_id,
                sendUpdates=send_updates
            ).execute()

            logger.info(f"✅ Event {event_id} deleted successfully from calendar {calendar_id}")
            return json.dumps({
                "message": f"Event {event_id} deleted successfully",
                "calendar_id": calendar_id
            })

        except HttpError as error:
            if error.resp.status == 404:
                logger.warning(f"Event {event_id} not found in calendar {calendar_id}")
                return json.dumps({"error": f"Event with ID {event_id} not found in calendar {calendar_id}"})
            else:
                logger.error(f"Google Calendar API error: {error}")
                return json.dumps({"error": f"Google Calendar API error: {error}"})
        except Exception as error:
            logger.error(f"Unexpected error in delete_event: {error}")
            return json.dumps({"error": f"Failed to delete event: {error}"})

    def get_event(self, event_id: str, calendar_id: str = "primary") -> str:
        """
        Get details of a specific calendar event by ID from a specific calendar.

        Args:
            event_id (str): Event ID from list_events() response
            calendar_id (str): Calendar containing the event (default: "primary")

        Agent Usage Examples:
            # Get from primary calendar (unchanged behavior)
            get_event(event_id="6b20focpa932fjsm9mia7ksat0")

            # Get from specific calendar
            get_event(event_id="6b20focpa932fjsm9mia7ksat0", calendar_id="work@company.com")
        """
        try:
            self._ensure_authenticated()

            # Validate calendar access
            if not self._validate_calendar_access(calendar_id):
                return json.dumps({"error": f"No access to calendar: {calendar_id}"})

            logger.info(f"Fetching event {event_id} from calendar {calendar_id} for user {self.user_id}")

            # Get the specific event from specified calendar
            event = self.service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()

            logger.info(f"✅ Event {event_id} retrieved successfully from calendar {calendar_id}")
            return json.dumps({
                "event": event,
                "calendar_id": calendar_id
            })

        except HttpError as error:
            if error.resp.status == 404:
                logger.warning(f"Event {event_id} not found in calendar {calendar_id}")
                return json.dumps({
                    "error": f"Event with ID {event_id} not found in calendar {calendar_id}. Use list_events() to see available events."
                })
            else:
                logger.error(f"Google Calendar API error: {error}")
                return json.dumps({"error": f"Google Calendar API error: {error}"})
        except Exception as error:
            logger.error(f"Unexpected error in get_event: {error}")
            return json.dumps({"error": f"Failed to get event: {error}"})

    def find_free_time(
            self,
            duration_minutes: int,
            search_days: int = 7,
            work_hours_start: int = 9,
            work_hours_end: int = 17,
            exclude_weekends: bool = True,
            calendar_id: str = "primary",
            calendar_ids: Optional[List[str]] = None
    ) -> str:
        """
        Find available time slots considering events from one or multiple calendars.

        Args:
            duration_minutes (int): Required duration in minutes
            search_days (int): Days to search ahead
            work_hours_start (int): Start of work hours
            work_hours_end (int): End of work hours
            exclude_weekends (bool): Skip weekends
            calendar_id (str): Single calendar to check (default: "primary")
            calendar_ids (List[str], optional): Multiple calendars to check
                                               If provided, overrides calendar_id

        Agent Usage Examples:
            # Check primary calendar only (unchanged behavior)
            find_free_time(duration_minutes=60)

            # Check specific calendar
            find_free_time(duration_minutes=60, calendar_id="work@company.com")

            # Check across multiple calendars
            find_free_time(duration_minutes=60, calendar_ids=["primary", "work@company.com"])
        """
        try:
            self._ensure_authenticated()

            # Determine which calendars to check
            if calendar_ids:
                calendars_to_check = calendar_ids
                logger.info(f"Finding free time across multiple calendars: {calendar_ids}")
            else:
                calendars_to_check = [calendar_id]
                logger.info(f"Finding free time in calendar: {calendar_id}")

            logger.info(f"Finding {duration_minutes} min free slots for user {self.user_id}")

            # Get user's timezone first
            user_timezone_str = self._get_user_timezone()
            try:
                user_tz = pytz.timezone(user_timezone_str)
            except:
                user_tz = pytz.UTC

            logger.info(f"Using user timezone: {user_timezone_str}")

            # Calculate search date range in USER'S timezone
            start_date = datetime.datetime.now(user_tz)
            end_date = start_date + datetime.timedelta(days=search_days)

            # Get all events from all specified calendars
            all_events = []
            for cal_id in calendars_to_check:
                try:
                    if not self._validate_calendar_access(cal_id):
                        logger.warning(f"No access to calendar: {cal_id}, skipping")
                        continue

                    events_result = (
                        self.service.events()
                        .list(
                            calendarId=cal_id,
                            timeMin=start_date.isoformat(),
                            timeMax=end_date.isoformat(),
                            singleEvents=True,
                            orderBy="startTime",
                        )
                        .execute()
                    )

                    events = events_result.get("items", [])
                    all_events.extend(events)
                    logger.info(f"Found {len(events)} events in calendar {cal_id}")

                except HttpError as e:
                    logger.error(f"Error accessing calendar {cal_id}: {e}")

            logger.info(f"Found {len(all_events)} total events to work around")

            # Find free slots (same logic as before, but with all events)
            free_slots = []
            current_date = start_date.date()

            while current_date <= end_date.date():
                if exclude_weekends and current_date.weekday() >= 5:
                    current_date += datetime.timedelta(days=1)
                    continue

                day_start = user_tz.localize(datetime.datetime.combine(
                    current_date,
                    datetime.time(hour=work_hours_start, minute=0)
                ))

                day_end = user_tz.localize(datetime.datetime.combine(
                    current_date,
                    datetime.time(hour=work_hours_end, minute=0)
                ))

                if day_start < start_date:
                    day_start = start_date

                # Get events for this specific day from all calendars
                day_events = []
                for event in all_events:
                    event_start = event.get('start', {})
                    if 'dateTime' in event_start:
                        event_datetime = datetime.datetime.fromisoformat(
                            event_start['dateTime'].replace('Z', '+00:00')
                        )
                        event_datetime_local = event_datetime.astimezone(user_tz)
                        if event_datetime_local.date() == current_date:
                            day_events.append(event)

                day_events.sort(key=lambda x: x['start']['dateTime'])

                # Find gaps between events
                current_time = day_start

                for event in day_events:
                    event_start = datetime.datetime.fromisoformat(
                        event['start']['dateTime'].replace('Z', '+00:00')
                    ).astimezone(user_tz)

                    event_end = datetime.datetime.fromisoformat(
                        event['end']['dateTime'].replace('Z', '+00:00')
                    ).astimezone(user_tz)

                    # Check gap before this event
                    if event_start > current_time:
                        gap_duration = (event_start - current_time).total_seconds() / 60
                        if gap_duration >= duration_minutes:
                            slot_end = min(event_start, current_time + datetime.timedelta(minutes=duration_minutes))

                            free_slots.append({
                                "start_time": current_time.replace(tzinfo=None).isoformat(),
                                "end_time": slot_end.replace(tzinfo=None).isoformat(),
                                "duration_minutes": int((slot_end - current_time).total_seconds() / 60),
                                "date": current_time.strftime('%B %d, %Y'),
                                "time": f"{current_time.strftime('%I:%M %p')} - {slot_end.strftime('%I:%M %p')}"
                            })

                    current_time = max(current_time, event_end)

                # Check gap after last event until end of work day
                if current_time < day_end:
                    gap_duration = (day_end - current_time).total_seconds() / 60
                    if gap_duration >= duration_minutes:
                        slot_end = min(day_end, current_time + datetime.timedelta(minutes=duration_minutes))

                        free_slots.append({
                            "start_time": current_time.replace(tzinfo=None).isoformat(),
                            "end_time": slot_end.replace(tzinfo=None).isoformat(),
                            "duration_minutes": int((slot_end - current_time).total_seconds() / 60),
                            "date": current_time.strftime('%B %d, %Y'),
                            "time": f"{current_time.strftime('%I:%M %p')} - {slot_end.strftime('%I:%M %p')}"
                        })

                current_date += datetime.timedelta(days=1)

            # Limit results to prevent overwhelming responses
            free_slots = free_slots[:10]

            if not free_slots:
                logger.info(f"No free slots found for {duration_minutes} minutes")
                return json.dumps({
                    "free_slots": [],
                    "message": f"No free time slots of {duration_minutes} minutes found in the next {search_days} days",
                    "calendars_checked": calendars_to_check
                })

            logger.info(f"✅ Found {len(free_slots)} free time slots")
            return json.dumps({
                "free_slots": free_slots,
                "message": f"Found {len(free_slots)} available time slots",
                "calendars_checked": calendars_to_check
            })

        except HttpError as error:
            logger.error(f"Google Calendar API error: {error}")
            return json.dumps({"error": f"Google Calendar API error: {error}"})
        except Exception as error:
            logger.error(f"Unexpected error in find_free_time: {error}")
            return json.dumps({"error": f"Failed to find free time: {error}"})

    def list_day_events(
            self,
            date: str = datetime.date.today().isoformat(),
            calendar_id: str = "primary",
            calendar_ids: Optional[List[str]] = None
    ) -> str:
        """
        Get events for a specific date from one or multiple calendars using USER'S TIMEZONE.

        Args:
            date (str): Date in YYYY-MM-DD format
            calendar_id (str): Single calendar to query (default: "primary")
            calendar_ids (List[str], optional): Multiple calendars to query
                                               If provided, overrides calendar_id

        Agent Usage Examples:
            # Get from primary calendar (unchanged behavior)
            list_day_events(date="2025-05-30")

            # Get from specific calendar
            list_day_events(date="2025-05-30", calendar_id="work@company.com")

            # Get from multiple calendars
            list_day_events(date="2025-05-30", calendar_ids=["primary", "work@company.com"])
        """
        try:
            self._ensure_authenticated()

            # Get user's timezone
            user_timezone_str = self._get_user_timezone()
            try:
                user_tz = pytz.timezone(user_timezone_str)
            except:
                user_tz = pytz.UTC

            # Parse the target date
            try:
                target_date = datetime.datetime.fromisoformat(date).date()
            except ValueError:
                return json.dumps({"error": f"Invalid date format: {date}. Use YYYY-MM-DD format."})

            # Get date range (start and end of the specific date) in USER'S timezone
            day_start = user_tz.localize(datetime.datetime.combine(target_date, datetime.time.min))
            day_end = user_tz.localize(datetime.datetime.combine(target_date, datetime.time.max))

            # Determine which calendars to query
            if calendar_ids:
                calendars_to_query = calendar_ids
                logger.info(f"Fetching events for {target_date.isoformat()} from multiple calendars: {calendar_ids}")
            else:
                calendars_to_query = [calendar_id]
                logger.info(f"Fetching events for {target_date.isoformat()} from calendar: {calendar_id}")

            all_events = []
            calendar_info = {}

            # Query each calendar
            for cal_id in calendars_to_query:
                try:
                    if not self._validate_calendar_access(cal_id):
                        logger.warning(f"No access to calendar: {cal_id}")
                        calendar_info[cal_id] = {"error": "No access to this calendar"}
                        continue

                    # Get events for the specific date
                    events_result = (
                        self.service.events()
                        .list(
                            calendarId=cal_id,
                            timeMin=day_start.isoformat(),
                            timeMax=day_end.isoformat(),
                            singleEvents=True,
                            orderBy="startTime",
                        )
                        .execute()
                    )

                    events = events_result.get("items", [])

                    # Filter to only events that actually START on the target date in user's timezone
                    target_date_events = []
                    for event in events:
                        event_start = event.get('start', {})
                        if 'dateTime' in event_start:
                            start_dt = datetime.datetime.fromisoformat(
                                event_start['dateTime'].replace('Z', '+00:00')
                            ).astimezone(user_tz)
                            if start_dt.date() == target_date:
                                event['_calendar_id'] = cal_id
                                target_date_events.append(event)
                        elif 'date' in event_start:
                            start_date = datetime.datetime.fromisoformat(event_start['date']).date()
                            if start_date == target_date:
                                event['_calendar_id'] = cal_id
                                target_date_events.append(event)

                    all_events.extend(target_date_events)
                    calendar_info[cal_id] = {
                        "event_count": len(target_date_events),
                        "calendar_name": events_result.get("summary", cal_id)
                    }

                except HttpError as e:
                    logger.error(f"Error accessing calendar {cal_id}: {e}")
                    calendar_info[cal_id] = {"error": f"Calendar API error: {str(e)}"}

            # Sort events by start time
            all_events.sort(key=lambda x: x.get('start', {}).get('dateTime', x.get('start', {}).get('date', '')))

            # Format the date for response
            formatted_date = target_date.strftime("%A, %B %d, %Y")

            if not all_events:
                logger.info(f"No events found for {target_date.isoformat()}")
                return json.dumps({
                    "message": f"No events scheduled for {formatted_date}",
                    "events": [],
                    "date": formatted_date,
                    "calendar_info": calendar_info
                })

            logger.info(f"Found {len(all_events)} events for {target_date.isoformat()}")
            return json.dumps({
                "message": f"Found {len(all_events)} events for {formatted_date}",
                "events": all_events,
                "date": formatted_date,
                "calendar_info": calendar_info
            })

        except HttpError as error:
            logger.error(f"Google Calendar API error: {error}")
            return json.dumps({"error": f"Google Calendar API error: {error}"})
        except Exception as error:
            logger.error(f"Unexpected error in list_day_events: {error}")
            return json.dumps({"error": f"Failed to get events for specified date: {error}"})

    # ========================= AUTHENTICATION ======================

    def is_authenticated(self) -> bool:
        """
        Check if the user is authenticated with Google Calendar

        Returns:
            bool: True if authenticated, False otherwise
        """
        return self.auth.is_authenticated()

    def logout(self):
        """
        Logout the user (removes saved token)
        """
        self.auth.logout()
        self.service = None
        logger.info(f"User {self.user_id} logged out from Google Calendar")

    def get_auth_status(self) -> dict:
        """
        Get authentication status for debugging

        Returns:
            dict: Authentication status information
        """
        return {
            "user_id": self.user_id,
            "authenticated": self.is_authenticated(),
            "service_available": self.service is not None,
            "token_path": self.auth.token_path
        }


# Example usage:
if __name__ == "__main__":
    # Test the updated GoogleCalendarTools
    user_id = "test_user_123"

    try:
        # Create the tools instance
        calendar_tools = GoogleCalendarTools(user_id=user_id)

        # Test authentication status
        print("Auth Status:", calendar_tools.get_auth_status())

        # Test listing calendars
        calendars_json = calendar_tools.list_calendars()
        print("Calendars:", calendars_json)

        # Test listing events from primary calendar
        events_json = calendar_tools.list_events(limit=5)
        print("Events:", events_json)

        # Test listing events from multiple calendars
        # events_json = calendar_tools.list_events(calendar_ids=["primary", "work@company.com"], limit=5)
        # print("Multi-calendar Events:", events_json)

        # For debugging - print events nicely
        print("\n" + "=" * 50)
        print("FORMATTED EVENTS:")
        print("=" * 50)
        data = json.loads(events_json)
        for event in data.get('events', []):
            print(print_event(event))

    except Exception as e:
        print(f"❌ Error: {e}")