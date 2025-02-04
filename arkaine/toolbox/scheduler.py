import json
from datetime import datetime
from typing import Dict, Optional, Union

from arkaine.connectors.schedule import Schedule, Task
from arkaine.internal.registrar import Registrar
from arkaine.llms.llm import LLM, Prompt
from arkaine.tools.agent import Agent
from arkaine.tools.argument import Argument
from arkaine.tools.context import Context
from arkaine.tools.example import Example
from arkaine.tools.result import Result
from arkaine.tools.tool import Tool
from arkaine.utils.interval import Interval


class Scheduler(Tool):
    """
    A tool for scheduling tasks to run at specific times with optional
    recurrence.

    Args:
        schedule: Schedule instance to use for task management
        allow_recurrence: Whether to allow recurring tasks
    """

    def __init__(
        self,
        schedule: Schedule,
        allow_recurrence: bool = False,
    ):
        """
        Initialize the Scheduler.

        Args:
            schedule: Schedule instance to use for task management
            allow_recurrence: Whether to allow recurring tasks
        """
        if not schedule:
            raise ValueError("Schedule instance is required")

        self.__schedule = schedule
        self._allow_recurrence = allow_recurrence

        args = [
            Argument(
                name="tool_name",
                description="Name of the tool to schedule",
                type="str",
                required=True,
            ),
            Argument(
                name="tool_args",
                description="Arguments to pass to the tool when executed",
                type="dict",
                required=True,
            ),
            Argument(
                name="trigger_at",
                description=(
                    "When to trigger the task. Can be a datetime string in ISO "
                    "format (e.g. '2024-03-15T14:30:00') or 'now'"
                ),
                type="str",
                required=True,
            ),
        ]

        if allow_recurrence:
            args.append(
                Argument(
                    name="recur_every",
                    description=(
                        "How often to repeat the task. Can be: 'never', 'hourly', "
                        "'daily', 'twice a day', 'weekends', 'weekdays', 'weekly', "
                        "'fortnightly', 'monthly', 'yearly', or time-based like "
                        "'30:minutes', '2:hours', '90:seconds'"
                    ),
                    type="str",
                    required=False,
                    default="never",
                ),
            )

        examples = [
            Example(
                name="Schedule a weather check",
                args={
                    "tool_name": "weather_tool",
                    "tool_args": {"location": "New York,US"},
                    "trigger_at": "2024-03-15T09:00:00",
                },
                output={
                    "task_id": "550e8400-e29b-41d4-a716-446655440000",
                    "next_trigger": "2024-03-15T09:00:00",
                    "tool": "weather_tool",
                    "recurrence": "daily",
                },
                description="Schedule daily weather updates for New York",
            ),
            Example(
                name="Schedule a weekly check on restaurants at a location",
                args={
                    "tool_name": "local_search",
                    "tool_args": {
                        "query": "restaurants",
                        "location": "Seattle,WA",
                    },
                    "trigger_at": "now",
                    "recur_every": "weekly",
                },
                output={
                    "task_id": "550e8400-e29b-41d4-a716-446655440001",
                    "next_trigger": "2024-03-08T12:00:00",
                    "tool": "local_search",
                    "recurrence": "weekly",
                },
                description="Schedule weekly restaurant searches in Seattle",
            ),
        ]

        super().__init__(
            name="scheduler",
            description=(
                "Schedule tools to run at specific times with optional "
                "recurrence."
            ),
            args=args,
            func=self.schedule_task,
            examples=examples,
            result=Result(
                type="dict",
                description=(
                    "Information about the scheduled task including its ID, "
                    "next trigger time, tool name, and recurrence pattern"
                ),
            ),
        )

        # Start the schedule if it's not already running
        if not self.__schedule.running:
            self.__schedule.run()

    def schedule_task(
        self,
        context: Context,
        tool_name: str,
        tool_args: Dict,
        trigger_at: str,
        recur_every: Optional[str] = None,
    ) -> Dict[str, Union[str, datetime]]:
        """Schedule a task to run at a specific time."""
        # Get the tool from the registry
        tool = Registrar.get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not found")

        # Parse the trigger time
        if trigger_at.lower() == "now":
            trigger_time = datetime.now()
        else:
            try:
                trigger_time = datetime.fromisoformat(trigger_at)
            except ValueError:
                raise ValueError(
                    "trigger_at must be 'now' or a datetime in ISO format "
                    "(e.g. '2024-03-15T14:30:00')"
                )

        # Create the interval
        if self._allow_recurrence:
            trigger = Interval(trigger_time, recur_every)
        else:
            trigger = trigger_time

        # Create and add the task
        task = Task(tool=tool, args=tool_args, trigger_at=trigger)

        self.__schedule.add_task(task)

        return {
            "task_id": task.id,
            "next_trigger": task.next,
            "tool": tool_name,
            "recurrence": recur_every,
        }


