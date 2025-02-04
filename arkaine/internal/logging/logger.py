"""Logger module for tracking and displaying context execution and events."""

import json
import sys
from threading import Lock
from typing import Any, Dict, Optional, TextIO

from arkaine.internal.registrar import Registrar
from arkaine.tools.context import Attachable, Context
from arkaine.tools.events import Event
from arkaine.tools.tool import Tool


class Colors:
    """ANSI color codes for terminal output formatting."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"


class Logger:
    """Thread-safe logger for context execution and events.

    Provides real-time and post-execution logging of contexts and their events,
    with support for colored output and JSON export.
    """

    def __init__(
        self,
        output_stream: Optional[TextIO] = sys.stdout,
        use_colors: bool = True,
        indent_size: int = 2,
        event_colors: Optional[Dict[str, str]] = None,
    ):
        """Initialize the logger with specified configuration.

        Args:
            output_stream: Where to write log output. Defaults to stdout.
            use_colors: Whether to use ANSI colors in output. Defaults to True.
            indent_size: Number of spaces for JSON indentation. Defaults to 2.
            event_colors: Custom color mapping for event types.
        """
        self.output_stream = output_stream
        self.use_colors = use_colors
        self.indent_size = indent_size
        self._lock = Lock()
        self._event_colors = (
            event_colors
            if event_colors
            else {
                "child_context_created": Colors.GREEN,
                "context_update": Colors.BLUE,
                "context_exception": Colors.RED,
                "context_output": Colors.CYAN,
                "agent_called": Colors.YELLOW,
                "agent_prompt": Colors.MAGENTA,
                "agent_llm_response": Colors.CYAN,
                "tool_called": Colors.YELLOW,
                "tool_return": Colors.GREEN,
            }
        )

    def attach_tool(self, tool: Tool):
        """
        Attach a tool to the logger such that whenever the tool is utilized the
        logger will appropriately log the resulting context and all sub events.
        """
        tool.add_on_call_listener(self.on_tool_call)

    def on_producer_call(self, producer: Attachable, context: Context):
        # Subscribe to the context events
        context.add_event_listener(self.log_event, ignore_children_events=True)

    def _colorize(self, text: str, color: str) -> str:
        """Apply ANSI color codes to text if colors are enabled.

        Args:
            text: The text to colorize. color: The ANSI color code to apply.

        Returns:
            The text with color codes if colors are enabled, otherwise
            unchanged.
        """
        if self.use_colors:
            return f"{color}{text}{Colors.RESET}"
        return text

    def _format_data(self, data: Any) -> str:
        """
        Format data for display, using JSON formatting when possible.

        Args:
            data: The data to format.

        Returns:
            A string representation of the data.
        """
        if data is None:
            return ""

        if isinstance(data, (dict, list)):
            try:
                return json.dumps(data, indent=self.indent_size)
            except (TypeError, ValueError):
                return str(data)
        return str(data)

    def _format_event(self, event: Event, context: Context) -> str:
        """
        Format an event for display with context information.

        Args:
            event: The event to format. context: The context object containing
            the event.

        Returns:
            A formatted string representing the event.
        """
        color = self._event_colors.get(event._event_type, Colors.GRAY)
        timestamp = event._get_readable_timestamp()
        event_type = event._event_type.replace("_", " ").title()

        # Build the header with context information
        header = f"{timestamp} - {event_type}"

        # Add tool name for tool-related events
        header += f" [{context.attached.name} | {context.attached.id}]"

        # Format the event data
        if event.data:
            # Use to_json if available
            if hasattr(event.data, "to_json"):
                formatted_data = self._format_data(event.data.to_json())
            else:
                formatted_data = self._format_data(event.data)

            if formatted_data:
                if "\n" in formatted_data:
                    indented_data = "\n".join(
                        f"    {line}" for line in formatted_data.split("\n")
                    )
                    result = f"{header}:\n{indented_data}"
                else:
                    result = f"{header}:\n    {formatted_data}"
            else:
                result = header
        else:
            result = header

        return self._colorize(result, color)

    def _write(self, text: str):
        """Write text to output stream in a thread-safe manner.

        Args:
            text: The text to write.
        """
        if self.output_stream:
            with self._lock:
                self.output_stream.write(f"{text}\n")
                self.output_stream.flush()

    def log_event(self, context: Context, event: Event):
        """Log a single event with optional context information.

        Args:
            event: The event to log.
            context: The executing context
        """
        formatted = self._format_event(event, context)
        self._write(formatted)

    def cleanup(self):
        self.output_stream = None

    def __del__(self):
        self.cleanup()


class GlobalLogger:
    """
    Global logger is just a singleton instance of a logger
    that utilizes the registrar to automatically detect and
    thus log all tools.
    """

    _instance: Logger = None

    def __init__(self):
        raise ValueError("GlobalLogger is a singleton")

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = Logger()
        return cls._instance

    @classmethod
    def enable(cls):
        Registrar.enable()
        instance = cls.get_instance()
        Registrar.add_on_producer_call(instance.on_producer_call)

    @classmethod
    def disable(cls):
        del cls._instance
