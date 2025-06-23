import json
import datetime
import os
from typing import Optional, List, Union

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools import Toolkit
from agno.utils.log import logger
from agendo.sdk.googlecalendar import GoogleCalendarTools


class Scheduler(Toolkit):
    """
    Comprehensive scheduling toolkit for the Calendar Agent.

    Provides all calendar and scheduling functionality needed for the Calendar Agent
    to manage events, analyze time availability, and provide intelligent scheduling
    recommendations when working with other agents or handling user requests.
    """

    def __init__(
            self,
            calendar_tools: Optional[GoogleCalendarTools] = None,
            credentials_path: Optional[str] = None,
            token_path: Optional[str] = None,
            todoist_calendar_name: str = "Todoist",
            **kwargs
    ):
        """
        Initialize the Scheduler toolkit for the Calendar Agent.

        Args:
            calendar_tools: Already authenticated GoogleCalendarTools instance (preferred)
            credentials_path: Path to Google Calendar credentials.json (if calendar_tools not provided)
            token_path: Path to Google Calendar token.json (if calendar_tools not provided)
            todoist_calendar_name: Name of the Todoist calendar (default: "Todoist")
        """
        super().__init__(**kwargs)

        # Use provided instance or create new one
        if calendar_tools is not None:
            self.calendar_tools = calendar_tools
        else:
            # Fallback to creating new instance
            self.calendar_tools = GoogleCalendarTools(
                credentials_path=credentials_path,
                token_path=token_path
            )

        self.todoist_calendar = todoist_calendar_name

        # Register Calendar Agent functions - organized by capability

        # === SCHEDULE READING ===
        self.register(self.get_events)
        self.register(self.get_tasks)  # Read synced Todoist tasks
        self.register(self.get_week_schedule)
        self.register(self.get_schedule_range)
        self.register(self.list_available_calendars)

        # === EVENT & TASK SCHEDULING ===
        self.register(self.find_event_by_name)
        self.register(self.move_event_by_name)
        self.register(self.create_event_simple)
        self.register(self.find_task_by_name)
        self.register(self.move_task_by_name)

        # === TIME ANALYSIS & OPTIMIZATION ===
        self.register(self.check_availability_simple)
        self.register(self.find_free_time_blocks)
        self.register(self.suggest_optimal_times)

    def _parse_human_date(self, date_input: str) -> str:
        """Helper to parse human-friendly dates into ISO format."""
        try:
            date_input = date_input.lower().strip()
            today = datetime.date.today()

            # Direct ISO format
            if len(date_input) == 10 and "-" in date_input:
                return date_input

            # Common phrases
            if date_input in ["today"]:
                return today.isoformat()
            elif date_input in ["tomorrow"]:
                return (today + datetime.timedelta(days=1)).isoformat()
            elif "next week" in date_input:
                return (today + datetime.timedelta(days=7)).isoformat()

            # Weekdays
            weekdays = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                        'friday': 4, 'saturday': 5, 'sunday': 6}

            for day_name, day_num in weekdays.items():
                if day_name in date_input:
                    days_ahead = day_num - today.weekday()
                    if days_ahead <= 0: days_ahead += 7
                    return (today + datetime.timedelta(days=days_ahead)).isoformat()

            return today.isoformat()
        except:
            return datetime.date.today().isoformat()

    def _parse_human_time(self, time_input: str, date: str) -> tuple:
        """Helper to parse human-friendly times into ISO datetime format."""
        try:
            time_input = time_input.lower().strip()

            # Default times for vague inputs
            time_mappings = {
                "morning": "09:00:00", "afternoon": "14:00:00",
                "evening": "18:00:00", "noon": "12:00:00"
            }

            start_time = None
            for phrase, time in time_mappings.items():
                if phrase in time_input:
                    start_time = time
                    break

            if not start_time:
                # Parse specific times like "2 PM", "14:30"
                if "pm" in time_input or "am" in time_input:
                    time_part = time_input.replace("pm", "").replace("am", "").strip()
                    hour = int(time_part.split(":")[0] if ":" in time_part else time_part)
                    minute = time_part.split(":")[1] if ":" in time_part else "00"

                    if "pm" in time_input and hour != 12:
                        hour += 12
                    elif "am" in time_input and hour == 12:
                        hour = 0

                    start_time = f"{hour:02d}:{minute}:00"
                elif ":" in time_input:
                    start_time = f"{time_input}:00"
                else:
                    start_time = "09:00:00"  # Default

            # Default 1 hour duration
            start_hour = int(start_time.split(":")[0])
            end_hour = min(start_hour + 1, 23)
            end_time = f"{end_hour:02d}:{start_time.split(':')[1]}:00"

            return f"{date}T{start_time}", f"{date}T{end_time}"
        except:
            return f"{date}T09:00:00", f"{date}T10:00:00"

    # =================== SCHEDULE READING ===================

    def get_events(self, limit: int = 10, date_from: str = datetime.date.today().isoformat()) -> str:
        """Get calendar events from primary calendar (excludes Todoist tasks)."""
        try:
            events_json = self.calendar_tools.list_events(limit=limit, date_from=date_from, calendar_id="primary")
            if "No upcoming events" in events_json or "error" in events_json:
                return events_json

            events = json.loads(events_json)
            if isinstance(events, list):
                for event in events:
                    event["item_type"] = "event"
            return json.dumps(events, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error getting events: {e}")
            return json.dumps({"error": f"Error getting events: {e}"})

    def get_tasks(self, limit: int = 10, date_from: str = datetime.date.today().isoformat()) -> str:
        """Get Todoist tasks synced to calendar for unified schedule view."""
        try:
            tasks_json = self.calendar_tools.list_events(limit=limit, date_from=date_from,
                                                         calendar_id=self.todoist_calendar)
            if "No upcoming events" in tasks_json or "error" in tasks_json:
                return tasks_json

            tasks = json.loads(tasks_json)
            for task in tasks:
                task["item_type"] = "task"
                description = task.get("description", "")
                if "todoist.com/app/task/" in description:
                    task["todoist_url"] = description.strip()
            return json.dumps(tasks, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error getting tasks: {e}")
            return json.dumps({"error": f"Error getting tasks: {e}"})

    def get_week_schedule(self, start_date: str = datetime.date.today().isoformat(), include_tasks: bool = True) -> str:
        """Get unified weekly schedule including events and synced tasks."""
        try:
            start = datetime.datetime.fromisoformat(start_date).date()
            week_schedule = {}

            for day_offset in range(7):
                current_date = start + datetime.timedelta(days=day_offset)
                date_str = current_date.isoformat()
                day_name = current_date.strftime("%A")

                day_data = {"date": date_str, "day_name": day_name, "events": [], "tasks": []}

                # Get events
                events_json = self.calendar_tools.list_events(limit=50, date_from=date_str, calendar_id="primary")
                if not ("error" in events_json or "No upcoming events" in events_json):
                    events = json.loads(events_json)
                    day_data["events"] = [e for e in events if date_str in e.get("time", "")]

                # Get tasks if requested
                if include_tasks:
                    tasks_json = self.calendar_tools.list_events(limit=50, date_from=date_str,
                                                                 calendar_id=self.todoist_calendar)
                    if not ("error" in tasks_json or "No upcoming events" in tasks_json):
                        tasks = json.loads(tasks_json)
                        day_data["tasks"] = [t for t in tasks if date_str in t.get("time", "")]

                week_schedule[date_str] = day_data

            return json.dumps(week_schedule, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error getting week schedule: {e}")
            return json.dumps({"error": f"Error getting week schedule: {e}"})

    def get_schedule_range(self, start_date: str, end_date: str, include_tasks: bool = True) -> str:
        """Get schedule for custom date range - flexible scheduling analysis."""
        try:
            start = datetime.datetime.fromisoformat(start_date).date()
            end = datetime.datetime.fromisoformat(end_date).date()

            if start > end:
                return json.dumps({"error": "Start date must be before or equal to end date"})

            range_schedule = []
            current_date = start

            while current_date <= end:
                date_str = current_date.isoformat()

                # Get events
                events_json = self.calendar_tools.list_events(limit=50, date_from=date_str, calendar_id="primary")
                if not ("error" in events_json or "No upcoming events" in events_json):
                    events = json.loads(events_json)
                    range_schedule.extend([e for e in events if date_str in e.get("time", "")])

                # Get tasks if requested
                if include_tasks:
                    tasks_json = self.calendar_tools.list_events(limit=50, date_from=date_str,
                                                                 calendar_id=self.todoist_calendar)
                    if not ("error" in tasks_json or "No upcoming events" in tasks_json):
                        tasks = json.loads(tasks_json)
                        range_schedule.extend([t for t in tasks if date_str in t.get("time", "")])

                current_date += datetime.timedelta(days=1)

            range_schedule.sort(key=lambda x: x.get("time", ""))
            return json.dumps(range_schedule, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error getting schedule range: {e}")
            return json.dumps({"error": f"Error getting schedule range: {e}"})

    def list_available_calendars(self) -> str:
        """List available calendars for calendar management."""
        try:
            return self.calendar_tools.list_calendars()
        except Exception as e:
            logger.error(f"Error listing calendars: {e}")
            return json.dumps({"error": f"Error listing calendars: {e}"})

    # =================== EVENT & TASK SCHEDULING ===================

    def find_event_by_name(self, event_name: str) -> str:
        """Find events by name - allows natural language event references instead of requiring exact IDs."""
        try:
            search_result = self.calendar_tools.search_events(query=event_name, calendar_id="primary", max_results=10)
            if "error" in search_result:
                return search_result

            events = json.loads(search_result)
            if not events or (isinstance(events, dict) and "message" in events):
                return json.dumps({"found": False, "error": f"No events found matching '{event_name}'"})

            # Find best matches
            exact_matches = [e for e in events if event_name.lower() == e.get("title", "").lower()]
            partial_matches = [e for e in events if event_name.lower() in e.get("title", "").lower()]
            matches = exact_matches if exact_matches else partial_matches

            if len(matches) == 1:
                event = matches[0]
                return json.dumps({
                    "found": True, "event_id": event.get("id"), "title": event.get("title"),
                    "time": event.get("time"), "location": event.get("location", "")
                })
            elif len(matches) > 1:
                return json.dumps({
                    "found": False, "multiple_matches": True, "count": len(matches),
                    "events": [{"event_id": e.get("id"), "title": e.get("title"), "time": e.get("time")} for e in
                               matches]
                })
            else:
                return json.dumps({"found": False, "error": f"No events found matching '{event_name}'"})
        except Exception as e:
            return json.dumps({"found": False, "error": f"Error finding event: {e}"})

    def move_event_by_name(self, event_name: str, new_date: str, new_time: str = "morning") -> str:
        """Move events using natural language dates and times."""
        try:
            # Find the event
            find_result = self.find_event_by_name(event_name)
            find_data = json.loads(find_result)

            if not find_data.get("found"):
                return find_result

            # Parse human-friendly date/time
            parsed_date = self._parse_human_date(new_date)
            start_datetime, end_datetime = self._parse_human_time(new_time, parsed_date)

            # Update the event
            result = self.calendar_tools.update_event(
                event_id=find_data["event_id"], calendar_id="primary",
                start_datetime=start_datetime, end_datetime=end_datetime
            )

            return json.dumps({
                "success": True, "event_name": event_name, "new_date": parsed_date,
                "new_time": new_time, "message": f"Event '{event_name}' moved to {parsed_date} at {new_time}"
            })
        except Exception as e:
            return json.dumps({"success": False, "error": f"Error moving event: {e}"})

    def create_event_simple(self, title: str, date: str, time: str = "morning",
                            duration: str = "1 hour", description: str = None, location: str = None) -> str:
        """Create events with natural language inputs for user-friendly scheduling."""
        try:
            parsed_date = self._parse_human_date(date)
            start_datetime, default_end = self._parse_human_time(time, parsed_date)

            # Parse duration
            hours = 1  # default
            if "hour" in duration.lower():
                if "2" in duration:
                    hours = 2
                elif "3" in duration:
                    hours = 3
                elif "30 min" in duration or "half" in duration:
                    hours = 0.5
            elif "30" in duration:
                hours = 0.5

            # Calculate end time
            start_dt = datetime.datetime.fromisoformat(start_datetime)
            end_dt = start_dt + datetime.timedelta(hours=hours)
            end_datetime = end_dt.strftime("%Y-%m-%dT%H:%M:%S")

            result = self.calendar_tools.create_event(
                start_datetime=start_datetime, end_datetime=end_datetime,
                title=title, description=description, location=location, calendar_id="primary"
            )

            return json.dumps({
                "success": True, "title": title, "date": parsed_date, "time": time,
                "start_datetime": start_datetime, "end_datetime": end_datetime,
                "message": f"Event '{title}' created for {parsed_date} at {time}"
            })
        except Exception as e:
            return json.dumps({"success": False, "error": f"Error creating event: {e}"})

    def find_task_by_name(self, task_name: str) -> str:
        """Find Todoist tasks by name - enables natural language task references."""
        try:
            search_result = self.calendar_tools.search_events(query=task_name, calendar_id=self.todoist_calendar,
                                                              max_results=10)
            if "error" in search_result:
                return search_result

            tasks = json.loads(search_result)
            if not tasks or (isinstance(tasks, dict) and "message" in tasks):
                return json.dumps({"found": False, "error": f"No tasks found matching '{task_name}'"})

            # Find best matches
            exact_matches = [t for t in tasks if task_name.lower() == t.get("title", "").lower()]
            partial_matches = [t for t in tasks if task_name.lower() in t.get("title", "").lower()]
            matches = exact_matches if exact_matches else partial_matches

            if len(matches) == 1:
                task = matches[0]
                return json.dumps({
                    "found": True, "task_id": task.get("id"), "title": task.get("title"),
                    "time": task.get("time"), "description": task.get("description", ""),
                    "todoist_url": task.get("todoist_url", "")
                })
            elif len(matches) > 1:
                return json.dumps({
                    "found": False, "multiple_matches": True, "count": len(matches),
                    "tasks": [{"task_id": t.get("id"), "title": t.get("title"), "time": t.get("time")} for t in matches]
                })
            else:
                return json.dumps({"found": False, "error": f"No tasks found matching '{task_name}'"})
        except Exception as e:
            return json.dumps({"found": False, "error": f"Error finding task: {e}"})

    def move_task_by_name(self, task_name: str, new_date: str, new_time: str = "morning") -> str:
        """Move Todoist tasks using natural language - Calendar Agent's scheduling authority."""
        try:
            # Find the task
            find_result = self.find_task_by_name(task_name)
            find_data = json.loads(find_result)

            if not find_data.get("found"):
                return find_result

            # Parse human-friendly date/time
            parsed_date = self._parse_human_date(new_date)
            start_datetime, end_datetime = self._parse_human_time(new_time, parsed_date)

            # Update the task in Todoist calendar (bidirectional sync will update Todoist)
            result = self.calendar_tools.update_event(
                event_id=find_data["task_id"], calendar_id=self.todoist_calendar,
                start_datetime=start_datetime, end_datetime=end_datetime
            )

            return json.dumps({
                "success": True, "task_name": task_name, "new_date": parsed_date,
                "new_time": new_time, "message": f"Task '{task_name}' rescheduled to {parsed_date} at {new_time}",
                "note": "Change will sync back to Todoist automatically"
            })
        except Exception as e:
            return json.dumps({"success": False, "error": f"Error moving task: {e}"})

    # =================== TIME ANALYSIS & OPTIMIZATION ===================

    def check_availability_simple(self, date: str, time: str = "morning") -> str:
        """Quick availability check using natural language inputs."""
        try:
            parsed_date = self._parse_human_date(date)

            # Get day's events and tasks
            events_json = self.calendar_tools.list_events(limit=50, date_from=parsed_date, calendar_id="primary")
            tasks_json = self.calendar_tools.list_events(limit=50, date_from=parsed_date,
                                                         calendar_id=self.todoist_calendar)

            conflicts = []

            # Check events
            if not ("error" in events_json or "No upcoming events" in events_json):
                events = json.loads(events_json)
                conflicts.extend([{"type": "event", "title": e.get("title"), "time": e.get("time")}
                                  for e in events if
                                  parsed_date in e.get("time", "") and "All day" not in e.get("time", "")])

            # Check tasks
            if not ("error" in tasks_json or "No upcoming events" in tasks_json):
                tasks = json.loads(tasks_json)
                conflicts.extend([{"type": "task", "title": t.get("title"), "time": t.get("time")}
                                  for t in tasks if
                                  parsed_date in t.get("time", "") and "All day" not in t.get("time", "")])

            return json.dumps({
                "date": parsed_date, "requested_time": time, "available": len(conflicts) == 0,
                "conflicts_count": len(conflicts), "conflicts": conflicts,
                "message": f"{'Available' if len(conflicts) == 0 else 'Busy'} on {parsed_date} during {time}"
            })
        except Exception as e:
            return json.dumps({"error": f"Error checking availability: {e}"})

    def find_free_time_blocks(self, hours_needed: float, date_range: tuple = None,
                              working_hours: tuple = (9, 17)) -> str:
        """Find available time blocks for scheduling - core scheduling intelligence."""
        try:
            if date_range is None:
                start_date = datetime.date.today().isoformat()
                end_date = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
            else:
                start_date, end_date = date_range

            # Get all scheduled items in range
            schedule_data = self.get_schedule_range(start_date, end_date, include_tasks=True)
            if "error" in schedule_data:
                return schedule_data

            items = json.loads(schedule_data)
            free_blocks = []

            # Analyze each day
            current_date = datetime.datetime.fromisoformat(start_date).date()
            end_date_obj = datetime.datetime.fromisoformat(end_date).date()

            while current_date <= end_date_obj:
                date_str = current_date.isoformat()
                day_items = [item for item in items if date_str in item.get("time", "")]

                # Simple free time detection (can be enhanced)
                start_hour, end_hour = working_hours
                total_work_hours = end_hour - start_hour
                busy_hours = len([item for item in day_items if "All day" not in item.get("time", "")])

                estimated_free_hours = max(0, total_work_hours - busy_hours)

                if estimated_free_hours >= hours_needed:
                    free_blocks.append({
                        "date": date_str,
                        "day_name": current_date.strftime("%A"),
                        "estimated_free_hours": estimated_free_hours,
                        "busy_items": len(day_items),
                        "recommended_times": ["morning", "afternoon"] if estimated_free_hours > 4 else ["morning"]
                    })

                current_date += datetime.timedelta(days=1)

            return json.dumps({
                "hours_needed": hours_needed,
                "date_range": f"{start_date} to {end_date}",
                "free_blocks_found": len(free_blocks),
                "recommendations": free_blocks
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": f"Error finding free time: {e}"})

    def suggest_optimal_times(self, task_count: int, hours_per_task: float, deadline_date: str = None) -> str:
        """Suggest optimal scheduling for multiple tasks with deadline analysis."""
        try:
            if deadline_date:
                deadline = datetime.datetime.fromisoformat(deadline_date).date()
                days_available = (deadline - datetime.date.today()).days
            else:
                days_available = 7  # Default to one week

            total_hours = task_count * hours_per_task
            hours_per_day = total_hours / max(1, days_available)

            # Get free time blocks
            end_date = deadline_date if deadline_date else (
                        datetime.date.today() + datetime.timedelta(days=7)).isoformat()
            free_blocks_result = self.find_free_time_blocks(hours_per_task,
                                                            (datetime.date.today().isoformat(), end_date))
            free_blocks_data = json.loads(free_blocks_result)

            return json.dumps({
                "analysis": {
                    "total_tasks": task_count,
                    "hours_per_task": hours_per_task,
                    "total_hours_needed": total_hours,
                    "days_available": days_available,
                    "recommended_hours_per_day": round(hours_per_day, 1)
                },
                "feasibility": "feasible" if hours_per_day <= 8 else "challenging",
                "available_blocks": free_blocks_data.get("recommendations", []),
                "suggestion": f"Schedule {hours_per_task}h blocks across {len(free_blocks_data.get('recommendations', []))} available days"
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": f"Error suggesting optimal times: {e}"})


if __name__ == "__main__":
    calendar = GoogleCalendarTools(
        credentials_path=r"E:\Projects\AgenDo\agendo\config\credentials\credentials.json",
        token_path=r"E:\Projects\AgenDo\agendo\config\credentials\token.json"
    )
    scheduler = Scheduler(calendar_tools=calendar)

    # Test Calendar Agent toolkit capabilities
    print("=== CALENDAR AGENT TOOLKIT TEST ===")
    print("\n1. Week Schedule Analysis:")
    print(scheduler.get_week_schedule())

    print("\n2. Event Search:")
    print(scheduler.find_event_by_name("BSidesTLV"))

    print("\n3. Task Search:")
    print(scheduler.find_task_by_name("pwn.college"))

    print("\n4. Availability Check:")
    print(scheduler.check_availability_simple("tomorrow", "afternoon"))

    print("\n5. Free Time Analysis:")
    print(scheduler.find_free_time_blocks(2.5, working_hours=(9, 17)))

    # Calendar Agent setup
    calendar_agent = Agent(
        model=OpenAIChat(id="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY")),
        tools=[scheduler],
        markdown=True,
        show_tool_calls=True
    )

    print("\n=== CALENDAR AGENT TEST ===")
    calendar_agent.print_response("Find my pwn.college task and check if I can reschedule it to Friday morning")