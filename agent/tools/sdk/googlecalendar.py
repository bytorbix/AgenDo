# agent/tools/sdk/googlecalendar.py

import datetime
import json
import uuid
from typing import List, Optional, Dict, Any

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

    def create_event(
            self,
            start_datetime: str,
            end_datetime: str,
            title: Optional[str] = None,
            description: Optional[str] = None,
            location: Optional[str] = None,
            timezone: Optional[str] = None,
            attendees: List[str] = [],
            send_updates: Optional[str] = "all",
            add_google_meet_link: Optional[bool] = False,
    ) -> str:
        """
        Create a new event in the user's primary calendar.

        Args:
            start_datetime (str): Start date and time in ISO format
            end_datetime (str): End date and time in ISO format
            title (str, optional): Title of the event
            description (str, optional): Detailed description of the event
            location (str, optional): Location of the event
            timezone (str, optional): Timezone for the event
            attendees (List[str]): List of attendee email addresses
            send_updates (str): Whether to send updates to attendees ('all', 'externalOnly', 'none')
            add_google_meet_link (bool): Whether to add a Google Meet link

        Returns:
            JSON string with created event details or error message
        """
        try:
            # Ensure we're authenticated
            self._ensure_authenticated()

            # Prepare attendees list
            attendees_list = [{"email": attendee} for attendee in attendees] if attendees else []

            # Format datetime strings and handle timezone
            try:
                start_time = datetime.datetime.fromisoformat(start_datetime).strftime("%Y-%m-%dT%H:%M:%S")
                end_time = datetime.datetime.fromisoformat(end_datetime).strftime("%Y-%m-%dT%H:%M:%S")

                # Default timezone if not provided
                if not timezone:
                    timezone = "UTC"  # Default to UTC if no timezone specified

            except ValueError as e:
                return json.dumps({"error": f"Invalid datetime format: {str(e)}"})

            # Build event object
            event = {
                "summary": title or "New Event",
                "location": location,
                "description": description,
                "start": {"dateTime": start_time, "timeZone": timezone},
                "end": {"dateTime": end_time, "timeZone": timezone},
                "attendees": attendees_list,
            }

            # Add Google Meet link if requested
            if add_google_meet_link:
                event["conferenceData"] = {
                    "createRequest": {
                        "requestId": str(uuid.uuid4()),
                        "conferenceSolutionKey": {"type": "hangoutsMeet"}
                    }
                }

            logger.info(f"Creating event '{title}' for user {self.user_id}")

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

            logger.info(f"✅ Event created successfully: {event_result.get('id')}")
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
            timezone: Optional[str] = None,
            attendees: Optional[List[str]] = None,
            send_updates: Optional[str] = "all",
    ) -> str:
        """
        Update an existing event in the user's primary calendar.

        Args:
            event_id (str): ID of the event to update
            title (str, optional): New title of the event
            description (str, optional): New description of the event
            location (str, optional): New location of the event
            start_datetime (str, optional): New start date and time in ISO format
            end_datetime (str, optional): New end date and time in ISO format
            timezone (str, optional): New timezone for the event
            attendees (List[str], optional): New list of attendee email addresses
            send_updates (str): Whether to send updates to attendees ('all', 'externalOnly', 'none')

        Returns:
            JSON string with updated event details or error message
        """
        try:
            # Ensure we're authenticated
            self._ensure_authenticated()

            # First, get the existing event
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

            logger.info(f"Updating event {event_id} for user {self.user_id}")

            # Update only the fields that were provided
            if title is not None:
                existing_event['summary'] = title

            if description is not None:
                existing_event['description'] = description

            if location is not None:
                existing_event['location'] = location

            if start_datetime is not None and end_datetime is not None:
                try:
                    start_time = datetime.datetime.fromisoformat(start_datetime).strftime("%Y-%m-%dT%H:%M:%S")
                    end_time = datetime.datetime.fromisoformat(end_datetime).strftime("%Y-%m-%dT%H:%M:%S")
                    existing_event['start'] = {"dateTime": start_time, "timeZone": timezone}
                    existing_event['end'] = {"dateTime": end_time, "timeZone": timezone}
                except ValueError as e:
                    return json.dumps({"error": f"Invalid datetime format: {str(e)}"})

            if attendees is not None:
                existing_event['attendees'] = [{"email": attendee} for attendee in attendees]

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

            logger.info(f"✅ Event {event_id} updated successfully")
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

    def find_free_time(
            self,
            duration_minutes: int,
            search_days: int = 7,
            work_hours_start: int = 9,
            work_hours_end: int = 17,
            exclude_weekends: bool = True
    ) -> str:
        """
        Find available time slots for scheduling new events.

        TIMEZONE FIXED VERSION - handles timezone-aware datetimes properly
        """
        try:
            # Ensure we're authenticated
            self._ensure_authenticated()

            logger.info(f"Finding {duration_minutes} min free slots for user {self.user_id}")

            # Calculate search date range - make timezone-aware from the start
            from datetime import timezone

            start_date = datetime.datetime.now(timezone.utc)
            end_date = start_date + datetime.timedelta(days=search_days)

            # Get all events in the search period
            events_result = (
                self.service.events()
                .list(
                    calendarId="primary",
                    timeMin=start_date.isoformat(),  # Already has timezone info
                    timeMax=end_date.isoformat(),  # Already has timezone info
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
                if exclude_weekends and current_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
                    current_date += datetime.timedelta(days=1)
                    continue

                # Define work hours for this day - make timezone-aware
                day_start = datetime.datetime.combine(
                    current_date,
                    datetime.time(hour=work_hours_start, minute=0)
                ).replace(tzinfo=timezone.utc)  # Make timezone-aware

                day_end = datetime.datetime.combine(
                    current_date,
                    datetime.time(hour=work_hours_end, minute=0)
                ).replace(tzinfo=timezone.utc)  # Make timezone-aware

                # Don't search in the past
                if day_start < start_date:
                    day_start = start_date

                # Get events for this specific day
                day_events = []
                for event in events:
                    event_start = event.get('start', {})
                    if 'dateTime' in event_start:
                        # Parse timezone-aware datetime from Google Calendar
                        event_date = datetime.datetime.fromisoformat(
                            event_start['dateTime'].replace('Z', '+00:00')
                        ).date()
                        if event_date == current_date:
                            day_events.append(event)

                # Sort events by start time
                day_events.sort(key=lambda x: x['start']['dateTime'])

                # Find gaps between events
                current_time = day_start

                for event in day_events:
                    # Parse timezone-aware datetimes
                    event_start = datetime.datetime.fromisoformat(
                        event['start']['dateTime'].replace('Z', '+00:00')
                    )
                    event_end = datetime.datetime.fromisoformat(
                        event['end']['dateTime'].replace('Z', '+00:00')
                    )

                    # Check gap before this event
                    if event_start > current_time:
                        gap_duration = (event_start - current_time).total_seconds() / 60
                        if gap_duration >= duration_minutes:
                            # Found a suitable slot
                            slot_end = min(event_start, current_time + datetime.timedelta(minutes=duration_minutes))

                            # Convert back to local time for display (remove timezone for user-friendly display)
                            display_start = current_time.replace(tzinfo=None)
                            display_end = slot_end.replace(tzinfo=None)

                            free_slots.append({
                                "start_time": display_start.isoformat(),
                                "end_time": display_end.isoformat(),
                                "duration_minutes": int((slot_end - current_time).total_seconds() / 60),
                                "date": display_start.strftime('%B %d, %Y'),
                                "time": f"{display_start.strftime('%I:%M %p')} - {display_end.strftime('%I:%M %p')}"
                            })

                    # Move past this event
                    current_time = max(current_time, event_end)

                # Check gap after last event until end of work day
                if current_time < day_end:
                    gap_duration = (day_end - current_time).total_seconds() / 60
                    if gap_duration >= duration_minutes:
                        slot_end = min(day_end, current_time + datetime.timedelta(minutes=duration_minutes))

                        # Convert back to local time for display
                        display_start = current_time.replace(tzinfo=None)
                        display_end = slot_end.replace(tzinfo=None)

                        free_slots.append({
                            "start_time": display_start.isoformat(),
                            "end_time": display_end.isoformat(),
                            "duration_minutes": int((slot_end - current_time).total_seconds() / 60),
                            "date": display_start.strftime('%B %d, %Y'),
                            "time": f"{display_start.strftime('%I:%M %p')} - {display_end.strftime('%I:%M %p')}"
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
        Get events scheduled for ONE SPECIFIC DATE only (not a range).

        IMPORTANT FOR AI AGENTS:
        This function returns ONLY events that are happening on the specified date.
        Use this for queries like:
        - "What do I have today?" → list_day_events()
        - "What do I have tomorrow?" → list_day_events(date="2025-05-23")
        - "What's on my schedule on Friday?" → list_day_events(date="2025-05-24")
        - "Am I busy on June 1st?" → list_day_events(date="2025-06-01")

        For upcoming events or date ranges, use list_events() instead.

        Args:
            date (str): Specific date in ISO format (YYYY-MM-DD).
                       Defaults to today if not specified.
                       Examples: "2025-05-22", "2025-06-01"

        Returns:
            JSON string containing:
            - On success: {"message": "Found X events for [date]", "events": [...], "date": "May 22, 2025"}
            - If no events: {"message": "No events scheduled for [date]", "events": [], "date": "May 22, 2025"}
            - On error: {"error": "descriptive error message"}

        AI Usage Examples:
        - User: "What do I have today?" → list_day_events()
        - User: "What do I have tomorrow?" → list_day_events(date="2025-05-23")
        - User: "Am I free on Friday?" → list_day_events(date="2025-05-24")
        """
        try:
            # Ensure we're authenticated
            self._ensure_authenticated()

            # Parse the target date
            try:
                target_date = datetime.datetime.fromisoformat(date).date()
            except ValueError:
                return json.dumps({"error": f"Invalid date format: {date}. Use YYYY-MM-DD format."})

            # Get date range (start and end of the specific date)
            date_start = datetime.datetime.combine(target_date, datetime.time.min)
            date_end = datetime.datetime.combine(target_date, datetime.time.max)

            logger.info(f"Fetching events for {target_date.isoformat()} for user {self.user_id}")

            # Get events for the specific date only
            events_result = (
                self.service.events()
                .list(
                    calendarId="primary",
                    timeMin=date_start.isoformat() + 'Z',
                    timeMax=date_end.isoformat() + 'Z',
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            events = events_result.get("items", [])

            # Filter to only events that actually START on the target date
            target_date_events = []
            for event in events:
                event_start = event.get('start', {})
                if 'dateTime' in event_start:
                    # Regular timed event
                    start_dt = datetime.datetime.fromisoformat(event_start['dateTime'].replace('Z', '+00:00'))
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
                logger.info(f"No events found for {target_date.isoformat()} for user {self.user_id}")
                return json.dumps({
                    "message": f"No events scheduled for {formatted_date}",
                    "events": [],
                    "date": formatted_date
                })

            logger.info(f"Found {len(target_date_events)} events for {target_date.isoformat()} for user {self.user_id}")
            return json.dumps({
                "message": f"Found {len(target_date_events)} events for {formatted_date}",
                "events": target_date_events,
                "date": formatted_date
            })

        except HttpError as error:
            logger.error(f"Google Calendar API error: {error}")
            return json.dumps({"error": f"Google Calendar API error: {error}"})
        except Exception as error:
            logger.error(f"Unexpected error in get_today_events: {error}")
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