from agno.tools import Toolkit
from assistant.sdk.googlecalendar import GoogleCalendarTools  # Assuming you placed it here
from datetime import datetime, timedelta
import json

class DailyPlanner(Toolkit):
    def __init__(self, calendar_sdk: GoogleCalendarTools, timezone: str = "UTC", **kwargs):
        super().__init__(name="DailyPlanner", **kwargs)

        self.description = "Simple daily planner using Google Calendar events."
        self.calendar = calendar_sdk
        self.timezone = timezone

        # Register public methods
        self.register(self.add_task)
        self.register(self.list_today)
        self.register(self.clear_today)

    def _today_bounds(self):
        today = datetime.now()
        start = today.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return start, end

    def add_task(self, title: str, start_time: str, end_time: str, description: str = "") -> str:
        """
        Add a new task (event) to today's schedule.

        Args:
            title (str): Title of the event.
            start_time (str): Start time in HH:MM format.
            end_time (str): End time in HH:MM format.
            description (str, optional): Description text. Defaults to empty.

        Example:
            planner.add_task("Study", "16:00", "18:00")
        """
        today = datetime.now().date()
        start = datetime.strptime(f"{today} {start_time}", "%Y-%m-%d %H:%M")
        end = datetime.strptime(f"{today} {end_time}", "%Y-%m-%d %H:%M")

        result = self.calendar.create_event(
            start_datetime=start.isoformat(),
            end_datetime=end.isoformat(),
            title=title,
            description=description,
            timezone=self.timezone
        )
        return result

    def list_today(self) -> str:
        """
        List all today's events.

        Example:
            planner.list_today()
        """
        start, _ = self._today_bounds()
        return self.calendar.list_events(limit=20, date_from=start.isoformat())

    def clear_today(self) -> str:
        """
        (Optional future feature) Clear all today's events. [NOT IMPLEMENTED]
        """
        return json.dumps({"error": "Not implemented yet."})


if __name__ == "__main__":
    calendar = GoogleCalendarTools(token_path="token.json")
    planner = DailyPlanner(calendar_sdk=calendar)

    # Add a task
    print(planner.add_task("Math Homework", "17:00", "19:00"))

    # List today's schedule
    print(planner.list_today())
