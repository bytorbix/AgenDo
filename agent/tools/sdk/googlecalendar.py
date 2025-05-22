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
        self.register(self.list_events)
        self.register(self.create_event)
        self.register(self.update_event)
        self.register(self.delete_event)
        self.register(self.get_event)
        self.register(self.find_free_time)
        self.register(self.list_day_events)
        self.register(self.test_timezone_detection)

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

    # ========================= EVENTS ======================

    def list_events(self, limit: int = 10, date_from: str = datetime.date.today().isoformat()) -> str:
        """
        List events from the user's calendar within a DATE RANGE (from a specific date onwards).

        IMPORTANT FOR AI AGENTS:
        This function returns events FROM the specified date ONWARDS (not just on that date).
        Use this for queries like:
        - "What's coming up this week?"
        - "Show me upcoming events"
        - "What do I have starting from tomorrow?"

        For TODAY ONLY events, use get_today_events() instead.

        Args:
            limit (int): Number of events to return, default is 10
            date_from (str): Start date in ISO format (YYYY-MM-DD). Events from this date onwards will be returned.
                           Default is today's date.

        Returns:
            JSON string with events starting from the specified date onwards or error message

        AI Usage Examples:
        - "What's coming up?" → list_events()
        - "What do I have next week?" → list_events(date_from="2025-05-29")
        - "Show me 5 upcoming events" → list_events(limit=5)
        """
        try:
            # Ensure we're authenticated
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

            # Get events from Google Calendar
            logger.info(f"Fetching {limit} events from {date_from} for user {self.user_id}")

            events_result = (
                self.service.events()
                .list(
                    calendarId="primary",
                    timeMin=date_from,
                    maxResults=limit,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            events = events_result.get("items", [])

            if not events:
                logger.info(f"No upcoming events found for user {self.user_id}")
                return json.dumps({"message": "No upcoming events found", "events": []})

            logger.info(f"Found {len(events)} events for user {self.user_id}")
            return json.dumps({"message": f"Found {len(events)} events", "events": events})

        except HttpError as error:
            logger.error(f"Google Calendar API error: {error}")
            return json.dumps({"error": f"Google Calendar API error: {error}"})
        except Exception as error:
            logger.error(f"Unexpected error in list_events: {error}")
            return json.dumps({"error": f"Failed to list events: {error}"})

    # Replace your create_event method with this version that handles timezone 100% automatically

    def create_event(
            self,
            start_datetime: str,
            end_datetime: str,
            title: Optional[str] = None,
            description: Optional[str] = None,
            location: Optional[str] = None,
            timezone: Optional[str] = None,  # IGNORED - we always auto-detect
            attendees: List[str] = [],
            send_updates: Optional[str] = "all",
            add_google_meet_link: Optional[bool] = False,
    ) -> str:
        """
        Create event with AUTOMATIC timezone detection - never fails
        """
        try:
            self._ensure_authenticated()

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

            # Create the event
            event_result = (
                self.service.events()
                .insert(
                    calendarId="primary",
                    body=event,
                    sendUpdates=send_updates,
                    conferenceDataVersion=1 if add_google_meet_link else 0,
                )
                .execute()
            )

            logger.info(f"✅ Event created with timezone {user_timezone}")
            return json.dumps({
                "message": "Event created successfully",
                "event": event_result
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
            timezone: Optional[str] = None,  # IGNORED - we always auto-detect
            attendees: Optional[List[str]] = None,
            send_updates: Optional[str] = "all",
    ) -> str:
        """
        Update event with AUTOMATIC timezone detection - never fails
        """
        try:
            self._ensure_authenticated()

            # Get existing event
            try:
                existing_event = self.service.events().get(
                    calendarId="primary",
                    eventId=event_id
                ).execute()
            except HttpError as e:
                if e.resp.status == 404:
                    return json.dumps({"error": f"Event with ID {event_id} not found"})
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

            # Update the event
            updated_event = (
                self.service.events()
                .update(
                    calendarId="primary",
                    eventId=event_id,
                    body=existing_event,
                    sendUpdates=send_updates,
                )
                .execute()
            )

            logger.info(f"✅ Event updated with timezone {user_timezone}")
            return json.dumps({
                "message": "Event updated successfully",
                "event": updated_event
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
            send_updates: Optional[str] = "all"
    ) -> str:
        """
        Delete an event from the user's primary calendar.

        Args:
            event_id (str): ID of the event to delete
            send_updates (str): Whether to send updates to attendees ('all', 'externalOnly', 'none')

        Returns:
            JSON string with success message or error message
        """
        try:
            # Ensure we're authenticated
            self._ensure_authenticated()

            logger.info(f"Deleting event {event_id} for user {self.user_id}")

            # Delete the event
            self.service.events().delete(
                calendarId="primary",
                eventId=event_id,
                sendUpdates=send_updates
            ).execute()

            logger.info(f"✅ Event {event_id} deleted successfully")
            return json.dumps({
                "message": f"Event {event_id} deleted successfully"
            })

        except HttpError as error:
            if error.resp.status == 404:
                logger.warning(f"Event {event_id} not found")
                return json.dumps({"error": f"Event with ID {event_id} not found"})
            else:
                logger.error(f"Google Calendar API error: {error}")
                return json.dumps({"error": f"Google Calendar API error: {error}"})
        except Exception as error:
            logger.error(f"Unexpected error in delete_event: {error}")
            return json.dumps({"error": f"Failed to delete event: {error}"})

    def get_event(self, event_id: str) -> str:
        """
        Get details of a specific calendar event by ID.

        IMPORTANT FOR AI:
        - First call list_events() to see available events
        - Copy the "id" field from the event you want
        - Then use that ID in this function

        Typical AI workflow:
        1. events = list_events()
        2. Find desired event in results
        3. event_id = events['events'][0]['id']
        4. details = get_event(event_id)

        Args:
            event_id (str): Event ID from list_events() response

        Example:
            # Step 1: Get events list
            events = list_events()
            # Step 2: Extract ID (e.g., "6b20focpa932fjsm9mia7ksat0")
            # Step 3: Get specific event
            details = get_event("6b20focpa932fjsm9mia7ksat0")
        """
        try:
            # Ensure we're authenticated
            self._ensure_authenticated()

            logger.info(f"Fetching event {event_id} for user {self.user_id}")

            # Get the specific event
            event = self.service.events().get(
                calendarId="primary",
                eventId=event_id
            ).execute()

            logger.info(f"✅ Event {event_id} retrieved successfully")
            return json.dumps({
                "event": event
            })

        except HttpError as error:
            if error.resp.status == 404:
                logger.warning(f"Event {event_id} not found")
                return json.dumps({
                    "error": f"Event with ID {event_id} not found. Use list_events() to see available events."
                })
            else:
                logger.error(f"Google Calendar API error: {error}")
                return json.dumps({"error": f"Google Calendar API error: {error}"})
        except Exception as error:
            logger.error(f"Unexpected error in get_event: {error}")
            return json.dumps({"error": f"Failed to get event: {error}"})

    # Replace both methods in your googlecalendar.py with these timezone-aware versions

    def find_free_time(
            self,
            duration_minutes: int,
            search_days: int = 7,
            work_hours_start: int = 9,
            work_hours_end: int = 17,
            exclude_weekends: bool = True
    ) -> str:
        """
        Find available time slots using USER'S TIMEZONE (not UTC)
        """
        try:
            # Ensure we're authenticated
            self._ensure_authenticated()

            logger.info(f"Finding {duration_minutes} min free slots for user {self.user_id}")

            # Get user's timezone first
            user_timezone_str = self._get_user_timezone()
            try:
                user_tz = pytz.timezone(user_timezone_str)
            except:
                user_tz = pytz.UTC  # Fallback to UTC if timezone parsing fails

            logger.info(f"Using user timezone: {user_timezone_str}")

            # Calculate search date range in USER'S timezone
            start_date = datetime.datetime.now(user_tz)
            end_date = start_date + datetime.timedelta(days=search_days)

            # Get all events in the search period
            events_result = (
                self.service.events()
                .list(
                    calendarId="primary",
                    timeMin=start_date.isoformat(),
                    timeMax=end_date.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            events = events_result.get("items", [])
            logger.info(f"Found {len(events)} existing events to work around")

            # Find free slots
            free_slots = []
            current_date = start_date.date()

            while current_date <= end_date.date():
                # Skip weekends if requested
                if exclude_weekends and current_date.weekday() >= 5:
                    current_date += datetime.timedelta(days=1)
                    continue

                # Define work hours for this day in USER'S timezone
                day_start = user_tz.localize(datetime.datetime.combine(
                    current_date,
                    datetime.time(hour=work_hours_start, minute=0)
                ))

                day_end = user_tz.localize(datetime.datetime.combine(
                    current_date,
                    datetime.time(hour=work_hours_end, minute=0)
                ))

                # Don't search in the past
                if day_start < start_date:
                    day_start = start_date

                # Get events for this specific day
                day_events = []
                for event in events:
                    event_start = event.get('start', {})
                    if 'dateTime' in event_start:
                        # Parse timezone-aware datetime from Google Calendar
                        event_datetime = datetime.datetime.fromisoformat(
                            event_start['dateTime'].replace('Z', '+00:00')
                        )
                        # Convert to user's timezone for comparison
                        event_datetime_local = event_datetime.astimezone(user_tz)
                        if event_datetime_local.date() == current_date:
                            day_events.append(event)

                # Sort events by start time
                day_events.sort(key=lambda x: x['start']['dateTime'])

                # Find gaps between events
                current_time = day_start

                for event in day_events:
                    # Parse timezone-aware datetimes and convert to user timezone
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
                            # Found a suitable slot
                            slot_end = min(event_start, current_time + datetime.timedelta(minutes=duration_minutes))

                            free_slots.append({
                                "start_time": current_time.replace(tzinfo=None).isoformat(),
                                "end_time": slot_end.replace(tzinfo=None).isoformat(),
                                "duration_minutes": int((slot_end - current_time).total_seconds() / 60),
                                "date": current_time.strftime('%B %d, %Y'),
                                "time": f"{current_time.strftime('%I:%M %p')} - {slot_end.strftime('%I:%M %p')}"
                            })

                    # Move past this event
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
                    "message": f"No free time slots of {duration_minutes} minutes found in the next {search_days} days"
                })

            logger.info(f"✅ Found {len(free_slots)} free time slots")
            return json.dumps({
                "free_slots": free_slots,
                "message": f"Found {len(free_slots)} available time slots"
            })

        except HttpError as error:
            logger.error(f"Google Calendar API error: {error}")
            return json.dumps({"error": f"Google Calendar API error: {error}"})
        except Exception as error:
            logger.error(f"Unexpected error in find_free_time: {error}")
            return json.dumps({"error": f"Failed to find free time: {error}"})

    def list_day_events(self, date: str = datetime.date.today().isoformat()) -> str:
        """
        Get events for a specific date using USER'S TIMEZONE
        """
        try:
            # Ensure we're authenticated
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

            logger.info(f"Fetching events for {target_date.isoformat()} in timezone {user_timezone_str}")

            # Get events for the specific date
            events_result = (
                self.service.events()
                .list(
                    calendarId="primary",
                    timeMin=day_start.isoformat(),  # No more forcing 'Z'
                    timeMax=day_end.isoformat(),  # Use user's timezone
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
                    # Regular timed event - convert to user's timezone
                    start_dt = datetime.datetime.fromisoformat(
                        event_start['dateTime'].replace('Z', '+00:00')
                    ).astimezone(user_tz)
                    if start_dt.date() == target_date:
                        target_date_events.append(event)
                elif 'date' in event_start:
                    # All-day event
                    start_date = datetime.datetime.fromisoformat(event_start['date']).date()
                    if start_date == target_date:
                        target_date_events.append(event)

            # Format the date for response
            formatted_date = target_date.strftime("%A, %B %d, %Y")

            if not target_date_events:
                logger.info(f"No events found for {target_date.isoformat()}")
                return json.dumps({
                    "message": f"No events scheduled for {formatted_date}",
                    "events": [],
                    "date": formatted_date
                })

            logger.info(f"Found {len(target_date_events)} events for {target_date.isoformat()}")
            return json.dumps({
                "message": f"Found {len(target_date_events)} events for {formatted_date}",
                "events": target_date_events,
                "date": formatted_date
            })

        except HttpError as error:
            logger.error(f"Google Calendar API error: {error}")
            return json.dumps({"error": f"Google Calendar API error: {error}"})
        except Exception as error:
            logger.error(f"Unexpected error in list_day_events: {error}")
            return json.dumps({"error": f"Failed to get events for specified date: {error}"})


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

        # Test listing events
        events_json = calendar_tools.list_events(limit=5)
        print("Events:", events_json)

        # For debugging - print events nicely
        print("\n" + "=" * 50)
        print("FORMATTED EVENTS:")
        print("=" * 50)
        data = json.loads(events_json)
        for event in data.get('events', []):
            print(print_event(event))

        # Test update and delete (uncomment to test with real event ID)
        """
        # Example: Update an event (replace with real event ID)
        event_id = "your_event_id_here"
        update_result = calendar_tools.update_event(
            event_id=event_id,
            title="Updated Event Title",
            description="Updated description"
        )
        print(f"\nUpdate Result: {update_result}")

        # Example: Delete an event (replace with real event ID)  
        delete_result = calendar_tools.delete_event(event_id=event_id)
        print(f"Delete Result: {delete_result}")
        """

    except Exception as e:
        print(f"❌ Error: {e}")