class SchedulerNL(Agent):
    """
    A natural language interface for scheduling tasks. This agent converts
    natural language requests into structured scheduling commands.
    """

    def __init__(
        self,
        llm: LLM,
        scheduler: Optional[Scheduler] = None,
        schedule: Optional[Schedule] = None,
        allow_recurrence: bool = False,
    ):
        if not scheduler and not schedule:
            raise ValueError("Either scheduler or schedule must be provided")

        if not scheduler:
            scheduler = Scheduler(
                schedule=schedule, allow_recurrence=allow_recurrence
            )

        self.__scheduler = scheduler

        args = [
            Argument(
                name="request",
                description=(
                    "Natural language request describing what to schedule. Should include "
                    "the tool to run, when to run it, and any tool-specific parameters"
                ),
                type="str",
                required=True,
            )
        ]

        examples = [
            Example(
                name="schedule_nl",
                args={
                    "request": (
                        "Check the weather in New York every morning at 9 AM"
                    )
                },
                output={
                    "task_id": "550e8400-e29b-41d4-a716-446655440000",
                    "next_trigger": "2024-03-15T09:00:00",
                    "tool": "WeatherTool",
                    "recurrence": "daily",
                },
                description="Schedule daily weather updates using natural language",
            ),
            Example(
                name="schedule_nl",
                args={
                    "request": (
                        "Search for restaurants near Seattle every Sunday at noon"
                    )
                },
                output={
                    "task_id": "550e8400-e29b-41d4-a716-446655440001",
                    "next_trigger": "2024-03-17T12:00:00",
                    "tool": "LocalSearch",
                    "recurrence": "weekly",
                },
                description="Schedule weekly restaurant searches using natural language",
            ),
        ]

        super().__init__(
            name="scheduler::natural_language",
            description=(
                "Schedule tasks using natural language. Converts plain English requests "
                "into scheduled tasks with specific timing and recurrence patterns."
            ),
            args=args,
            llm=llm,
            examples=examples,
            result=Result(
                type="dict",
                description=(
                    "Information about the scheduled task including its ID, next trigger "
                    "time, tool name, and recurrence pattern"
                ),
            ),
        )

    def prepare_prompt(self, context: Context, request: str) -> Prompt:
        """Convert the natural language request into a structured prompt."""
        available_tools = [
            f"- {tool.name}: {tool.description}"
            for tool in Registrar.get_tools()
        ]

        return [
            {
                "role": "system",
                "content": (
                    "You are a scheduling assistant that converts natural "
                    "language requests into structured task schedules. You "
                    "should extract the following information from the "
                    "request:\n"
                    "1. The tool to run\n"
                    "2. The arguments for the tool\n"
                    "3. When to run it"
                    + (
                        " and recurrence"
                        if self.__scheduler._allow_recurrence
                        else ""
                    )
                    + "\n\n"
                    "Available tools:\n" + "\n".join(available_tools) + "\n\n"
                    "Output your response in JSON format with these fields:\n"
                    "- tool_name: The name of the tool to run\n"
                    "- tool_args: Dictionary of arguments for the tool\n"
                    "- trigger_at: Either 'now' or an ISO datetime\n"
                    + (
                        "- recur_every: Recurrence pattern (optional)\n\n"
                        "For recurrence, use these patterns: 'never', "
                        "'hourly', 'daily', 'twice a day', 'weekends', "
                        "'weekdays', 'weekly', 'fortnightly', 'monthly', "
                        "'yearly', or time-based intervals like "
                        "'30:minutes', '2:hours', '90:seconds'\n"
                        if self.__scheduler._allow_recurrence
                        else ""
                    )
                ),
            },
            {
                "role": "user",
                "content": "Check the weather in London every morning at 8 AM",
            },
            {
                "role": "assistant",
                "content": """{
                    "tool_name": "WeatherTool",
                    "tool_args": {
                        "location": "London,UK"
                    },
                    "trigger_at": "2024-03-15T08:00:00",
                    "recur_every": "daily"
                }""",
            },
            {"role": "user", "content": request},
        ]

    def extract_result(self, context: Context, response: str) -> Dict:
        """Process the LLM response and schedule the task."""
        try:
            # Ensure response is a valid JSON string
            if isinstance(response, str):
                schedule_args = json.loads(response)
            else:
                raise ValueError(
                    "The JSON object must be str, bytes or bytearray."
                )
            # Remove context from args if present as it's handled separately
            schedule_args.pop("context", None)
            return self.__scheduler.schedule_task(context=None, **schedule_args)
        except json.JSONDecodeError:
            raise ValueError("Failed to parse LLM response as JSON")
        except Exception as e:
            raise ValueError(f"Failed to schedule task: {str(e)}")
