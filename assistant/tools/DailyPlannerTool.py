import os
import json
from datetime import datetime, time, timedelta, timezone
from typing import List, Dict, Optional

from agno.tools import Toolkit
from agno.utils.log import logger

DEFAULT_DURATION_MINUTES = 30


def normalize_time_string(t: str) -> time:
    return datetime.fromisoformat(t.replace("Z", "+00:00")).time()


def time_in_range(start: time, end: time, now: time) -> bool:
    if start <= end:
        return start <= now <= end
    else:
        return now >= start or now <= end


class DayContextTool(Toolkit):
    def __init__(self, todoist_sdk, routine_path="data/routine_memory.json", config_path="data/blocked_config.json", **kwargs):
        super().__init__(name="DayContextTool", **kwargs)
        self.description = "Builds a full schedule for a day using routines, exceptions, and Todoist tasks."

        self.todoist = todoist_sdk
        self.routine_file = routine_path
        self.config_file = config_path
        self._cache = {}

        os.makedirs(os.path.dirname(self.routine_file), exist_ok=True)
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)

        # Primary entry point for daily planning. Use this to get today's schedule overview.
        self.register(self.get_day_schedule)
        self.register(self.add_routine)
        self.register(self.remove_routine)
        self.register(self.get_routine)
        self.register(self.add_exception)
        self.register(self.reschedule_routine_for_day)
        self.register(self.update_routine)

    def get_day_schedule(self, date: Optional[str] = None, force_refresh: bool = False) -> str:
        """
        Constructs a full schedule for the specified date using routines, exceptions,
        and Todoist tasks. Integrates with `get_tasks_by_day()` and `get_overdue_tasks()`
        from the Todoist SDK to ensure task inclusion and freshness.
        """
        try:
            date = date or datetime.today().strftime("%Y-%m-%d")
            self._apply_pending_exceptions(date)

            if not force_refresh and date in self._cache:
                return json.dumps(self._cache[date], indent=2)

            # Load routines and exceptions
            routines = self._get_routines(date)
            blocked = self._get_blocked_periods(date, routines)

            # Get Todoist tasks
            today_tasks = json.loads(self.todoist.get_tasks_by_day(date))
            if not isinstance(today_tasks, list):
                logger.warning(f"Expected list for today_tasks but got {type(today_tasks)}: {today_tasks}")
                today_tasks = []

            overdue_tasks = json.loads(self.todoist.get_overdue_tasks())
            if not isinstance(overdue_tasks, list):
                logger.warning(f"Expected list for overdue_tasks but got {type(overdue_tasks)}: {overdue_tasks}")
                overdue_tasks = []

            all_tasks = today_tasks + overdue_tasks

            # Combine all tasks (do NOT exclude recurring anymore!)
            all_tasks = today_tasks + overdue_tasks

            # Classify tasks
            scheduled, unscheduled, violating = [], [], []

            import pytz
            from dateutil.parser import isoparse

            local_tz = pytz.timezone("Asia/Jerusalem")

            for task in all_tasks:
                if not isinstance(task, dict):
                    continue

                due = task.get("due", {})

                if not due or not due.get("date"):
                    continue

                if due.get("datetime"):
                    try:
                        if due.get("timezone") is None:
                            # Assume datetime is already in local time
                            local_dt = isoparse(due["datetime"])
                        else:
                            # Convert from UTC to local timezone
                            utc_dt = isoparse(due["datetime"]).replace(tzinfo=timezone.utc)
                            local_dt = utc_dt.astimezone(local_tz)

                        # Attach the local time to the task for later use (like free block calc)
                        task["__local_datetime"] = local_dt.isoformat()
                        task["__local_time"] = local_dt.time().strftime("%H:%M")

                        scheduled.append(task)
                    except Exception as e:
                        logger.warning(f"Failed to parse datetime for task {task.get('content')}: {e}")
                else:
                    unscheduled.append(task)

            result = {
                "date": date,
                "routines": routines,
                "scheduled_tasks": scheduled,
                "unscheduled_tasks": unscheduled,
                "violating_tasks": violating,
                "free_blocks": self._get_free_blocks(date, blocked, scheduled)
            }

            self._cache[date] = result
            return json.dumps(result, indent=2)

        except Exception as e:
            logger.error(f"Failed to get day schedule: {e}")
            return json.dumps({"error": str(e)})

    def add_routine(self, label: str, days: List[str], start: str, end: str) -> str:
        """
        Adds a new recurring routine to the schedule. Note that this does not affect existing
        Todoist recurring tasks directly — make sure your recurring routines and Todoist
        recurring tasks are in sync if needed.
        """
        try:
            routines = {}
            if os.path.exists(self.routine_file):
                with open(self.routine_file, 'r') as f:
                    routines = json.load(f)

            added = []
            for day in days:
                d = day.lower()
                routines.setdefault(d, [])
                if not any(r for r in routines[d] if r['label'] == label and r['start'] == start and r['end'] == end):
                    routines[d].append({"label": label, "start": start, "end": end})
                    added.append(d)

            with open(self.routine_file, 'w') as f:
                json.dump(routines, f, indent=2)

            return json.dumps({"success": True, "added_to_days": added})
        except Exception as e:
            logger.error(f"Failed to add routine: {e}")
            return json.dumps({"error": str(e)})

    def remove_routine(self, label: str, day: Optional[str] = None) -> str:
        try:
            with open(self.routine_file, 'r') as f:
                routines = json.load(f)

            if day:
                d = day.lower()
                routines[d] = [r for r in routines.get(d, []) if r['label'] != label]
            else:
                for d in routines:
                    routines[d] = [r for r in routines[d] if r['label'] != label]

            with open(self.routine_file, 'w') as f:
                json.dump(routines, f, indent=2)
            return json.dumps({"success": True, "removed_label": label})
        except Exception as e:
            logger.error(f"Failed to remove routine: {e}")
            return json.dumps({"error": str(e)})

    def get_routine(self, day: str) -> str:
        try:
            with open(self.routine_file, 'r') as f:
                routines = json.load(f)
            blocks = routines.get(day.lower(), [])
            return json.dumps(blocks)
        except Exception as e:
            logger.warning(f"Failed to read routines: {e}")
            return json.dumps([])

    def add_exception(self, date: str, blocks: List[Dict[str, str]]) -> str:
        try:
            config = {}
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)

            if date == datetime.today().strftime("%Y-%m-%d"):
                config.setdefault("exceptions", {})[date] = blocks
            else:
                config.setdefault("pending_exceptions", {})[date] = blocks

            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)

            return json.dumps({"success": True, "applied_now": date == datetime.today().strftime("%Y-%m-%d")})
        except Exception as e:
            logger.error(f"Failed to add exception: {e}")
            return json.dumps({"error": str(e)})

    def reschedule_routine_for_day(self, date: str, label: str, new_start: str, new_end: str) -> str:
        """
        Temporarily overrides a single routine block for a specific date.
        This creates an exception entry that applies only on the given date.
        Note: This does not modify the recurring routine — only creates a one-day exception.
        """
        try:
            weekday = datetime.strptime(date, "%Y-%m-%d").strftime("%A").lower()

            # Load all routines to find matching block(s)
            with open(self.routine_file, 'r') as f:
                routines = json.load(f)

            base_blocks = routines.get("everyday", []) + routines.get(weekday, [])

            # Replace only the specified routine label with new time
            updated_blocks = [
                r if r['label'] != label else {"label": label, "start": new_start, "end": new_end}
                for r in base_blocks
            ]

            # Add exception for that day
            return self.add_exception(date, updated_blocks)

        except Exception as e:
            logger.error(f"Failed to reschedule routine: {e}")
            return json.dumps({"error": str(e)})

    def update_routine(self, label: str, new_start: str, new_end: str, day: Optional[str] = None) -> str:
        """
        Updates the time range of a recurring routine for a specific day or all days.
        If day is None, it will update across all weekdays that contain the routine.

        """
        try:
            if not os.path.exists(self.routine_file):
                return json.dumps({"error": "No routines exist yet."})

            with open(self.routine_file, 'r') as f:
                routines = json.load(f)

            updated_days = []
            target_days = routines.keys() if day is None else [day.lower()]

            for d in target_days:
                changed = False
                for r in routines.get(d, []):
                    if r["label"] == label:
                        r["start"] = new_start
                        r["end"] = new_end
                        changed = True
                if changed:
                    updated_days.append(d)

            with open(self.routine_file, 'w') as f:
                json.dump(routines, f, indent=2)

            return json.dumps({"success": True, "updated_on_days": updated_days})

        except Exception as e:
            logger.error(f"Failed to update routine: {e}")
            return json.dumps({"error": str(e)})

    def _apply_pending_exceptions(self, date: str):
        try:
            if not os.path.exists(self.config_file):
                return
            with open(self.config_file, 'r') as f:
                config = json.load(f)

            pending = config.get("pending_exceptions", {})
            if date in pending:
                config.setdefault("exceptions", {})[date] = pending[date]
                del config["pending_exceptions"][date]

                with open(self.config_file, 'w') as f:
                    json.dump(config, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to apply pending exceptions: {e}")

    def _get_routines(self, date: str) -> List[dict]:
        weekday = datetime.strptime(date, "%Y-%m-%d").strftime("%A").lower()
        routines = []
        try:
            if os.path.exists(self.routine_file):
                with open(self.routine_file, 'r') as f:
                    data = json.load(f)
                    routines.extend(data.get("everyday", []))
                    routines.extend(data.get(weekday, []))
        except Exception as e:
            logger.warning(f"Failed to load routines: {e}")
        return routines

    def _get_blocked_periods(self, date: str, base_routines: List[dict]) -> List[dict]:
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    exceptions = config.get("exceptions", {})
                    if date in exceptions:
                        raw = exceptions[date]

                        # Ensure the data is a list of dicts
                        if not isinstance(raw, list):
                            logger.warning(f"Blocked periods for {date} is not a list.")
                            return base_routines

                        filtered = [b for b in raw if isinstance(b, dict)]
                        if len(filtered) < len(raw):
                            logger.warning(f"Some exception blocks for {date} were not dicts and were skipped.")

                        return filtered
        except Exception as e:
            logger.warning(f"Failed to apply exceptions for {date}: {e}")

        return base_routines

    def _get_free_blocks(self, date: str, blocked: List[dict], scheduled: List[dict]) -> List[dict]:
        busy = []

        # 1. Add routines / exceptions as busy blocks
        for b in blocked:
            busy.append({
                "start": b["start"],
                "end": b["end"],
                "source": b.get("label", "routine")
            })

        # 2. Add scheduled Todoist tasks as busy blocks (assumes 15 min default if no duration)
        for task in scheduled:
            try:
                start_str = task["__local_time"]
                start_time = datetime.strptime(start_str, "%H:%M").time()
                end_time = (datetime.combine(datetime.today(), start_time) + timedelta(minutes=15)).time()

                busy.append({
                    "start": start_time.strftime("%H:%M"),
                    "end": end_time.strftime("%H:%M"),
                    "source": task.get("content", "task")
                })
            except Exception as e:
                logger.warning(f"Failed to handle time block for task {task.get('content')}: {e}")

        # 3. Sort busy periods by start time
        busy.sort(key=lambda b: b["start"])

        # 4. Detect free gaps between busy blocks
        free = []
        last_end = time(hour=6, minute=0)  # Assume wake-up at 06:00

        for b in busy:
            current_start = datetime.strptime(b["start"], "%H:%M").time()
            if last_end < current_start:
                free.append({
                    "start": last_end.strftime("%H:%M"),
                    "end": current_start.strftime("%H:%M")
                })
            last_end = max(last_end, datetime.strptime(b["end"], "%H:%M").time())

        # 5. Fill final free time until 23:00
        end_of_day = time(hour=23, minute=0)
        if last_end < end_of_day:
            free.append({
                "start": last_end.strftime("%H:%M"),
                "end": end_of_day.strftime("%H:%M")
            })

        return free


