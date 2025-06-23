import datetime
import json
import os.path
from functools import wraps
from typing import Optional

from agno.tools import Toolkit
from agno.utils.log import logger

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore
    from googleapiclient.discovery import build  # type: ignore
    from googleapiclient.errors import HttpError  # type: ignore
except ImportError:
    raise ImportError(
        "Google client library for Python not found , install it using `pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib`"
    )

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def authenticated(func):
    """Decorator to ensure authentication before executing the method."""

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        # Ensure credentials are valid
        if os.path.exists(self.token_path):
            self.creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.creds_path, SCOPES)
                self.creds = flow.run_local_server(port=0)
                # Save the credentials for future use
            with open(self.token_path, "w") as token:
                token.write(self.creds.to_json())

            # Initialize the Google Calendar service
        try:
            self.service = build("calendar", "v3", credentials=self.creds)
        except HttpError as error:
            logger.error(f"An error occurred while creating the service: {error}")
            raise

        # Ensure the service is available
        if not self.service:
            raise ValueError("Google Calendar service could not be initialized.")

        return func(self, *args, **kwargs)

    return wrapper


class GoogleCalendarTools(Toolkit):
    def __init__(
            self,
            credentials_path: Optional[str] = None,
            token_path: Optional[str] = None,
            **kwargs,
    ):
        """
        Google Calendar Tool.

        :param credentials_path: Path of the file credentials.json file which contains OAuth 2.0 Client ID. A client ID is used to identify a single app to Google's OAuth servers. If your app runs on multiple platforms, you must create a separate client ID for each platform. Refer doc https://developers.google.com/calendar/api/quickstart/python#authorize_credentials_for_a_desktop_application
        :param token_path: Path of the file token.json which stores the user's access and refresh tokens, and is created automatically when the authorization flow completes for the first time.

        """

        if not credentials_path:
            logger.error(
                "Google Calendar Tool : Please Provide Valid Credentials Path , You can refer https://developers.google.com/calendar/api/quickstart/python#authorize_credentials_for_a_desktop_application to create your credentials"
            )
            raise ValueError("Credential path is required")
        elif not os.path.exists(credentials_path):
            logger.error(
                "Google Calendar Tool : Credential file Path is invalid , please provide the full path of the credentials json file"
            )
            raise ValueError("Credentials Path is invalid")

        if not token_path:
            logger.warning(
                f"Google Calendar Tool : Token path is not provided, using {os.getcwd()}/token.json as default path"
            )
            token_path = "agendo/config/credentials/token.json"

        self.creds = None
        self.service = None
        self.token_path = token_path
        self.creds_path = credentials_path

        super().__init__(**kwargs)

        # Register all SDK methods as tools
        self.register(self.list_calendars)
        self.register(self.list_events)
        self.register(self.create_event)
        self.register(self.update_event)
        self.register(self.delete_event)
        self.register(self.get_event_by_id)
        self.register(self.search_events)

    @staticmethod
    def _parse_event(events_json: str, calendar_name: str = "Google Calendar") -> str:
        """
        Parse Google Calendar events JSON into simplified format for AI agent consumption.

        Args:
            events_json: JSON string from Google Calendar API
            calendar_name: Name of the calendar these events belong to

        Returns:
            JSON string with simplified event information
        """
        try:
            events = json.loads(events_json)

            if isinstance(events, dict) and "error" in events:
                return events_json  # Return error as-is

            if not events:
                return json.dumps({"message": "No events found."})

            parsed_events = []
            for event in events:
                # Extract basic info
                title = event.get("summary", "No Title")
                description = event.get("description", "")
                event_type = event.get("eventType", "default")
                location = event.get("location", "")

                # Parse start and end times
                start_info = event.get("start", {})
                end_info = event.get("end", {})

                # Handle all-day events (date only) vs timed events (dateTime)
                if "date" in start_info:
                    # All-day event
                    start_date = start_info["date"]
                    end_date = end_info["date"]
                    time_info = f"All day: {start_date} to {start_date}"
                    if start_date != end_date:
                        # Multi-day event
                        end_display = datetime.datetime.fromisoformat(end_date) - datetime.timedelta(days=1)
                        time_info = f"All day: {start_date} to {end_display.strftime('%Y-%m-%d')}"
                else:
                    # Timed event
                    start_datetime = start_info.get("dateTime", "")
                    end_datetime = end_info.get("dateTime", "")

                    if start_datetime and end_datetime:
                        try:
                            start_dt = datetime.datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
                            end_dt = datetime.datetime.fromisoformat(end_datetime.replace('Z', '+00:00'))

                            # Format for readability
                            if start_dt.date() == end_dt.date():
                                # Same day
                                time_info = f"{start_dt.strftime('%Y-%m-%d %H:%M')} - {end_dt.strftime('%H:%M')}"
                            else:
                                # Multi-day
                                time_info = f"{start_dt.strftime('%Y-%m-%d %H:%M')} - {end_dt.strftime('%Y-%m-%d %H:%M')}"
                        except Exception as e:
                            time_info = f"Time parsing error: {e}"
                    else:
                        time_info = "Time not specified"

                # Build parsed event object
                parsed_event = {
                    "title": title,
                    "time": time_info,
                    "type": event_type,
                    "calendar": calendar_name
                }

                # Add optional fields only if they exist
                if location:
                    parsed_event["location"] = location

                if description:
                    # Truncate long descriptions
                    desc = description.strip()
                    if len(desc) > 100:
                        desc = desc[:100] + "..."
                    parsed_event["description"] = desc

                parsed_events.append(parsed_event)

            return json.dumps(parsed_events, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"Error parsing events: {e}")
            return json.dumps({"error": f"Error parsing events: {e}"})

    @authenticated
    def _get_calendar_id_by_name(self, calendar_identifier: str) -> str:
        """
        Helper method to get calendar ID by name or return the ID if already provided.

        Args:
            calendar_identifier: Either calendar name or calendar ID

        Returns:
            Calendar ID string
        """
        # If it already looks like a calendar ID (contains @ or is "primary"), return as-is
        if "@" in calendar_identifier or calendar_identifier == "primary":
            return calendar_identifier

        try:
            if self.service:
                calendars_result = self.service.calendarList().list().execute()
                calendars = calendars_result.get('items', [])

                # Search for calendar by name (case-insensitive)
                for calendar in calendars:
                    calendar_name = calendar.get("summary", "")
                    if calendar_name.lower() == calendar_identifier.lower():
                        return calendar.get("id", calendar_identifier)

                # If not found by exact match, try partial match
                for calendar in calendars:
                    calendar_name = calendar.get("summary", "")
                    if calendar_identifier.lower() in calendar_name.lower():
                        return calendar.get("id", calendar_identifier)

                # If still not found, return original identifier
                logger.warning(f"Calendar '{calendar_identifier}' not found, using as-is")
                return calendar_identifier
            else:
                return calendar_identifier
        except HttpError as error:
            logger.error(f"Error looking up calendar: {error}")
            return calendar_identifier

    @authenticated
    def list_calendars(self) -> str:
        """
        List all calendars available to the user.

        Returns:
            JSON string with calendar information
        """
        try:
            if self.service:
                calendars_result = self.service.calendarList().list().execute()
                calendars = calendars_result.get('items', [])

                if not calendars:
                    return json.dumps({"message": "No calendars found."})

                # Simplify calendar info
                simplified_calendars = []
                for calendar in calendars:
                    simplified_calendars.append({
                        "id": calendar.get("id"),
                        "name": calendar.get("summary"),
                        "description": calendar.get("description", ""),
                        "primary": calendar.get("primary", False),
                        "access_role": calendar.get("accessRole", ""),
                        "background_color": calendar.get("backgroundColor", "")
                    })

                return json.dumps(simplified_calendars, ensure_ascii=False, indent=2)
            else:
                return json.dumps({"error": "authentication issue"})
        except HttpError as error:
            logger.error(f"An error occurred: {error}")
            return json.dumps({"error": f"An error occurred: {error}"})

    @authenticated
    def list_events(
            self,
            limit: int = 10,
            date_from: str = datetime.date.today().isoformat(),
            calendar_id: str = "primary"
    ) -> str:
        """
        List events from the specified calendar.

        Args:
            limit (Optional[int]): Number of events to return, default value is 10
            date_from (str): the start date to return events from in date isoformat. Defaults to current datetime.
            calendar_id (str): ID or name of the calendar to list events from. Defaults to "primary".
        """
        # Resolve calendar name to ID if needed
        resolved_calendar_id = self._get_calendar_id_by_name(calendar_id)

        # Determine display name for the calendar
        if "@" not in calendar_id and calendar_id != "primary":
            # User provided a name, use it as display name
            calendar_display_name = calendar_id
        else:
            # User provided an ID, look up the display name
            calendar_display_name = self._get_calendar_id_by_name(resolved_calendar_id)

        if date_from is None:
            date_from = datetime.datetime.now(datetime.timezone.utc).isoformat()
        elif isinstance(date_from, str):
            date_from = datetime.datetime.fromisoformat(date_from).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        try:
            if self.service:
                events_result = (
                    self.service.events()
                    .list(
                        calendarId=resolved_calendar_id,
                        timeMin=date_from,
                        maxResults=limit,
                        singleEvents=True,
                        orderBy="startTime",
                    )
                    .execute()
                )
                events = events_result.get("items", [])
                if not events:
                    return f"No upcoming events found in calendar '{calendar_display_name}'."

                events_json = json.dumps(events)
                return self._parse_event(events_json, calendar_display_name)
            else:
                return json.dumps({"error": "authentication issue"})
        except HttpError as error:
            return json.dumps({"error": f"An error occurred: {error}"})

    @authenticated
    def create_event(
            self,
            start_datetime: str,
            end_datetime: str,
            title: Optional[str] = None,
            description: Optional[str] = None,
            location: Optional[str] = None,
            calendar_id: str = "primary"
    ) -> str:
        """
        Create a new event in the specified calendar.

        Args:
            start_datetime (str): start date and time of the event
            end_datetime (str): end date and time of the event
            title (Optional[str]): Title of the Event
            description (Optional[str]): Detailed description of the event
            location (Optional[str]): Location of the event
            calendar_id (str): ID or name of the calendar to create event in. Defaults to "primary".
        """
        # Resolve calendar name to ID if needed
        resolved_calendar_id = self._get_calendar_id_by_name(calendar_id)

        start_time = datetime.datetime.fromisoformat(start_datetime).strftime("%Y-%m-%dT%H:%M:%S")
        end_time = datetime.datetime.fromisoformat(end_datetime).strftime("%Y-%m-%dT%H:%M:%S")

        try:
            event = {
                "summary": title,
                "location": location,
                "description": description,
                "start": {"dateTime": start_time},
                "end": {"dateTime": end_time},
            }

            if self.service:
                event_result = (
                    self.service.events()
                    .insert(
                        calendarId=resolved_calendar_id,
                        body=event,
                    )
                    .execute()
                )
                return json.dumps(event_result)
            else:
                return json.dumps({"error": "authentication issue"})
        except HttpError as error:
            logger.error(f"An error occurred: {error}")
            return json.dumps({"error": f"An error occurred: {error}"})

    @authenticated
    def update_event(
            self,
            event_id: str,
            calendar_id: str = "primary",
            title: Optional[str] = None,
            description: Optional[str] = None,
            location: Optional[str] = None,
            start_datetime: Optional[str] = None,
            end_datetime: Optional[str] = None
    ) -> str:
        """
        Update an existing event in the specified calendar.

        Args:
            event_id (str): ID of the event to update
            calendar_id (str): ID or name of the calendar containing the event. Defaults to "primary".
            title (Optional[str]): New title for the event
            description (Optional[str]): New description for the event
            location (Optional[str]): New location for the event
            start_datetime (Optional[str]): New start date and time in ISO format
            end_datetime (Optional[str]): New end date and time in ISO format

        Returns:
            JSON string with updated event information or error message

        Example:
            # Update just the title
            update_event("event123", title="New Meeting Title")

            # Update time and location
            update_event("event123",
                        start_datetime="2025-06-25T14:00:00",
                        end_datetime="2025-06-25T15:00:00",
                        location="Conference Room A")
        """
        # Resolve calendar name to ID if needed
        resolved_calendar_id = self._get_calendar_id_by_name(calendar_id)

        try:
            if self.service:
                # First, get the existing event
                existing_event = (
                    self.service.events()
                    .get(calendarId=resolved_calendar_id, eventId=event_id)
                    .execute()
                )

                # Prepare updates - only update fields that are provided
                updates = {}

                if title is not None:
                    updates["summary"] = title

                if description is not None:
                    updates["description"] = description

                if location is not None:
                    updates["location"] = location

                if start_datetime is not None:
                    start_time = datetime.datetime.fromisoformat(start_datetime).strftime("%Y-%m-%dT%H:%M:%S")
                    updates["start"] = {"dateTime": start_time}

                if end_datetime is not None:
                    end_time = datetime.datetime.fromisoformat(end_datetime).strftime("%Y-%m-%dT%H:%M:%S")
                    updates["end"] = {"dateTime": end_time}

                # If no updates provided, return error
                if not updates:
                    return json.dumps({"error": "No update fields provided"})

                # Merge updates with existing event
                updated_event = {**existing_event, **updates}

                # Update the event
                result = (
                    self.service.events()
                    .update(
                        calendarId=resolved_calendar_id,
                        eventId=event_id,
                        body=updated_event
                    )
                    .execute()
                )

                # Parse and return the updated event in simplified format
                return self._parse_event(json.dumps([result]), calendar_id)

            else:
                return json.dumps({"error": "authentication issue"})

        except HttpError as error:
            if error.resp.status == 404:
                return json.dumps({"error": f"Event '{event_id}' not found in calendar '{calendar_id}'"})
            else:
                logger.error(f"An error occurred: {error}")
                return json.dumps({"error": f"An error occurred: {error}"})
        except Exception as e:
            logger.error(f"Error updating event: {e}")
            return json.dumps({"error": f"Error updating event: {e}"})

    @authenticated
    def delete_event(self, event_id: str, calendar_id: str = "primary") -> str:
        """
        Delete an existing event from the specified calendar.

        Args:
            event_id (str): ID of the event to delete
            calendar_id (str): ID or name of the calendar containing the event. Defaults to "primary".

        Returns:
            JSON string with success message or error message

        Example:
            delete_event("event123")
            delete_event("event123", calendar_id="Todoist")
        """
        # Resolve calendar name to ID if needed
        resolved_calendar_id = self._get_calendar_id_by_name(calendar_id)

        try:
            if self.service:
                # Delete the event
                self.service.events().delete(
                    calendarId=resolved_calendar_id,
                    eventId=event_id
                ).execute()

                return json.dumps({
                    "success": True,
                    "message": f"Event '{event_id}' deleted successfully from calendar '{calendar_id}'"
                })

            else:
                return json.dumps({"error": "authentication issue"})

        except HttpError as error:
            if error.resp.status == 404:
                return json.dumps({"error": f"Event '{event_id}' not found in calendar '{calendar_id}'"})
            elif error.resp.status == 410:
                return json.dumps({"error": f"Event '{event_id}' was already deleted"})
            else:
                logger.error(f"An error occurred: {error}")
                return json.dumps({"error": f"An error occurred: {error}"})
        except Exception as e:
            logger.error(f"Error deleting event: {e}")
            return json.dumps({"error": f"Error deleting event: {e}"})

    @authenticated
    def get_event_by_id(self, event_id: str, calendar_id: str = "primary") -> str:
        """
        Get a specific event by its ID.

        Args:
            event_id (str): ID of the event to retrieve
            calendar_id (str): ID or name of the calendar containing the event. Defaults to "primary".

        Returns:
            JSON string with event information or error message

        Example:
            get_event_by_id("event123")
            get_event_by_id("event123", calendar_id="Todoist")
        """
        # Resolve calendar name to ID if needed
        resolved_calendar_id = self._get_calendar_id_by_name(calendar_id)

        # Determine display name for the calendar
        if "@" not in calendar_id and calendar_id != "primary":
            calendar_display_name = calendar_id
        else:
            calendar_display_name = self._get_calendar_id_by_name(resolved_calendar_id)

        try:
            if self.service:
                # Get the event
                event = (
                    self.service.events()
                    .get(calendarId=resolved_calendar_id, eventId=event_id)
                    .execute()
                )

                # Parse and return the event in simplified format
                return self._parse_event(json.dumps([event]), calendar_display_name)

            else:
                return json.dumps({"error": "authentication issue"})

        except HttpError as error:
            if error.resp.status == 404:
                return json.dumps({"error": f"Event '{event_id}' not found in calendar '{calendar_id}'"})
            else:
                logger.error(f"An error occurred: {error}")
                return json.dumps({"error": f"An error occurred: {error}"})
        except Exception as e:
            logger.error(f"Error getting event: {e}")
            return json.dumps({"error": f"Error getting event: {e}"})

    @authenticated
    def search_events(
            self,
            query: str,
            calendar_id: str = "primary",
            max_results: int = 50,
            date_range: tuple = None
    ) -> str:
        """
        Search events by keywords in title, description, or location.

        Args:
            query (str): Search term to look for in events
            calendar_id (str): ID or name of the calendar to search. Defaults to "primary".
            max_results (int): Maximum number of results to return. Defaults to 50.
            date_range (tuple): Optional (start_date, end_date) tuple in YYYY-MM-DD format

        Returns:
            JSON string with matching events or error message

        Example:
            search_events("meeting")
            search_events("pwn.college", calendar_id="primary", date_range=("2025-06-01", "2025-06-30"))
        """
        # Resolve calendar name to ID if needed
        resolved_calendar_id = self._get_calendar_id_by_name(calendar_id)

        # Determine display name for the calendar
        if "@" not in calendar_id and calendar_id != "primary":
            calendar_display_name = calendar_id
        else:
            calendar_display_name = self._get_calendar_id_by_name(resolved_calendar_id)

        try:
            if self.service:
                # Prepare search parameters
                search_params = {
                    'calendarId': resolved_calendar_id,
                    'q': query,
                    'maxResults': max_results,
                    'singleEvents': True,
                    'orderBy': 'startTime'
                }

                # Add date range if provided
                if date_range:
                    start_date, end_date = date_range
                    # Convert to datetime with time for API
                    time_min = datetime.datetime.fromisoformat(start_date).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    time_max = datetime.datetime.fromisoformat(end_date + "T23:59:59").strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    search_params['timeMin'] = time_min
                    search_params['timeMax'] = time_max

                # Execute search
                events_result = self.service.events().list(**search_params).execute()
                events = events_result.get("items", [])

                if not events:
                    return json.dumps({
                        "message": f"No events found matching '{query}' in calendar '{calendar_display_name}'"
                    })

                events_json = json.dumps(events)
                return self._parse_event(events_json, calendar_display_name)

            else:
                return json.dumps({"error": "authentication issue"})

        except HttpError as error:
            logger.error(f"An error occurred during search: {error}")
            return json.dumps({"error": f"An error occurred during search: {error}"})
        except Exception as e:
            logger.error(f"Error searching events: {e}")
            return json.dumps({"error": f"Error searching events: {e}"})


if __name__ == "__main__":
    calendar = GoogleCalendarTools(
        credentials_path=r"E:\Projects\AgenDo\agendo\config\credentials\credentials.json",
        token_path=r"E:\Projects\AgenDo\agendo\config\credentials\token.json"
    )

    print("=== ALL CALENDARS ===")
    calendars = calendar.list_calendars()
    print(calendars)

    print("\n=== UPCOMING EVENTS (PRIMARY CALENDAR) ===")
    result = calendar.list_events()
    print(result)

    print("\n=== TESTING TODOIST CALENDAR BY NAME ===")
    todoist_events = calendar.list_events(calendar_id="Todoist")
    print(todoist_events)

    print("\n=== TESTING SEARCH ===")
    search_results = calendar.search_events("meeting")
    print(search_results)