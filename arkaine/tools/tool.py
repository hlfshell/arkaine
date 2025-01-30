from __future__ import annotations

import inspect
import json
import threading
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event as ThreadEvent
from time import time
from types import TracebackType
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from uuid import uuid4

from arkaine.internal.options.context import ContextOptions
from arkaine.internal.registrar import Registrar
from arkaine.internal.to_json import recursive_to_json
from arkaine.tools.argument import Argument, InvalidArgumentException
from arkaine.tools.datastore import ThreadSafeDataStore
from arkaine.tools.events import (
    ChildContextCreated,
    ContextUpdate,
    Event,
    ToolCalled,
    ToolException,
    ToolReturn,
)
from arkaine.tools.example import Example
from arkaine.tools.result import Result
from arkaine.tools.types import ToolArguments


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
    6. args - the arguments passed to the tool/agent for this execution

    Contexts also have a controlled set of data features meant for potential
    debugging or passing of state information throughout a tool's lifetime. To
    access this data, you can use ctx["key"] = value and similar notation - it
    implements a ThreadSafeDataStore in the background, adding additional
    thread safe nested attribute operations. Data stored and used in this
    manner is for a single level of context, for this tool alone. If you wish
    to have inter tool state sharing, utilize the x attribute, which is a
    ThreadSafeDataStore that is shared across all contexts in the chain by
    attaching to the root context. This data store is unique to the individual
    execution of the entire tool chain (hence x, for execution), and allows a
    thread safe shared data store for multiple tools simultaneously.

    Updates to the context's attributes are broadcasted under the event type
    ContextUpdate ("context_update" for the listeners). The output is
    broadcasted as tool_return, and errors/exceptions as tool_exception.

    Contexts can have listeners assigned. They are:
        - event listeners via add_event_listener() - with an option to filter
          specific event types, and whether or not to ignore propagated
          children's events
        - output listeners - when the context's output value is set
        - error listeners - when the context's error value is set
        - on end - when either the output or the error value is set

    Events in contexts can be utilized for your own purposes as well utilizing
    the broadcast() function, as long as they follow the Event class's
    interface.

    Contexts have several useful flow control functions as well:
        - wait() - wait for the context to complete (blocking)
        - future() - returns a concurrent.futures.Future object for the context
          to be compatible with standard async approaches
        - cancel() - cancel the context NOT IMPLEMENTED

    A context's executing attribute is assigned once, when it is utilized by a
    tool or agent. It can never be changed, and is utilized to determine if a
    context is being passed to create a child context or if its being passed to
    be utilized as the current execution's context. If the context is marked as
    executing already, a child context will be created as it is implied that
    this context is the root of the execution of the tool. If the execution is
    not marked as executing, the context is assumed to be the root of the
    execution process and utilized as the tool's current context.
    """

    def __init__(
        self,
        tool: Optional[Tool] = None,
        parent: Optional[Context] = None,
        llm: Optional["LLM"] = None,
    ):
        self.__id = str(uuid4())
        self.__executing = False
        self.__tool = tool
        self.__parent = parent
        self.__llm = llm

        if self.__llm is None and hasattr(tool, "completion"):
            self.__tool = None
            self.__llm = tool

        self.__root: Optional[Context] = None
        # Trigger getter to hunt for root
        self.__root

        self.__exception: Exception = None
        self.__args: Dict[str, Any] = {}
        self.__output: Any = None
        self.__created_at = time()

        self.__children: List[Context] = []

        self.__event_listeners_all: Dict[
            str, List[Callable[[Context, Event], None]]
        ] = {"all": []}
        self.__event_listeners_filtered: Dict[
            str, List[Callable[[Context, Event], None]]
        ] = {"all": []}

        self.__on_output_listeners: List[Callable[[Context, Any], None]] = []
        self.__on_exception_listeners: List[
            Callable[[Context, Exception], None]
        ] = []
        self.__on_end_listeners: List[Callable[[Context], None]] = []

        self.__history: List[Event] = []

        self.__lock = threading.Lock()

        self.__data: ThreadSafeDataStore = ThreadSafeDataStore(
            context=self.__id, label="data"
        )
        self.__x: ThreadSafeDataStore = ThreadSafeDataStore(
            context=self.__id, label="x"
        )
        self.__debug: ThreadSafeDataStore = ThreadSafeDataStore(
            context=self.__id, label="debug"
        )

        # No max workers due to possible lock synchronization issues
        self.__executor = ThreadPoolExecutor(
            thread_name_prefix=f"context-{self.__id}"
        )

        self.__completion_event = ThreadEvent()

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type: Optional[Exception],
        exc_value: Optional[Exception],
        traceback: Optional[TracebackType],
    ) -> bool:
        if exc_type is not None:
            self.exception = exc_value

        try:
            ContextOptions.get_store().save(self)
        except:  # noqa: E722
            pass

        return False

    def __del__(self):
        self.__executor.shutdown(wait=False)
        self.__event_listeners_all.clear()
        self.__event_listeners_filtered.clear()
        self.__children.clear()

    def __getitem__(self, name: str) -> Any:
        return self.__data[name]

    def __setitem__(self, name: str, value: Any):
        self.__data[name] = value

    def __contains__(self, name: str) -> bool:
        return name in self.__data

    def __delitem__(self, name: str):
        del self.__data[name]

    @property
    def x(self) -> ThreadSafeDataStore:
        if self.is_root:
            return self.__x
        else:
            return self.root.x

    @property
    def debug(self) -> ThreadSafeDataStore:
        if self.is_root:
            return self.__debug
        else:
            return self.root.debug

    def operate(
        self, keys: Union[str, List[str]], operation: Callable[[Any], Any]
    ) -> None:
        self.__data.operate(keys, operation)

    def update(self, key: str, operation: Callable) -> Any:
        return self.__data.update(key, operation)

    def increment(self, key: str, amount=1):
        return self.__data.increment(key, amount)

    def decrement(self, key: str, amount=1):
        return self.__data.decrement(key, amount)

    def append(self, keys: Union[str, List[str]], value: Any) -> None:
        self.__data.append(keys, value)

    def concat(self, keys: Union[str, List[str]], value: Any) -> None:
        self.__data.concat(keys, value)

    @property
    def _datastores(
        self,
    ) -> Tuple[ThreadSafeDataStore, ThreadSafeDataStore, ThreadSafeDataStore]:
        return self.__data, self.__x, self.__debug

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

    @tool.setter
    def tool(self, tool: Tool):
        with self.__lock:
            if self.__tool:
                raise ValueError("Tool already set")
            self.__tool = tool

        self.broadcast(
            ContextUpdate(tool_id=self.tool.id, tool_name=self.tool.name)
        )

    @property
    def llm(self) -> "LLM":
        return self.__llm

    @llm.setter
    def llm(self, llm: "LLM"):
        with self.__lock:
            if self.__llm:
                raise ValueError("LLM already set")
            self.__llm = llm

    @property
    def parent(self) -> Context:
        return self.__parent

    @property
    def children(self) -> List[Context]:
        with self.__lock:
            return self.__children

    @property
    def events(self) -> List[Event]:
        with self.__lock:
            return self.__history

    def child_context(self, tool_or_llm: Union[Tool, "LLM"]) -> Context:
        """Create a new child context for the given tool."""
        if isinstance(tool_or_llm, Tool):
            ctx = Context(tool=tool_or_llm, parent=self)
        elif hasattr(tool_or_llm, "completion"):
            ctx = Context(llm=tool_or_llm, parent=self)
        elif hasattr(tool_or_llm, "bash"):
            ctx = Context(tool=tool_or_llm, parent=self)
        else:
            raise ValueError(
                f"Invalid type for child context: {type(tool_or_llm)}"
            )

        with self.__lock:
            self.__children.append(ctx)

        # All events happening in the children contexts are broadcasted
        # to their parents as well so the root context receives all events
        ctx.add_event_listener(
            lambda event_context, event: self.broadcast(
                event,
                source_context=event_context,
            )
        )

        # Broadcast that we created a child context
        self.broadcast(ChildContextCreated(self.id, ctx.id))
        return ctx

    def clear(
        self,
        executing: bool = False,
        args: Optional[Dict[str, Any]] = None,
    ):
        """
        Clears the context for re-running. This removes the output, the
        exceptions, and sets __executing to False. The completion event is
        triggered to clear whatever is waiting on the context to complete
        first.

        You can opt to maintain the executing state, and/or args; By default
        they are "cleared" as well.
        """
        self.__completion_event.set()
        with self.__lock:
            self.__output = None
            self.__exception = None
            self.__executing = executing
            self.__args = args

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

    @property
    def executing(self) -> bool:
        with self.__lock:
            return self.__executing

    @executing.setter
    def executing(self, executing: bool):
        with self.__lock:
            if self.__executing:
                raise ValueError("already executing")
            self.__executing = executing

    def add_event_listener(
        self,
        listener: Callable[[Context, Event], None],
        event_type: Optional[str] = None,
        ignore_children_events: bool = False,
    ):
        """
        Adds a listener to the context. If ignore_children_events is True, the
        listener will not be notified of events from child contexts, only from
        this context. The event_type, if not specified, or set to "all", will
        return all events.

        Args:
            listener (Callable[[Context, Event], None]): The listener to add
            event_type (Optional[str]): The type of event to listen for, or
                "all" to listen for all events
            ignore_children_events (bool): If True, the listener will not be
                notified of events from child contexts
        """
        with self.__lock:
            event_type = event_type or "all"
            if ignore_children_events:
                if event_type not in self.__event_listeners_filtered:
                    self.__event_listeners_filtered[event_type] = []
                self.__event_listeners_filtered[event_type].append(listener)
            else:
                if event_type not in self.__event_listeners_all:
                    self.__event_listeners_all[event_type] = []
                self.__event_listeners_all[event_type].append(listener)

    def broadcast(self, event: Event, source_context: Optional[Context] = None):
        """
        id is optional and overrides using the current id, usually because
        its an event actually from a child context or deeper.
        """
        if source_context is None:
            source_context = self

        with self.__lock:
            if source_context.id == self.id:
                self.__history.append(event)

            for listener in self.__event_listeners_all["all"]:
                self.__executor.submit(listener, source_context, event)
            if event._event_type in self.__event_listeners_all:
                for listener in self.__event_listeners_all[event._event_type]:
                    self.__executor.submit(listener, source_context, event)

            if source_context.id == self.id:
                for listener in self.__event_listeners_filtered["all"]:
                    self.__executor.submit(listener, source_context, event)
                if event._event_type in self.__event_listeners_filtered:
                    for listener in self.__event_listeners_filtered[
                        event._event_type
                    ]:
                        self.__executor.submit(listener, source_context, event)

    def add_on_output_listener(self, listener: Callable[[Context, Any], None]):
        with self.__lock:
            self.__on_output_listeners.append(listener)

    def add_on_exception_listener(
        self, listener: Callable[[Context, Exception], None]
    ):
        with self.__lock:
            self.__on_exception_listeners.append(listener)

    def add_on_end_listener(self, listener: Callable[[Context], None]):
        with self.__lock:
            self.__on_end_listeners.append(listener)

    def wait(self, timeout: Optional[float] = None):
        """
        Wait for the context to complete (either with a result or exception).

        Args:
            timeout: Maximum time to wait in seconds. If None, wait
            indefinitely.

        Raises:
            TimeoutError: If the timeout is reached before completion The
            original exception: If the context failed with an exception
        """
        with self.__lock:
            if self.__output is not None or self.__exception is not None:
                return

        if not self.__completion_event.wait(timeout):
            with self.__lock:
                if self.__output is not None or self.__exception is not None:
                    return

            e = TimeoutError(
                "Context did not complete within the specified timeout"
            )
            self.__exception = e
            raise e

    def future(self) -> Future:
        """Return a concurrent.futures.Future object for the context."""
        future = Future()

        def on_end(context: Context):
            if self.exception:
                future.set_exception(self.exception)
            else:
                future.set_result(self.output)

        # Due to timing issues, we have to manually create the listeners within
        # the lock instead of our usual methods to avoid race conditions.
        with self.__lock:
            if self.__output is not None:
                future.set_result(self.__output)
                return future
            if self.__exception is not None:
                future.set_exception(self.__exception)
                return future

            self.__on_end_listeners.append(on_end)

        return future

    def cancel(self):
        """Cancel the context."""
        raise NotImplementedError("Not implemented")

    @property
    def exception(self) -> Optional[Exception]:
        with self.__lock:
            return self.__exception

    @exception.setter
    def exception(self, e: Optional[Exception]):
        if e is None:
            with self.__lock:
                self.__exception = e
        else:
            self.broadcast(ToolException(e))
            with self.__lock:
                self.__exception = e
            self.__completion_event.set()

            for listener in self.__on_exception_listeners:
                self.__executor.submit(listener, self, e)
            for listener in self.__on_end_listeners:
                self.__executor.submit(listener, self)

    @property
    def args(self) -> Dict[str, Any]:
        with self.__lock:
            return self.__args

    @args.setter
    def args(self, args: Optional[Dict[str, Any]]):
        with self.__lock:
            if self.__args and args:
                raise ValueError("args already set")
            self.__args = args

    @property
    def output(self) -> Any:
        with self.__lock:
            return self.__output

    @output.setter
    def output(self, value: Any):
        with self.__lock:
            if value is None:
                self.__output = None
                self.__completion_event.set()
                return
            if self.__output:
                raise ValueError("output already set")
            self.__output = value
        self.__completion_event.set()

        for listener in self.__on_output_listeners:
            self.__executor.submit(listener, self, value)
        for listener in self.__on_end_listeners:
            self.__executor.submit(listener, self)

    def to_json(self, children: bool = True, debug: bool = True) -> dict:
        """Convert Context to a JSON-serializable dictionary."""
        # We have to grab certain things prior to the lock to avoid
        # competing locks. This introduces a possible race condition
        # but should be fine for most purposes for now.
        status = self.status
        output = self.output

        if self.exception:
            exception = f"\n{self.exception}\n\n"

            exception += "".join(
                traceback.format_exception(
                    type(self.exception),
                    self.exception,
                    self.exception.__traceback__,
                )
            )
        else:
            exception = None

        root = self.root

        with self.__lock:
            history = [event.to_json() for event in self.__history]

            if output:
                output = recursive_to_json(output)

            data = self.__data.to_json()

            if root.id == self.id:
                x = root.x.to_json()
            else:
                x = None

            if debug:
                debug = self.__debug.to_json()
            else:
                debug = None

        args = recursive_to_json(self.args)

        if children:
            children = [child.to_json() for child in self.__children]
        else:
            children = []

        return {
            "id": self.__id,
            "parent_id": self.__parent.id if self.__parent else None,
            "root_id": self.root.id,
            "tool_id": None if not self.__tool else self.__tool.id,
            "tool_name": None if not self.__tool else self.__tool.name,
            "llm_name": None if not self.__llm else self.__llm.name,
            "status": status,
            "args": args,
            "output": output,
            "history": history,
            "created_at": self.__created_at,
            "children": children,
            "error": exception,
            "data": data,
            "x": x,
            "debug": debug,
        }

    def save(
        self,
        filepath: str,
        children: bool = True,
        debug: bool = True,
    ):
        """
        Save the context and (by default, but toggleable) all children context
        to the given filepath. Note that outputs or attached data are not
        necessarily saved if they can't be converted to JSON. All of the
        arguments, data, and outputs are first checked for a to_json method,
        then via json.dumps, and finally just an attempted str() conversion.
        Finally, if all of this fails, it is saved as "Unable to serialize" and
        that data is lost.

        All x data is recorded only if it is the root context.

        Args:
            filepath: The path to save the context to
            children: Whether to expand children contexts
            debug: Whether to save debug information if present
        """
        json_data = self.to_json(children=children, debug=debug)

        # Save the context
        with open(filepath, "w") as f:
            json.dump(json_data, f)

    @classmethod
    def load(cls, filepath: str) -> Context:
        """
        Load a context and its children from a JSON file.

        Args:
            filepath: Path to the JSON file containing the context data

        Returns:
            Context: The reconstructed context object

        Note:
            Tool references are resolved in the following order:
            1. By tool ID from the Registrar
            2. By tool name from the Registrar
            3. Set to None if no matching tool is found
        """
        with open(filepath, "r") as f:
            data = json.load(f)

        return cls.__load_from_json(data)

    @classmethod
    def __load_from_json(cls, data: dict) -> Context:
        """Create a context object from JSON data."""
        # Find the associated tool
        tool = cls._find_tool(data.get("tool_id"), data.get("tool_name"))

        # Create the base context
        context = cls(tool=tool)

        # Load the basic properties
        context.__id = data["id"]
        context.__created_at = data["created_at"]

        # Load args
        if data.get("args"):
            context.__args = data["args"]

        # Load output if present
        if data.get("output") is not None:
            context.__output = data["output"]

        # Load error if present
        if data.get("error"):
            context.__exception = Exception(data["error"])

        # Load data stores
        if data.get("data"):
            context.__data = ThreadSafeDataStore.from_json(data["data"])
        if (
            data.get("x") and data.get("parent_id") is None
        ):  # Only load x data for root
            context.__x = ThreadSafeDataStore.from_json(data["x"])
        if data.get("debug"):
            context.__debug = ThreadSafeDataStore.from_json(data["debug"])

        # Load history
        if data.get("history"):
            context.__history = cls.__load_history(data["history"])

        # Load children recursively
        if data.get("children"):
            for child_data in data["children"]:
                child = cls.__load_from_json(child_data)
                child.__parent = context
                context.__children.append(child)

        return context

    @staticmethod
    def _find_tool(
        tool_id: Optional[str], tool_name: Optional[str]
    ) -> Optional[Tool]:
        """Find a tool by ID or name from the Registrar."""
        tools = Registrar.get_tools()

        # Try finding by ID first
        if tool_id:
            for tool in tools:
                if tool.id == tool_id:
                    return tool

        # Try finding by name if ID search failed
        if tool_name:
            for tool in tools:
                if tool.name == tool_name:
                    return tool

        return None

    @staticmethod
    def __load_history(history_data: List[dict]) -> List[Event]:
        """Convert history data back into Event objects."""
        events = []
        for event_data in history_data:
            event_type = event_data.get("_event_type")
            if event_type == "tool_called":
                events.append(ToolCalled(event_data.get("args", {})))
            elif event_type == "tool_return":
                events.append(ToolReturn(event_data.get("value")))
            elif event_type == "tool_exception":
                events.append(
                    ToolException(Exception(event_data.get("error", "")))
                )
            elif event_type == "context_update":
                events.append(
                    ContextUpdate(
                        event_data.get("tool_id"), event_data.get("tool_name")
                    )
                )
            elif event_type == "child_context_created":
                events.append(
                    ChildContextCreated(
                        event_data.get("parent_id"), event_data.get("child_id")
                    )
                )
        return events


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        args: List[Argument],
        func: Callable,
        examples: List[Example] = [],
        id: Optional[str] = None,
        result: Optional[Result] = None,
    ):
        self.__id = id or str(uuid4())
        self.name = name
        self.description = description
        self.args = args
        self.func = func
        self.examples = examples
        self._on_call_listeners: List[Callable[[Tool, Context], None]] = []
        self.result = result
        self._executor = ThreadPoolExecutor()

        Registrar.register(self)

    def __del__(self):
        if self._executor:
            self._executor.shutdown(wait=False)

    @property
    def id(self) -> str:
        return self.__id

    @property
    def tname(self) -> str:
        """
        Short for tool name, it removes wrapper and modifying monikers
        by only grabbing the name prior to any "::"
        """
        return self.name.split("::")[0]

    def get_context(self) -> Context:
        """
        get_context returns a blank context for use with this tool.
        """
        return Context(self)

    def _init_context_(self, context: Optional[Context], kwargs) -> Context:
        if context is None:
            ctx = Context(self)
        else:
            ctx = context

        if ctx.executing:
            ctx = context.child_context(self)
            ctx.executing = True
        else:
            if not ctx.tool and not ctx.llm:
                ctx.tool = self
            ctx.executing = True

        ctx.args = kwargs
        ctx.broadcast(ToolCalled(kwargs))
        for listener in self._on_call_listeners:
            self._executor.submit(listener, self, ctx)

        return ctx

    def invoke(self, context: Context, **kwargs) -> Any:
        params = inspect.signature(self.func).parameters
        if "context" in params:
            if params["context"].kind == inspect.Parameter.VAR_POSITIONAL:
                return self.func(context, **kwargs)
            else:
                return self.func(context=context, **kwargs)
        else:
            return self.func(**kwargs)

    def extract_arguments(self, args, kwargs):
        # Extract context if present as first argument
        context = None
        if args and isinstance(args[0], Context):
            context = args[0]
            args = args[1:]  # Remove context from args

        # Handle single dict argument case
        if len(args) == 1 and not kwargs and isinstance(args[0], dict):
            kwargs = args[0]
            args = ()

        # Map remaining positional args to their parameter names
        tool_args = [arg.name for arg in self.args]
        for i, value in enumerate(args):
            if i < len(tool_args):
                if tool_args[i] in kwargs:
                    raise TypeError(
                        f"Got multiple values for argument '{tool_args[i]}'"
                    )
                kwargs[tool_args[i]] = value

        # Check to see if context is in the kwargs
        if "context" in kwargs:
            if context is not None:
                raise ValueError("context passed twice")
            context = kwargs.pop("context")

        return context, kwargs

    def __call__(self, *args, **kwargs) -> Any:
        context, kwargs = self.extract_arguments(args, kwargs)

        with self._init_context_(context, kwargs) as ctx:
            kwargs = self.fulfill_defaults(kwargs)
            self.check_arguments(kwargs)
            ctx.broadcast(ToolCalled(self.name))

            results = self.invoke(ctx, **kwargs)
            ctx.output = results
            ctx.broadcast(ToolReturn(results))
            return results

    def async_call(
        self, context: Optional[Context] = None, *args, **kwargs
    ) -> Context:
        _, kwargs = self.extract_arguments(args, kwargs)

        if context is None:
            context = Context()
        else:
            # If we are passed a context, we need to determine if its a new
            # context or if it is an existing one that means we need to create
            # a child context. We don't mark it as executing so that the call
            # itself can do this. If it isn't executing we'll just continue
            # using the current context.
            if context.executing:
                context = context.child_context(self)

        def wrapped_call(context: Context, **kwargs):
            try:
                self.__call__(context, **kwargs)
            except Exception as e:
                context.exception = e

        # Use the existing thread pool instead of creating raw threads
        self._executor.submit(wrapped_call, context, **kwargs)

        return context

    def retry(self, context: Context) -> Any:
        """
        Retry the tool call. This function is expected to be overwritten by
        implementing class tools that have more complicated logic to make
        retrying more effective.
        """

        # Ensure that the context passed is in fact a context for this tool
        if context.tool is None:
            raise ValueError(f"no tool assigned to context")
        if context.tool != self:
            raise ValueError(
                f"context is not for {self.name}, is instead for "
                f"{context.tool.name}"
            )

        # Clear the context for re-running.
        args = context.args
        context.clear()

        # Retry the tool call
        return self.__call__(context, args)

    def examples_text(
        self, example_format: Optional[Callable[[Example], str]] = None
    ) -> List[str]:
        if not example_format:
            example_format = Example.ExampleBlock

        return [example_format(self.name, example) for example in self.examples]

    def __str__(self) -> str:
        return Tool.stringify(self)

    def __repr__(self) -> str:
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

    def to_json(self) -> dict:
        return {
            "id": self.__id,
            "name": self.name,
            "description": self.description,
            "args": [arg.to_json() for arg in self.args],
            "examples": [example.to_json() for example in self.examples],
            "result": self.result.to_json() if self.result else None,
        }
