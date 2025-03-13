from __future__ import annotations

import json
import threading
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event as ThreadEvent
from time import time
from types import TracebackType
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
    Union,
)
from uuid import uuid4

from arkaine.internal.json import (
    recursive_from_json,
    recursive_to_json,
)
from arkaine.internal.options.context import ContextOptions
from arkaine.internal.registrar import Registrar
from arkaine.tools.attachable import Attachable
from arkaine.tools.datastore import ThreadSafeDataStore
from arkaine.tools.events import (
    ChildContextCreated,
    ContextUpdate,
    Event,
    ToolCalled,
    ToolException,
    ToolReturn,
)


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
    4. exception - what the final exception of the tool was, if any
    5. name - a human readable name for the associated tool
    6. args - the arguments passed to the tool/agent for this execution
    7. type - the type of the context, specifically referring to the type
      of the object that is attached to the context
    8. attached - the object that is attached to the context

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
        attach: Optional[Attachable] = None,
        parent: Optional[Context] = None,
        id: Optional[str] = None,
    ):
        self.__id = id or str(uuid4())
        self.__executing = False
        self.__parent = parent

        if attach is not None and not isinstance(attach, Attachable):
            raise ValueError(
                "Object must implement id, name, and type properties, got "
                f"{type(attach)}"
            )
        self.__attachable = attach

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

    # OBJECT BEHAVIOR

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

    # PROPERTIES

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
    def attached(self) -> Attachable:
        return self.__attachable

    @attached.setter
    def attached(self, attach: Attachable):
        if not isinstance(attach, Attachable):
            raise ValueError(
                "Attachable must be an instance of Attachable, got "
                f"{type(attach)}"
            )
        with self.__lock:
            if self.__attachable:
                raise ValueError("Attachable already set")
            self.__attachable = attach

    @property
    def parent(self) -> Context:
        return self.__parent

    @property
    def parents(self) -> List[Context]:
        """
        parents is a list of all the parents in order of hierarchy, starting
        with the immediate parent and going up to the root context. If this is
        the root context, the list will be empty.
        """
        parents = []
        current = self
        while self.parent is not None:
            parents.append(current.parent)
            current = current.parent
        return parents

    def get_parents_of_type(
        self, type: Union[Type[Attachable], str]
    ) -> List[Context]:
        """
        get_parents_of_type returns a list of all the parents of a given type.
        If no parents are of the given type (or there are no parents), an empty
        list is returned. The order of the list is from the immediate parent to
        the root context, if applicable.
        """
        return [
            parent
            for parent in self.parents
            if isinstance(parent.attachable, type)
        ]

    @property
    def children(self) -> List[Context]:
        with self.__lock:
            return self.__children

    def is_descendant_of(self, context: Context) -> bool:
        """
        is_descendant_of returns True if the given context is a descendant of
        this context.
        """
        return context in self.parents

    def get_children_of_type(
        self, type: Union[Type[Attachable], str], depth: Optional[int] = None
    ) -> List[Context]:
        """
        get_children_of_type returns a list of all the children of a given type,
        up to a specific depth (if depth is None, it will traverse the entire
        tree). This is a flat list, with no meaning behind its ordering. Utilize
        map_to_child to get the specific path or depth to a specific child.
        """
        if depth == 0:
            return []

        matches = []
        for child in self.children:
            if isinstance(child.attachable, type):
                matches.append(child)
            else:
                matches.extend(
                    child.get_children_of_type(
                        type, depth - 1 if depth else None
                    )
                )
        return matches

    def map_to_child(self, child: Context) -> List[Context]:
        """
        map_to_child context returns a list of the path to a given child node
        *if* it exists as a child to this one (if it isn't, the list will be
        empty). This path starts at the first child node that leads to the given
        child, followed by the next child node, and so on to the node that
        contains the given child.
        """
        if not child.is_descendant_of(self):
            return []
        path = []
        current = child
        for child in self.children:
            if child == current:
                path.append(child)
                current = child
                break
            else:
                next_path = child.map_to_child(current)
                if next_path:
                    path.extend(next_path)
                    break

        return path

    @property
    def events(self) -> List[Event]:
        with self.__lock:
            return self.__history

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

    # DATASTORE FUNCTIONALITY

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

    def __getitem__(self, name: str) -> Any:
        return self.__data[name]

    def __setitem__(self, name: str, value: Any):
        self.__data[name] = value

    def __contains__(self, name: str) -> bool:
        return name in self.__data

    def __delitem__(self, name: str):
        del self.__data[name]

    def get(self, key: str, default: Any = None) -> Any:
        return self.__data.get(key, default)

    def operate(
        self, keys: Union[str, List[str]], operation: Callable[[Any], Any]
    ) -> None:
        self.__data.operate(keys, operation)

    def update(self, key: str, operation: Callable) -> Any:
        return self.__data.update(key, operation)

    def init(self, key: str, value: Any):
        return self.__data.init(key, value)

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

    # INTERNAL MANAGEMENT

    def child_context(self, attachable: Attachable) -> Context:
        """Create a new child context for the given tool."""

        if not isinstance(attachable, Attachable):
            raise ValueError(
                "Attachable must be an instance of Attachable, got "
                f"{type(attachable)}"
            )

        ctx = Context(attach=attachable, parent=self)

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

    # EVENT MANAGEMENT

    def add_event_listener(
        self,
        listener: Callable[[Context, Event], None],
        event_type: Optional[Union[str, Type[Event]]] = None,
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

        if isinstance(event_type, Event):
            event_type = event_type.type()

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

    # SERIALIZATION

    def to_json(self, children: bool = True, debug: bool = True) -> dict:
        """Convert Context to a JSON-serializable dictionary."""
        # We have to grab certain things prior to the lock to avoid
        # competing locks. This introduces a possible race condition
        # but should be fine for most purposes for now.
        status = self.status

        if self.exception:
            exception = f"{self.exception}:\n\n"

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
            history = recursive_to_json(self.__history)

            args = recursive_to_json(self.__args)

            output = None
            if self.__output:
                output = recursive_to_json(self.__output)

            data = self.__data.to_json()

            if root.id == self.id:
                x = root.x.to_json()
            else:
                x = None

            if debug:
                debug = self.__debug.to_json()
            else:
                debug = None

        if children:
            children = [child.to_json() for child in self.__children]
        else:
            children = []

        return {
            "id": self.__id,
            "parent_id": self.__parent.id if self.__parent else None,
            "root_id": self.root.id,
            "attached_id": self.__attachable.id,
            "attached_name": self.__attachable.name,
            "attached_type": self.__attachable.type,
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
        attached = cls._find_attached(
            data.get("attached_id"),
            data.get("attached_name"),
            data.get("attached_type"),
        )

        # Create the base context
        context = cls(attach=attached)

        # Load the basic properties
        context.__id = data["id"]
        context.__created_at = data["created_at"]

        # Load args
        if data.get("args"):
            context.args = recursive_from_json(
                data["args"], fallback_if_no_class=True
            )

        # Load output if present
        if data.get("output") is not None:
            context.__output = recursive_from_json(
                data["output"], fallback_if_no_class=True
            )

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
            context.__history = recursive_from_json(data["history"])

        # Load children recursively
        if data.get("children"):
            for child_data in data["children"]:
                child = cls.__load_from_json(child_data)
                child.__parent = context
                context.__children.append(child)

        return context

    @staticmethod
    def _find_attached(
        attached_id: Optional[str],
        attached_name: Optional[str],
        attached_type: Optional[str],
    ) -> Optional[Attachable]:
        """Find a tool by ID or name from the Registrar."""
        if not attached_id and not attached_name:
            raise ValueError("No attached ID or name provided")

        attached = Registrar.get_producer_by_type(
            attached_id or attached_name, attached_type
        )

        return attached

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
