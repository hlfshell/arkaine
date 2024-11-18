from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from time import time
from types import TracebackType
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from agents.registrar.registrar import Registrar
from agents.tools.events import (
    ChildContextCreated,
    ContextUpdate,
    Event,
    ToolCalled,
    ToolException,
    ToolReturn,
    ToolStart,
)
from agents.tools.types import ToolArguments


class Argument:
    def __init__(
        self,
        name: str,
        description: str,
        type: str,
        required: bool = False,
        default: Optional[str] = None,
    ):
        self.name = name
        self.description = description
        self.type = type
        self.required = required
        self.default = default

    def __str__(self) -> str:
        out = f"{self.name} - {self.type} - Required: "
        out += f"{self.required} - "
        if self.default:
            out += f"Default: {self.default} - "
        out += f"{self.description}"

        return out


class Example:
    def __init__(
        self,
        name: str,
        args: Dict[str, str],
        output: Optional[str] = None,
        description: Optional[str] = None,
        explanation: Optional[str] = None,
    ):
        self.name = name
        self.args = args
        self.output = output
        self.description = description
        self.explanation = explanation

    @classmethod
    def ExampleBlock(cls, function_name: str, example: Example) -> str:
        out = ""
        if example.description:
            out += f"{example.description}\n"
        out += f"{function_name}("

        args_str = ", ".join(
            [f"{arg}={value}" for arg, value in example.args.items()]
        )
        out += f"{args_str})"

        if example.output:
            out += f"\nReturns:\n{example.output}"

        if example.explanation:
            out += f"\nExplanation: {example.explanation}"

        return out


