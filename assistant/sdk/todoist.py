import json
from collections import defaultdict
from datetime import datetime, timezone, timedelta, time
from typing import Any, Dict, List, Optional

from dateutil.parser import isoparse
from dotenv import load_dotenv

from assistant.tools.DailyPlannerTool import normalize_time_string

load_dotenv()
import os
from agno.tools import Toolkit
from agno.utils.log import logger

try:
    from todoist_api_python.api import TodoistAPI
except ImportError:
    raise ImportError("`todoist-api-python` not installed. Please install using `pip install todoist-api-python`")


class TodoistTools(Toolkit):
    """A toolkit for interacting with Todoist tasks and projects."""

    def __init__(self, api_token: Optional[str] = None, **kwargs):
        """Initialize the Todoist toolkit.

        Args:
            api_token: Optional Todoist API token. If not provided, will look for TODOIST_API_TOKEN env var
            create_task: Whether to register the create_task function
            get_task: Whether to register the get_task function
            update_task: Whether to register the update_task function
            close_task: Whether to register the close_task function
            delete_task: Whether to register the delete_task function
            get_active_tasks: Whether to register the get_active_tasks function
            get_projects: Whether to register the get_projects function
        """
        super().__init__(name="todoist", **kwargs)

        self.api_token = api_token or os.getenv("TODOIST_API_TOKEN")
        if not self.api_token:
            raise ValueError("TODOIST_API_TOKEN not set. Please set the TODOIST_API_TOKEN environment variable.")

        self.api = TodoistAPI(self.api_token)

        # Register enabled functions
        # Register all available functions
        # Task Management
        self.register(self.create_task)
        self.register(self.create_recurring_task)
        self.register(self.get_task)
        self.register(self.update_task)
        self.register(self.close_task)
        self.register(self.delete_task)
        self.register(self.get_active_tasks)
        self.register(self.get_tasks_by_label)
        self.register(self.get_tasks_by_priority)
        self.register(self.get_tasks_by_project)
        self.register(self.get_overdue_tasks)
        self.register(self.get_task_summary)
        self.register(self.get_tasks_by_day)
        self.register(self.get_tasks_by_week)
        self.register(self.reschedule_overdue_tasks)
        self.register(self.get_recurring_tasks)
        self.register(self.group_tasks_by_day)
        self.register(self.detect_duplicate_tasks)
        self.register(self.delete_duplicate_tasks)

        # Project Management
        self.register(self.get_projects)
        self.register(self.get_inbox_id)
        self.register(self.count_tasks_by_project)

        # Label Management
        self.register(self.get_labels)
        self.register(self.create_label)
        self.register(self.get_or_create_label)
        self.register(self.rename_label)
        self.register(self.count_tasks_by_label)

        # Section Management
        self.register(self.get_sections)
        self.register(self.move_task_to_section)

    # =========== Helpers ===========


    def _task_to_dict(self, task: Any) -> Dict[str, Any]:
        """Convert a Todoist task to a dictionary with proper typing."""
        task_dict: Dict[str, Any] = {
            "id": task.id,
            "content": task.content,
            "description": task.description,
            "project_id": task.project_id,
            "section_id": task.section_id,
            "parent_id": task.parent_id,
            "order": task.order,
            "priority": task.priority,
            "url": task.url,
            "comment_count": task.comment_count,
            "creator_id": task.creator_id,
            "created_at": task.created_at,
            "labels": task.labels,
        }
        if task.due:
            task_dict["due"] = {
                "date": task.due.date,
                "string": task.due.string,
                "datetime": task.due.datetime,
                "timezone": task.due.timezone,
            }
        return task_dict

    # =========== Tasks ===========

    def create_task(
        self,
        content: str,
        project_id: Optional[str] = None,
        due_string: Optional[str] = None,
        priority: Optional[int] = None,
        labels: Optional[List[str]] = None,
    ) -> str:
        """
        Create a new task in Todoist.

        Args:
            content: The task content/description
            project_id: Optional ID of the project to add the task to
            due_string: Optional due date in natural language (e.g., "tomorrow at 12:00")
            priority: Optional priority level (1-4, where 4 is highest)
            labels: Optional list of label names to apply to the task

        Returns:
            str: JSON string containing the created task
        """
        try:
            task = self.api.add_task(
                content=content, project_id=project_id, due_string=due_string, priority=priority, labels=labels or []
            )
            # Convert task to a dictionary and handle the Due object
            task_dict = self._task_to_dict(task)
            return json.dumps(task_dict)
        except Exception as e:
            logger.error(f"Failed to create task: {str(e)}")
            return json.dumps({"error": str(e)})

    def get_task(self, task_id: str) -> str:
        """Get a specific task by ID."""
        try:
            task = self.api.get_task(task_id)
            task_dict = self._task_to_dict(task)
            return json.dumps(task_dict)
        except Exception as e:
            logger.error(f"Failed to get task: {str(e)}")
            return json.dumps({"error": str(e)})

    def update_task(
        self,
        task_id: str,
        content: Optional[str] = None,
        description: Optional[str] = None,
        labels: Optional[List[str]] = None,
        priority: Optional[int] = None,
        due_string: Optional[str] = None,
        due_date: Optional[str] = None,
        due_datetime: Optional[str] = None,
        due_lang: Optional[str] = None,
        assignee_id: Optional[str] = None,
        section_id: Optional[str] = None,
    ) -> str:
        """
        Update an existing task with the specified parameters.

        Args:
            task_id: The ID of the task to update
            content: The task content/name
            description: The task description
            labels: Array of label names
            priority: Task priority from 1 (normal) to 4 (urgent)
            due_string: Human readable date ("next Monday", "tomorrow", etc)
            due_date: Specific date in YYYY-MM-DD format
            due_datetime: Specific date and time in RFC3339 format
            due_lang: 2-letter code specifying language of due_string ("en", "fr", etc)
            assignee_id: The responsible user ID
            section_id: ID of the section to move task to

        Returns:
            str: JSON string containing success status or error message
        """
        try:
            # Build updates dictionary with only provided parameters
            updates: Dict[str, Any] = {}
            if content is not None:
                updates["content"] = content
            if description is not None:
                updates["description"] = description
            if labels is not None:
                updates["labels"] = labels
            if priority is not None:
                updates["priority"] = priority
            if due_string is not None:
                updates["due_string"] = due_string
            if due_date is not None:
                updates["due_date"] = due_date
            if due_datetime is not None:
                updates["due_datetime"] = due_datetime
            if due_lang is not None:
                updates["due_lang"] = due_lang
            if assignee_id is not None:
                updates["assignee_id"] = assignee_id
            if section_id is not None:
                updates["section_id"] = section_id

            success = self.api.update_task(task_id=task_id, **updates)
            return json.dumps({"success": success})
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to update task: {error_msg}")
            return json.dumps({"error": error_msg})

    def close_task(self, task_id: str) -> str:
        """Mark a task as completed."""
        try:
            success = self.api.close_task(task_id)
            return json.dumps({"success": success})
        except Exception as e:
            logger.error(f"Failed to close task: {str(e)}")
            return json.dumps({"error": str(e)})

    def delete_task(self, task_id: str) -> str:
        """Delete a task."""
        try:
            success = self.api.delete_task(task_id)
            return json.dumps({"success": success})
        except Exception as e:
            logger.error(f"Failed to delete task: {str(e)}")
            return json.dumps({"error": str(e)})

    def get_active_tasks(self) -> str:
        """Get all active (not completed) tasks."""
        try:
            tasks = self.api.get_tasks()
            tasks_list = []
            for task in tasks:
                task_dict = self._task_to_dict(task)
                tasks_list.append(task_dict)
            return json.dumps(tasks_list)
        except Exception as e:
            logger.error(f"Failed to get active tasks: {str(e)}")
            return json.dumps({"error": str(e)})

    def create_recurring_task(
            self,
            content: str,
            recurrence: str,
            project_id: Optional[str] = None,
            priority: Optional[int] = None,
            labels: Optional[List[str]] = None,
    ) -> str:
        """
        Create a recurring task in Todoist using natural language.

        Args:
            content: The task content (e.g. "Workout")
            recurrence: Recurring pattern (e.g. "every day at 18:00", "every Monday")
            project_id: Optional project ID to place the task in
            priority: Optional task priority (1-4)
            labels: Optional list of label names

        Returns:
            str: JSON string of the created task or error
        """
        return self.create_task(
            content=content,
            project_id=project_id,
            due_string=recurrence,
            priority=priority,
            labels=labels,
        )

    def get_tasks_by_label(self, label: str) -> str:
        """
        Get all active tasks that have the given label.

        Args:
            label: The label name to filter by

        Returns:
            str: JSON list of matching tasks
        """
        try:
            tasks = self.api.get_tasks()
            filtered = [
                self._task_to_dict(task)
                for task in tasks
                if label in task.labels
            ]
            return json.dumps(filtered)
        except Exception as e:
            logger.error(f"Failed to get tasks by label: {str(e)}")
            return json.dumps({"error": str(e)})

    def get_tasks_by_priority(self, priority: int) -> str:
        """
        Get all active tasks with the specified priority.

        Args:
            priority: Priority level (1 to 4, where 4 is highest)

        Returns:
            str: JSON list of matching tasks
        """
        try:
            tasks = self.api.get_tasks()
            filtered = [
                self._task_to_dict(task)
                for task in tasks
                if task.priority == priority
            ]
            return json.dumps(filtered)
        except Exception as e:
            logger.error(f"Failed to get tasks by priority: {str(e)}")
            return json.dumps({"error": str(e)})

    def get_tasks_by_project(self, project_id: str) -> str:
        """
        Get all active tasks within a specific project.

        Args:
            project_id: The ID of the project to filter tasks by

        Returns:
            str: JSON list of matching tasks
        """
        try:
            tasks = self.api.get_tasks()
            filtered = [
                self._task_to_dict(task)
                for task in tasks
                if task.project_id == project_id
            ]
            return json.dumps(filtered)
        except Exception as e:
            logger.error(f"Failed to get tasks by project: {str(e)}")
            return json.dumps({"error": str(e)})

    from dateutil.parser import isoparse
    from datetime import datetime, time, timezone

    def get_overdue_tasks(self) -> str:
        try:
            now = datetime.now(timezone.utc)
            tasks = self.api.get_tasks()
            overdue = []

            for task in tasks:
                if not hasattr(task, "due") or not task.due:
                    continue

                try:
                    # Handle datetime-based due
                    if hasattr(task.due, "datetime") and task.due.datetime:
                        due_datetime = isoparse(task.due.datetime)
                    # Handle date-only due
                    elif hasattr(task.due, "date") and task.due.date:
                        due_date = isoparse(task.due.date).date()
                        due_datetime = datetime.combine(due_date, time.min).replace(tzinfo=timezone.utc)
                    else:
                        continue  # skip if due is malformed

                    # Convert to naive to ensure consistent comparison
                    if due_datetime.replace(tzinfo=None) < now.replace(tzinfo=None):
                        overdue.append(self._task_to_dict(task))

                except Exception as e:
                    # Log for development purposes, but avoid crashing or warning
                    logger.debug(f"Handled task with invalid due: {e}")

            return json.dumps(overdue)

        except Exception as e:
            logger.error(f"Failed to get overdue tasks: {str(e)}")
            return json.dumps({"error": str(e)})

    def get_task_summary(self) -> str:
        """
        Return a summary of active tasks: total, overdue, and by priority level.

        Returns:
            str: JSON summary report
        """
        try:
            tasks = self.api.get_tasks()
            now = datetime.now().replace(tzinfo=None)  # make it offset-naive

            total = 0
            overdue = 0
            priority_count = {1: 0, 2: 0, 3: 0, 4: 0}

            for task in tasks:
                total += 1
                priority_count[task.priority] += 1

                if task.due and task.due.datetime:
                    due_dt = datetime.fromisoformat(task.due.datetime).replace(tzinfo=None)
                    if due_dt < now:
                        overdue += 1

            summary = {
                "total_tasks": total,
                "overdue_tasks": overdue,
                "priority_breakdown": priority_count
            }
            return json.dumps(summary)
        except Exception as e:
            logger.error(f"Failed to generate task summary: {str(e)}")
            return json.dumps({"error": str(e)})

    def get_tasks_by_day(self, date: str) -> str:
        try:
            tasks = self.api.get_tasks()
            matching = [
                self._task_to_dict(task)
                for task in tasks
                if task.due and task.due.date == date
            ]
            return json.dumps(matching)
        except Exception as e:
            logger.error(f"Failed to get tasks for day {date}: {str(e)}")
            return json.dumps({"error": str(e)})

    def get_tasks_by_week(self, start_date: str) -> str:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = start + timedelta(days=6)

            tasks = self.api.get_tasks()
            matching = [
                self._task_to_dict(task)
                for task in tasks
                if task.due and start <= datetime.strptime(task.due.date, "%Y-%m-%d").date() <= end
            ]
            return json.dumps(matching)
        except Exception as e:
            logger.error(f"Failed to get weekly tasks from {start_date}: {str(e)}")
            return json.dumps({"error": str(e)})

    def reschedule_overdue_tasks(self, new_due_string: str = "today") -> str:
        try:
            now = datetime.now().replace(tzinfo=None)
            tasks = self.api.get_tasks()
            updated_ids = []

            for task in tasks:
                if task.due and task.due.datetime:
                    due_dt = datetime.fromisoformat(task.due.datetime).replace(tzinfo=None)
                    if due_dt < now:
                        self.api.update_task(task.id, due_string=new_due_string)
                        updated_ids.append(str(task.id))

            return json.dumps({"rescheduled_tasks": updated_ids})
        except Exception as e:
            logger.error(f"Failed to reschedule overdue tasks: {str(e)}")
            return json.dumps({"error": str(e)})

    def detect_duplicate_tasks(self) -> str:
        try:
            tasks = self.api.get_tasks()
            content_map = defaultdict(list)

            for task in tasks:
                normalized = task.content.strip().lower()
                content_map[normalized].append(str(task.id))

            duplicates = [ids for ids in content_map.values() if len(ids) > 1]
            return json.dumps({"duplicates": duplicates})
        except Exception as e:
            logger.error(f"Failed to detect duplicates: {str(e)}")
            return json.dumps({"error": str(e)})

    def delete_duplicate_tasks(self) -> str:
        """
        Detect and delete duplicate tasks (same content). Keeps only one of each group.

        Returns:
            JSON string of deleted task IDs
        """
        try:
            tasks = self.api.get_tasks()
            content_map = defaultdict(list)

            for task in tasks:
                normalized = task.content.strip().lower()
                content_map[normalized].append(task)

            deleted_ids = []

            for group in content_map.values():
                if len(group) > 1:
                    # Keep the first task, delete the rest
                    for task in group[1:]:
                        self.api.delete_task(task.id)
                        deleted_ids.append(str(task.id))

            return json.dumps({"deleted_duplicates": deleted_ids})
        except Exception as e:
            logger.error(f"Failed to delete duplicate tasks: {str(e)}")
            return json.dumps({"error": str(e)})

    def group_tasks_by_day(self) -> str:
        """
        Groups all tasks by due date (YYYY-MM-DD).

        Returns:
            JSON string of grouped tasks: { "2025-04-18": [task1, task2], ... }
        """
        try:
            tasks = self.api.get_tasks()
            grouped = defaultdict(list)

            for task in tasks:
                if task.due and task.due.date:
                    grouped[task.due.date].append(self._task_to_dict(task))
                else:
                    grouped["no_due_date"].append(self._task_to_dict(task))

            return json.dumps(grouped)
        except Exception as e:
            logger.error(f"Failed to group tasks by day: {str(e)}")
            return json.dumps({"error": str(e)})

    def get_recurring_tasks(self) -> str:
        """
        Returns all recurring tasks by checking if the due string indicates repetition.

        Returns:
            JSON string of recurring tasks
        """
        try:
            tasks = self.api.get_tasks()
            recurring = []

            for task in tasks:
                if task.due and task.due.string:
                    due_str = task.due.string.lower()
                    # Heuristic: look for signs of recurrence
                    if any(word in due_str for word in ["every", "each", "daily", "weekly", "monthly"]):
                        recurring.append(self._task_to_dict(task))

            return json.dumps(recurring)
        except Exception as e:
            logger.error(f"Failed to get recurring tasks: {str(e)}")
            return json.dumps({"error": str(e)})

    # =========== Projects ===========

    def get_projects(self) -> str:
        """Get all projects."""
        try:
            projects = self.api.get_projects()
            return json.dumps([project.__dict__ for project in projects])
        except Exception as e:
            logger.error(f"Failed to get projects: {str(e)}")
            return json.dumps({"error": str(e)})

    def get_inbox_id(self) -> str:
        """
        Get the project ID of the Inbox.

        Returns:
            str: Inbox project ID or error message
        """
        try:
            projects = self.api.get_projects()
            for project in projects:
                if project.is_inbox_project:
                    return project.id
            return json.dumps({"error": "Inbox project not found"})
        except Exception as e:
            logger.error(f"Failed to get inbox ID: {str(e)}")
            return json.dumps({"error": str(e)})

    def count_tasks_by_project(self) -> str:
        """
        Count how many active tasks exist per project.

        Returns:
            str: JSON dict of project_id -> task count
        """
        try:
            tasks = self.api.get_tasks()
            project_count = {}

            for task in tasks:
                project_id = task.project_id
                project_count[project_id] = project_count.get(project_id, 0) + 1

            return json.dumps(project_count)
        except Exception as e:
            logger.error(f"Failed to count tasks by project: {str(e)}")
            return json.dumps({"error": str(e)})

    # =========== Labels ===========

    def get_labels(self) -> list[dict]:
        """Get all existing labels as a list of dicts."""
        try:
            labels = self.api.get_labels()
            return [label.__dict__ for label in labels]
        except Exception as e:
            logger.error(f"Failed to get labels: {str(e)}")
            return []

    VALID_LABEL_COLORS = {
        "berry_red", "red", "orange", "yellow", "olive_green", "lime_green",
        "green", "mint_green", "teal", "sky_blue", "light_blue", "blue",
        "grape", "violet", "lavender", "magenta", "salmon", "charcoal",
        "grey", "taupe"
    }

    def create_label(self, name: str, color: Optional[str] = None,
                     order: Optional[int] = None,
                     favorite: Optional[bool] = None) -> Optional[str]:
        """Create a new label and return it as a JSON string."""

        try:
            payload = {
                "name": name
            }

            if color and color in self.VALID_LABEL_COLORS:
                payload["color"] = color
            elif color:
                logger.warning(f"Invalid color '{color}' — falling back to default.")

            if order is not None:
                payload["order"] = order
            if favorite is not None:
                payload["favorite"] = favorite

            label = self.api.add_label(**payload)
            return json.dumps(label.__dict__)
        except Exception as e:
            logger.error(f"Failed to create label '{name}': {str(e)}")
            return None

    def get_or_create_label(self, name: str) -> Optional[str]:
        """Returns the label ID for an existing or newly created label."""
        for label in self.get_labels():
            if label["name"].lower() == name.lower():
                return label["id"]

        new_label_json = self.create_label(name)
        if new_label_json:
            try:
                new_label = json.loads(new_label_json)
                return new_label["id"]
            except Exception as e:
                logger.error(f"Failed to parse new label JSON: {str(e)}")
        return None

    def rename_label(self, old_name: str, new_name: str) -> str:
        """
        Rename a label by name.

        Args:
            old_name: Current label name
            new_name: New label name

        Returns:
            str: JSON of success status or error
        """
        try:
            labels = self.api.get_labels()
            for label in labels:
                if label.name == old_name:
                    success = self.api.update_label(label.id, name=new_name)
                    return json.dumps({"success": success})
            return json.dumps({"error": f"Label '{old_name}' not found"})
        except Exception as e:
            logger.error(f"Failed to rename label: {str(e)}")
            return json.dumps({"error": str(e)})

    def count_tasks_by_label(self) -> str:
        """
        Count how many active tasks are assigned to each label.

        Returns:
            str: JSON dict of label -> count
        """
        try:
            tasks = self.api.get_tasks()
            label_count = {}

            for task in tasks:
                for label in task.labels:
                    label_count[label] = label_count.get(label, 0) + 1

            return json.dumps(label_count)
        except Exception as e:
            logger.error(f"Failed to count tasks by label: {str(e)}")
            return json.dumps({"error": str(e)})

    # =========== Sections ===========

    def get_sections(self, project_id: str) -> str:
        """Get all sections within a specific project."""
        try:
            sections = self.api.get_sections(project_id=project_id)
            return json.dumps([section.__dict__ for section in sections])
        except Exception as e:
            logger.error(f"Failed to get sections: {str(e)}")
            return json.dumps({"error": str(e)})

    def move_task_to_section(self, task_id: str, section_id: str) -> str:
        """Move a task to a specific section."""
        try:
            success = self.api.update_task(task_id=task_id, section_id=section_id)
            return json.dumps({"success": success})
        except Exception as e:
            logger.error(f"Failed to move task to section: {str(e)}")
            return json.dumps({"error": str(e)})


if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv()


    # Initialize the SDK
    todoist_toolkit = TodoistTools()


    recurring_task_json = todoist_toolkit.create_recurring_task(
        content="Do 15 pushups 💪",
        recurrence="every day at 19:30",
        labels=["habit", "workout"],
        priority=3
    )
    print("Recurring Task:", recurring_task_json)

