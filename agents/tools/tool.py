from __future__ import annotations

import json
import threading
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event as ThreadEvent
from time import time
from types import TracebackType
from typing import Any, Callable, Dict, List, Optional, Union
from uuid import uuid4

from agents.options.context import ContextOptions
from agents.registrar.registrar import Registrar
from agents.tools.datastore import ThreadSafeDataStore
from agents.tools.events import (
    ChildContextCreated,
    ContextUpdate,
    Event,
    ToolCalled,
    ToolException,
    ToolReturn,
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

    def type_str(self) -> str:
        """
        Since some might pass in the literal type instead of the str of the
        class, we should ensure we convert the type correctly to a string for
        parsing.

        It is not simply str(self.type) as that tends to add "<class 'type'>"
        to the string.
        """
        if isinstance(self.type, str):
            return self.type
        else:
            try:
                return str(self.type).split("'")[1]
            except Exception:
                return str(self.type)

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "type": self.type_str(),
            "required": self.required,
            "default": self.default,
        }


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

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "args": self.args,
            "output": self.output,
        }


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
        self, tool: Optional[Tool] = None, parent: Optional[Context] = None
    ):
        self.__id = str(uuid4())
        self.__executing = False
        self.__tool = tool
        self.__parent = parent
        self.__tool = tool
        self.created_on = time()

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

        self.__data: ThreadSafeDataStore = ThreadSafeDataStore()
        self.__x: ThreadSafeDataStore = ThreadSafeDataStore()
        self.__debug: ThreadSafeDataStore = ThreadSafeDataStore()

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

        if self.exception and ContextOptions.save_on_exception():
            pass
        elif ContextOptions.save_on_success():
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

    def child_context(self, tool: Tool) -> Context:
        """Create a new child context for the given tool."""
        ctx = Context(tool=tool, parent=self)

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
    def exception(self, e: Exception):
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
    def args(self, args: Dict[str, Any]):
        with self.__lock:
            if self.__args:
                raise ValueError("args already set")
            self.__args = args

    @property
    def output(self) -> Any:
        with self.__lock:
            return self.__output

    @output.setter
    def output(self, value: Any):
        with self.__lock:
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

            data = self.__data.to_json()

            if self.__parent is None:
                x = self.__x.to_json()
            else:
                x = None

            if debug:
                debug = self.__debug.to_json()
            else:
                debug = None

        if hasattr(self.args, "to_json"):
            args = self.args.to_json()
        else:
            args = self.args

        if children:
            children = [child.to_json() for child in self.__children]
        else:
            children = []

        return {
            "id": self.__id,
            "parent_id": self.__parent.id if self.__parent else None,
            "root_id": self.root.id,
            "tool_id": self.__tool.id,
            "tool_name": self.__tool.name,
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
        filepath: Optional[str] = None,
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
            filepath: The path to save the context to. If None, the context
                will be saved to the default folder per ContextOptions
            children: Whether to expand children contexts
            debug: Whether to save debug information if present
        """
        if filepath is None:
            dir = ContextOptions.save_folder()
            if self.status == "success":
                dir = dir / ContextOptions.success_folder()
            elif self.status == "exception":
                dir = dir / ContextOptions.exception_folder()
            else:
                dir = dir / ContextOptions.running_folder()
            dir = dir / self.id
            filepath = dir / f"{self.id}.json"

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

    def __events_clear_after(self, timestamp: float):
        for event in self.__history:
            if event.timestamp > timestamp:
                # Technically we should be able to remove everything
                # after the first index that triggered the timestamp,
                # but because of threading it's not gauranteeed to
                # be in time order
                self.__history.remove(event)

    def __events_clear_by_type(self, event_type: str):
        for event in self.__history:
            if event.type == event_type:
                self.__history.remove(event)

    def _clear(self):
        """
        _clear is a protected metod for internal use only. Do not depend
        upon it.

        It is used to clear the context's output and reset its parents to accept
        new output.
        """
        # First, we need to go through each context (including this one)
        # through our parents up to and including the root context, removing
        # the output/exception at each point. We need to also remove all output
        # and exception events from the history of these contexts.
        ctx = self
        while ctx is not None:
            ctx.output = None
            ctx.exception = None
            ctx.__events_clear_by_type("tool_exception")
            ctx.__events_clear_by_type("tool_return")
            ctx = ctx.__parent

        # Then we clear out all of our children, to be executed again.
        self.__children = []

        # Finally, we clear out all of our events, to be executed again.
        self.__history = []

    def _can_clear(self) -> bool:
        """
        _can_clear checks to see if the context's parent tool can support
        resume, and thus can be properly cleared and restarted.
        """
        # Check the entire chain from this context to the root context,
        # ensuring that each tool supports a resume (outside this one,
        # which is merely getting reran)
        if self.parent is None:
            return False
        ctx = self.parent
        while ctx is not None:
            if not ctx.tool.can_resume:
                return False
            ctx = ctx.__parent
        return True

    def prepare_for_retry(self) -> bool:
        """
        prepare_for_resume will clear the output and exceptions of unfinished
        contexts, To do this, we will clear all exceptions across all contexts.

        These contexts that are the source of the exception will be removed, and
        the parent prepared to retry.
        """
        if not self.is_root:
            raise ValueError("Can only be called on the root context")


        for child in children:


    def isolate_root_exceptions(
        self, clone: bool = False, include_children: bool = True
    ) -> List[Context]:
        """
        isolate_root_exceptions will return a list of all contexts that were
        the source of an exception thrown.

        To determine the source of the exception, we check to see if the node
        itself has an exception, and, if so, if any of its children threw the
        same exception. If so, the current node is not the source of that
        exception, but a descendant is.

        If you are cloning, you may also specify to axe the children in the
        return context by setting include_children to False, or include all
        children nodes as well. Setting include_children to False when clone is
        set to False does nothing.

        This only explores down the context tree, so it is suggested to utilize
        this on a root context unless you are specifically isolating a larger
        context tree.

        Args:
            clone: Whether to clone the context

            include_children: Whether to include children in the return context

        Returns:
            List[Context]: Any contexts that created the initial exception
        """
        exception_contexts: List[Context] = []

        if self.exception:
            source = True
            for child in self.children:
                if child.exception and child.exception == self.exception:
                    source = False
                    break

            if source:
                exception_contexts.append(
                    self if not clone
                    else self.clone(include_children=include_children)
                )

        for child in self.children:
            exception_contexts.extend(
                child.isolate_root_exceptions(
                    clone=clone, include_children=include_children
                )
            )

        return exception_contexts

    def isolate_by_tool(
        self,
        tool: Union[Tool, str],
        include_children: bool = False,
        clone=False,
    ) -> List[Context]:
        """
        isolate_by_tool creates clones of each context within and below of this
        context that utilizes the given tool. You may pass a tool by reference,
        string id, or string name.

        If include_children is True, then all children of the context will also
        be cloned and isolated by the tool. If not, then only the context for
        the given tool is returned. Because contexts can have children that are
        subcalls of the same tool, you may get multiple clones of the same
        contexts if children are included.

        Args:
            tool: The tool to isolate

            include_children: Whether to include children of the context

        Returns:
            Context: The isolated contexts in a list. Order of execution is not
            guaranteed.
        """
        isolated: List[Context] = []

        ctx = self
        while ctx is not None:
            if isinstance(tool, Tool):
                if ctx.tool == tool:
                    isolated.append(
                        ctx.clone(include_children=include_children)
                    )
            elif ctx.tool.id == tool or ctx.tool.name == tool:
                isolated.append(ctx.clone(include_children=include_children))
            for child in self.children:
                isolated.extend(
                    child.isolate_by_tool(
                        tool, include_children=include_children
                    )
                )

        return isolated

    def clear_old(self, target: Optional[Union[str, Context]] = None):
        if isinstance(target, Context):
            target = target.id

        # First, if we have exceptions, we clear them.
        if self.__exception:
            self.__exception = None

        # Then, if the target is a descendant of this context,
        # we clear all events after the descendant's creation,
        # and our output if one is set.
        if self._is_descendant(target):
            self.output = None
            self.__events_clear_after(target.created_on)

        # If the target is specified and it is this context, we
        # need to clear all events, and output, as well as all children
        if target is self:
            self.__history = []
            self.__output = None
            self.__children = []
            return

        # If the target is specified and it is one of our children, we need to
        # clear all events after the child's creation, as well as that child,
        # and this event's outputs
        if self.__children:
            for child in self.__children:
                if child.id == target.id:
                    self.__children.remove(child)
                    self.__output = None

                    return

        # If the target is not specified OR it is not this context or a
        # direct child of the context,

    def __get_child(self, target: Union[str, Context]) -> Optional[Context]:
        if isinstance(target, Context):
            target = target.id

        for child in self.__children:
            if child.id == target:
                return child
        return None

    def _is_descendant(self, target: Union[Context, str]) -> Optional[Context]:
        """
        Determine if this context is a child of the target context
        or a sub child to any degree
        """
        id = target.id if isinstance(target, Context) else target
        if self.__parent is None:
            return False
        if self.__root.id == id:
            return self.__root
        if self.__parent.id == id:
            return True

        return self.__parent._is_descendant(target)

    def _is_ancestor(self, target: Union[Context, str]) -> bool:
        """
        Determine if this context is an ancestor (parent in some degree) of the
        target context
        """
        id = target.id if isinstance(target, Context) else target
        for child in self.__children:
            if child.id == id:
                return True
            else:
                if child._is_ancestor(target):
                    return True
        return False

    def clone(self, include_children: bool = True) -> Context:
        """
        Clone this context. Note that id's MUST be unique, so ids will
        change and references will not be preserved to the original copy,
        but instead expected clones of children will be created.

        If include_children is set to false, we ignore all children of
        the target node. Note that we expect this to be called by the
        root node.

        Args:
            include_children: Whether to include children of the context

        Returns:
            Context: A new Context instance with copied data but new IDs
        """
        # We need to add some protected methods to handle internal state copying
        new_ctx = Context(tool=self.tool)

        # Use existing public properties where possible
        if self.args:
            new_ctx.args = self.args.copy()
        if self.output is not None:
            new_ctx.output = self.output
        if self.exception is not None:
            new_ctx.exception = self.exception

        # Add protected methods for internal state copying
        new_ctx._copy_data_from(self)

        # Clone children
        if include_children:
            for child in self.children:
                child_clone = child.clone()
                new_ctx._add_child(child_clone)

        return new_ctx

    def _copy_data_from(self, other: Context) -> None:
        """Protected method to copy internal state from another context."""
        with self.__lock:
            self.__data = other.__data.clone()
            self.__x = (
                other.__x.clone() if other.is_root else ThreadSafeDataStore()
            )
            self.__debug = other.__debug.clone()
            self.__history = other.__history.copy()

    def _add_child(self, child: Context) -> None:
        """Protected method to properly add a child context."""
        with self.__lock:
            self.__children.append(child)
            child.__parent = self


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        args: List[Argument],
        func: Callable,
        examples: List[Example] = [],
        id: Optional[str] = None,
    ):
        self.__id = id or str(uuid4())
        self.name = name
        self.description = description
        self.args = args
        self.func = func
        self.examples = examples
        self._on_call_listeners: List[Callable[[Tool, Context], None]] = []

        self._executor = ThreadPoolExecutor()

        Registrar.register(self)

    def __del__(self):
        if self._executor:
            self._executor.shutdown(wait=False)

    @property
    def id(self) -> str:
        return self.__id

    @property
    def can_resume(self) -> bool:
        """
        A tool can only execute rerun
        """
        return (
            type(self) == Tool
            or self.rerun.__qualname__.split(".")[0] != "Tool"
        )

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
            if not ctx.tool:
                ctx.tool = self
            ctx.executing = True

        ctx.args = kwargs
        ctx.broadcast(ToolCalled(kwargs))
        for listener in self._on_call_listeners:
            self._executor.submit(listener, self, ctx)

        return ctx

    def invoke(self, context: Context, **kwargs) -> Any:
        if "context" in self.func.__code__.co_varnames:
            return self.func(context=context, **kwargs)
        return self.func(**kwargs)

    def __call__(self, context: Optional[Context] = None, **kwargs) -> Any:
        with self._init_context_(context, kwargs) as ctx:
            kwargs = self.fulfill_defaults(kwargs)

            self.check_arguments(kwargs)

            ctx.broadcast(ToolCalled(self.name))

            results = self.invoke(ctx, **kwargs)

            ctx.output = results

            ctx.broadcast(ToolReturn(results))

            return results

    def async_call(
        self, context: Optional[Context] = None, **kwargs
    ) -> Context:
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

    def rerun(self, context: Context):
        """
        rerun a context that was previously paused.
        """
        # If the calling tool is not a Tool (ie a child class)
        # then we should raise an error, as resume must be created by
        # the tool that created the context.
        if not isinstance(context.tool, Tool):
            raise ValueError("Resume is not implemented on this tool")

        context.executing = False
        return self.__call__(context, context.kwargs)

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

    def to_json(self) -> dict:
        return {
            "id": self.__id,
            "name": self.name,
            "description": self.description,
            "args": [arg.to_json() for arg in self.args],
            "examples": [example.to_json() for example in self.examples],
        }


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
