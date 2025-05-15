import json
from collections import defaultdict
from datetime import datetime, timezone, timedelta, time
from typing import Any, Dict, List, Optional

import requests
from dateutil.parser import isoparse
from dotenv import load_dotenv


load_dotenv()
import os
from agno.tools import Toolkit
from agno.utils.log import logger

try:
    from todoist_api_python.api import TodoistAPI
except ImportError:
    raise ImportError("`todoist-api-python` not installed. Please install using `pip install todoist-api-python`")


class TodoistTools(Toolkit):
    """
    A comprehensive toolkit for interacting with Todoist via the REST API v2.
    This class wraps the `todoist-api-python` client and exposes methods for tasks,
    projects, labels, sections, and custom utilities. Each method is heavily documented
    to explain purpose, parameters, and return values.
    """

    def __init__(self, api_token: Optional[str] = None, **kwargs):
        """
        Initialize the TodoistTools toolkit.

        This constructor will:
        1. Load the API token from the provided argument or environment.
        2. Instantiate the TodoistAPI client.
        3. Register all available tool methods for use by the agent.

        Args:
            api_token (Optional[str]): The Todoist API token. If None, will attempt to
                                      read from TODOIST_API_TOKEN environment variable.
            **kwargs: Additional keyword arguments passed to the base Toolkit.

        Raises:
            ValueError: If no API token is found.
            ImportError: If the `todoist-api-python` package is not installed.
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
        self.register(self.add_reminder)
        self.register(self.delete_task_by_name)

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

        # Helpers

    # =========== Helpers ===========



    def _task_to_dict(self, task: Any) -> Dict[str, Any]:
        """
        Convert a Todoist Task object into a serializable dictionary.

        This helper handles the conversion of nested `due` objects and ensures
        consistency in keys and formatting for downstream JSON encoding.

        Args:
            task (Any): The Todoist Task object returned by the API client.

        Returns:
            Dict[str, Any]: A flat dictionary representation of the task, including:
                - id, content, description, project_id, section_id, parent_id
                - order, priority, url, comment_count, creator_id, created_at
                - labels (list of label IDs)
                - due (nested dict with date, string, datetime, timezone)
        """
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
        Create a new task in Todoist with optional scheduling and metadata.

        This method wraps `api.add_task` and returns a JSON-encoded dictionary of
        the created task, or an error message if creation fails.

        Args:
            content (str): The human-readable task description.
            project_id (Optional[str]): ID of the project to place the task in.
            due_string (Optional[str]): Natural-language due date ("tomorrow at 12:00").
            priority (Optional[int]): Priority level 1-4 (4 is highest).
            labels (Optional[List[str]]): List of label names or IDs to tag the task.

        Returns:
            str: A JSON string of the created task dictionary or an error object.
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
        """
        Fetch a single task by its unique ID.

        Args:
            task_id (str): The ID of the task to retrieve.

        Returns:
            str: JSON-encoded dictionary of the task, or an error message.
        """
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
        Update properties of an existing task.

        Only fields explicitly provided (non-None) will be updated.

        Args:
            task_id (str): ID of the task to update.
            content (Optional[str]): New content if changing the title.
            description (Optional[str]): New description text.
            labels (Optional[List[str]]): Replace with this list of label IDs.
            priority (Optional[int]): New priority level.
            due_string (Optional[str]): New natural-language due date.
            due_date (Optional[str]): New due date in YYYY-MM-DD.
            due_datetime (Optional[str]): New due datetime in RFC3339.
            due_lang (Optional[str]): Two-letter language code for due_string.
            assignee_id (Optional[str]): User ID to assign the task to.
            section_id (Optional[str]): Section ID to move the task into.

        Returns:
            str: JSON `{"success": True}` on success or error message.
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

    def add_reminder(
            self,
            task_id: str,
            due_datetime: str,
            service: str = "push"
    ) -> str:
        """
        Create a reminder on an existing task.
        Args:
          task_id: ID of the task to remind.
          due_datetime: RFC3339 timestamp, e.g. "2025-04-28T09:00:00Z"
          service: "push", "email", or "sms"
        Returns:
          JSON string of the created reminder.
        """
        url = "https://api.todoist.com/reminders"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "task_id": task_id,
            "service": service,
            "due_datetime": due_datetime,
        }
        r = requests.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return r.text

    def close_task(self, task_id: str) -> str:
        """
        Mark a task as completed in Todoist.

        Args:
            task_id (str): The ID of the task to complete.

        Returns:
            str: JSON {"success": True} or error message.
        """
        try:
            success = self.api.close_task(task_id)
            return json.dumps({"success": success})
        except Exception as e:
            logger.error(f"Failed to close task: {str(e)}")
            return json.dumps({"error": str(e)})

    def delete_task(self, task_id: str) -> str:
        """
        Permanently remove a task from Todoist.

        Args:
            task_id (str): The ID of the task to delete.

        Returns:
            str: JSON {"success": True} or error message.
        """
        try:
            success = self.api.delete_task(task_id)
            return json.dumps({"success": success})
        except Exception as e:
            logger.error(f"Failed to delete task: {str(e)}")
            return json.dumps({"error": str(e)})

    def delete_task_by_name(self, task_name: str) -> str:
        """
        Helper function to delete a task by its content (name) instead of ID.

        Args:
            task_name (str): The name of the task to delete.

        Returns:
            str: JSON {"success": True} if deleted, or error.
        """
        try:
            tasks = self.api.get_tasks()
            for task in tasks:
                if task.content.strip().lower() == task_name.strip().lower():
                    success = self.api.delete_task(task.id)
                    return json.dumps({"success": success})
            return json.dumps({"error": f"Task '{task_name}' not found."})
        except Exception as e:
            logger.error(f"Failed to delete task by name '{task_name}': {str(e)}")
            return json.dumps({"error": str(e)})

    def get_active_tasks(self) -> str:
        """
        Fetch all active (incomplete) tasks across all projects.

        Returns:
            str: JSON list of task objects or error message.
        """
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
        Create a recurring task using a natural language recurrence rule.

        Args:
            content (str): Task description.
            recurrence (str): Recurrence rule (e.g., "every day at 18:00").
            project_id (Optional[str]): Project ID.
            priority (Optional[int]): Priority level.
            labels (Optional[List[str]]): Labels list.

        Returns:
            str: JSON string of the new recurring task or error.
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
        Retrieve all active tasks with a specific label.

        Args:
            label (str): Label name or ID to filter by.

        Returns:
            str: JSON list of matching tasks or error.
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
        Retrieve tasks at a given priority level.

        Args:
            priority (int): Priority level (1-4).

        Returns:
            str: JSON list of matching tasks or error.
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
        Retrieve all active tasks within a project.

        Args:
            project_id (str): The project identifier.

        Returns:
            str: JSON list of tasks or error.
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
        """
                Fetch tasks whose due date/time has already passed.

                Returns:
                    str: JSON list of overdue tasks or error.
        """
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
        Generate a summary report of active tasks:
        - Total count
        - Number overdue
        - Breakdown by priority

        Returns:
            str: JSON summary object or error.
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
        """
                Retrieve tasks due on a specific date.

                Args:
                    date (str): Target date in YYYY-MM-DD format.

                Returns:
                    str: JSON list of matching tasks or error.
        """
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
        """
                Retrieve tasks due within a week starting from a date.

                Args:
                    start_date (str): Week start date (YYYY-MM-DD).

                Returns:
                    str: JSON list of tasks within that 7-day span or error.
        """
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
        """
               Push all overdue tasks to a new due date.

               Args:
                   new_due_string (str): Natural-language date for rescheduling (default "today").

               Returns:
                   str: JSON {"rescheduled_tasks": [ids]} or error.
        """
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
        """
                Identify tasks with identical content (case-insensitive).

                Returns:
                    str: JSON {"duplicates": [[id1, id2], ...]} or error.
        """
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
        Remove duplicate tasks, keeping the first instance.

        Returns:
            str: JSON {"deleted_duplicates": [ids]} or error.
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
        Organize tasks into buckets by due date.

        Returns:
            str: JSON {"YYYY-MM-DD": [tasks], "no_due_date": [...]}
                 or error.
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
        List tasks whose due string indicates repetition.

        Returns:
            str: JSON list of recurring task objects or error.
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
        """
        Fetch all projects accessible to the user.

        Returns:
            str: JSON list of project objects or error.
        """
        try:
            projects = self.api.get_projects()
            return json.dumps([project.__dict__ for project in projects])
        except Exception as e:
            logger.error(f"Failed to get projects: {str(e)}")
            return json.dumps({"error": str(e)})

    def get_inbox_id(self) -> str:
        """
        Retrieve the project ID designated as the Inbox.

        Returns:
            str: Inbox project ID or error.
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
        Count active tasks in each project.

        Returns:
            str: JSON {project_id: count, ...} or error.
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
        """
        Retrieve all labels defined in the user's workspace.

        Returns:
            List[dict]: Each dict contains label metadata, or
                        empty list on error.
        """
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
        """
        Create a new label with optional color, order, and favorite flag.
        you can browse VALID_LABEL_COLORS to see the available colors.
        Args:
            name (str): The label name.
            color (Optional[str]): One of the valid color strings.
            order (Optional[int]): Position of the label in lists.
            favorite (Optional[bool]): Mark as favorite if True.

        Returns:
            Optional[str]: JSON string of created label or None on error.
        """

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
        """
        Lookup a label by name, or create it if not found.

        Args:
            name (str): Label name to find or create.

        Returns:
            Optional[str]: Label ID or None on failure.
        """
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
        Change the name of an existing label.

        Args:
            old_name (str): Current label name.
            new_name (str): Desired new label name.

        Returns:
            str: JSON {"success": True} or error message.
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
            str: JSON {label: count, ...} or error.
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
        """
        Fetch all sections within a given project.

        Args:
            project_id (str): The project identifier.

        Returns:
            str: JSON list of section objects or error.
        """
        try:
            sections = self.api.get_sections(project_id=project_id)
            return json.dumps([section.__dict__ for section in sections])
        except Exception as e:
            logger.error(f"Failed to get sections: {str(e)}")
            return json.dumps({"error": str(e)})

    def move_task_to_section(self, task_id: str, section_id: str) -> str:
        """
                Relocate a task into a specific section.

                Args:
                    task_id (str): ID of the task to move.
                    section_id (str): Destination section ID.

                Returns:
                    str: JSON {"success": True} or error.
                """
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
    todoist_toolkit.create_task("מתמטיקה")