class Context:
    """
    Context is a thread safe class that tracks what each execution of a tool
    does. Contexts track the execution of a singular tool/agent, and can
    consist of sub-tools/sub-agents and their own contexts. The parent context
    thus tracks the history of the entire execution even as it branches out. A
    tool can modify what it stores and how it represents its actions through
    Events, but the following attributes are always present in a context:

    1. id - a unique identifier for this particular execution
    2. children - a list of child contexts
    3. status - a string that tracks the status of the execution; can be one
       of:
        - "running"
        - "complete"
        - "cancelled" TODO
        - "error"
    3. output - what the final output of the tool was, if any
    4. history - a temporally ordered list of events that occurred during the
       execution of that specific tool/agent
    5. name - a human readable name for the tool/agent

    Updates to the context are broadcasted under the event type ContextUpdate
    ("context_update" for the listeners)
    """

    def __init__(self, tool: Tool, parent: Optional[Context] = None):
        self.__id = str(uuid4())
        self.__tool = tool
        self.__parent = parent
        self.__tool = tool

        self.__root: Optional[Context] = None
        # Trigger getter to hunt for root
        self.__root

        self.__exception: Exception = None
        self.__output: Any = None
        self.__created_at = time()

        self.__children: List[Context] = []

        self.__event_listeners: Dict[
            str, List[Callable[[Context, Event], None]]
        ] = {"all": []}

        self.__history: List[Event] = []

        self.__lock = threading.Lock()
        self.__status_changed = threading.Event()

        # No max workers due to possible lock synchronization issues
        self.__executor = ThreadPoolExecutor(
            thread_name_prefix=f"context-{self.__id}"
        )

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type: Optional[Exception],
        exc_value: Optional[Exception],
        traceback: Optional[TracebackType],
    ) -> bool:
        if exc_type is not None:
            self.exception(exc_value)
        return False

    def __del__(self):
        self.__executor.shutdown(wait=False)
        self.__event_listeners.clear()
        self.__children.clear()

    @property
    def root(self) -> Context:
        with self.__lock:
            if self.__root is not None:
                return self.__root
            if self.__parent is None:
                return self
            self.__root = self.__parent.root
            return self.__root

    @property
    def tool(self) -> Tool:
        return self.__tool

    def child_context(self, tool: Tool) -> Context:
        """Create a new child context for the given tool."""
        ctx = Context(tool=tool, parent=self)
        with self.__lock:
            self.__children.append(ctx)

        # All events happening in the children contexts are broadcasted
        # to their parents as well so the root context receives all events
        ctx.add_listener(
            lambda ctx, event: self.broadcast(event, source_context=ctx)
        )

        # Broadcast that we created a child context
        self.broadcast(ChildContextCreated(self.id, ctx.id))
        return ctx

    # @property
    # def name(self) -> str:
    #     return self.__name

    # @name.setter
    # def name(self, value: str):
    #     with self.__lock:
    #         self.__name = value
    #     self.broadcast(ContextUpdate(name=value))

    @property
    def is_root(self) -> bool:
        return self.__parent is None

    @property
    def status(self) -> str:
        with self.__lock:
            if self.__exception:
                return "error"
            elif self.__output is not None:
                return "complete"
            else:
                return "running"

    @property
    def id(self) -> str:
        return self.__id

    def add_listener(
        self,
        listener: Callable[[Context, Event], None],
        event_type: Optional[str] = None,
    ):
        with self.__lock:
            if event_type is None or event_type == "all":
                self.__event_listeners["all"].append(listener)
            else:
                if event_type not in self.__event_listeners:
                    self.__event_listeners[event_type] = []
                self.__event_listeners[event_type].append(listener)

    def broadcast(self, event: Event, source_context: Optional[Context] = None):
        """
        id is optional and overrides using the current id, usually because
        its an event actually from a child context or deeper.
        """
        if source_context is None:
            source_context = self

        with self.__lock:
            self.__history.append(event)

            for listener in self.__event_listeners["all"]:
                self.__executor.submit(listener, source_context, event)
            if event._event_type in self.__event_listeners:
                for listener in self.__event_listeners[event._event_type]:
                    self.__executor.submit(listener, source_context, event)

    def exception(self, e: Exception):
        self.broadcast(ToolException(e))

        with self.__lock:
            self.__exception = e
        self.__status_changed.set()

    @property
    def output(self) -> Any:
        with self.__lock:
            return self.__output

    @output.setter
    def output(self, value: Any):
        with self.__lock:
            if self.__output:
                raise ValueError("Output already set")
            self.__output = value

        self.__status_changed.set()
        self.broadcast(ToolReturn(self.tool.id, value))

    def wait(self, timeout: Optional[float] = None):
        while True:
            self.__status_changed.wait(timeout=timeout or 0.1)
            if timeout or self.status != "running":
                break

        self.__status_changed.clear()

    def to_json(self) -> dict:
        """Convert Context to a JSON-serializable dictionary."""
        # We have to grab certain things prior to the lock to avoid
        # competing locks. This introduces a possible race condition
        # but should be fine for most purposes for now.
        status = self.status
        output = self.__output

        with self.__lock:
            history = [event.to_json() for event in self.__history]

            if hasattr(output, "to_json"):
                output = output.to_json()
            else:
                try:
                    json.dumps(output)
                except (TypeError, ValueError):
                    try:
                        output = str(output)
                    except Exception:
                        output = "Unable to serialize output"

        # Build and return the complete dictionary while still holding the
        # lock
        return {
            "id": self.__id,
            # "name": self.__name,
            "parent_id": self.__parent.id if self.__parent else None,
            "root_id": self.root.id,
            "tool_id": self.__tool.id,
            "status": status,
            "output": output,
            "history": history,
            "created_at": self.__created_at,
            "children": [child.to_json() for child in self.__children],
            "error": str(self.__exception) if self.__exception else None,
        }


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        args: List[Argument],
        func: Callable,
        examples: List[Example] = [],
    ):
        self.__id = str(uuid4())
        self.name = name
        self.description = description
        self.args = args
        self.func = func
        self.examples = examples
        self._on_call_listeners: List[Callable[[Tool, Context], None]] = []
        self._called_event = ToolCalled
        self._return_event = ToolReturn

        self._executor = ThreadPoolExecutor()

        Registrar.register(self)

    def __del__(self):
        self._executor.shutdown(wait=False)

    @property
    def id(self) -> str:
        return self.__id

    def __init_context_(self, context: Optional[Context], **kwargs) -> Context:
        if context and not context.is_root:
            ctx = context.child_context(self)
        elif context and context.is_root:
            ctx = context
        else:
            ctx = Context(self)

        ctx.broadcast(self._called_event(self, kwargs))

        for listener in self._on_call_listeners:
            self._executor.submit(listener, self, ctx)

        return ctx

    def invoke(self, context: Context, **kwargs) -> Any:
        return self.func(**kwargs)

    def __call__(self, context: Optional[Context] = None, **kwargs) -> Any:
        with self.__init_context_(context, **kwargs) as ctx:

            kwargs = self.fulfill_defaults(kwargs)

            self.check_arguments(kwargs)

            ctx.broadcast(ToolStart(self.name))

            results = self.invoke(ctx, **kwargs)

            if ctx:
                ctx.output = results
                ctx.broadcast(self._return_event(self.name, results))

            return results

    def examples_text(
        self, example_format: Optional[Callable[[Example], str]] = None
    ) -> List[str]:
        if not example_format:
            example_format = Example.ExampleBlock

        return [example_format(self.name, example) for example in self.examples]

    def __str__(self) -> str:
        return Tool.stringify(self)

    def fulfill_defaults(self, args: ToolArguments) -> ToolArguments:
        """
        Given a set of arguments, check to see if any argument that is assigned
        a default value is missing a value and, if so, fill it with the
        default.
        """
        for arg in self.args:
            if arg.name not in args and arg.default:
                args[arg.name] = arg.default

        return args

    def check_arguments(self, args: ToolArguments):
        missing_args = []
        extraneous_args = []

        arg_names = [arg.name for arg in self.args]
        for arg in args.keys():
            if arg not in arg_names:
                extraneous_args.append(arg)

        for arg in self.args:
            if arg.required and arg.name not in args:
                missing_args.append(arg.name)

        if missing_args or extraneous_args:
            raise InvalidArgumentException(
                self.name, missing_args, extraneous_args
            )

    @staticmethod
    def stringify(tool: Tool) -> str:
        # Start with the tool name and description
        output = f"> Tool Name: {tool.name}\n"

        # Break the long line into multiple lines
        args_str = ", ".join([f"{arg.name}: {arg.type}" for arg in tool.args])
        output += f"Tool Description: {tool.name}({args_str})\n\n"

        # Add the function description, indented with 4 spaces
        output += f"    {tool.description}\n"

        # Add the Tool Args section
        output += "    \n"
        output += "Tool Args: {"

        # Create the properties dictionary
        properties = {
            arg.name: {
                "title": arg.name,
                "type": arg.type,
                "default": arg.default,
            }
            for arg in tool.args
        }

        # Create the required list
        required = [arg.name for arg in tool.args if arg.required]

        # Add properties and required to the output
        output += f'"properties": {properties}, '
        output += f'"required": {required}' + "}"

        return output

    def add_on_call_listener(self, listener: Callable[[Tool, Context], None]):
        self._on_call_listeners.append(listener)


class InvalidArgumentException(Exception):
    def __init__(
        self,
        tool_name: str,
        missing_required_args: List[str],
        extraneous_args: List[str],
    ):
        self.__tool_name = tool_name
        self.__missing_required_args = missing_required_args
        self.__extraneous_args = extraneous_args

    def __str__(self):
        out = f"Function {self.__tool_name} was improperly called\n"

        if self.__missing_required_args:
            out += (
                "Missing required arguments: "
                + ", ".join(self.__missing_required_args)
                + "\n"
            )
        if self.__extraneous_args:
            out += (
                "Extraneous arguments: "
                + ", ".join(self.__extraneous_args)
                + "\n"
            )

        return out
