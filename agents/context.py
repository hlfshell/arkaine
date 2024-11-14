from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4


class Event:
    """
    Event are events that can occur throughout execution of the agent,
    and are thus bubbled up through the chain of the context.
    """

    def __init__(self, event_type: str, data: Any):
        self.event_type = event_type

    def __str__(self) -> str:
        return self.event_type


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
    """

    def __init__(self, parent_id: Optional[str] = None):
        self.__id = str(uuid4())
        self.__parent_id = parent_id
        self.__exception: Exception = None
        self.__output: Any = None

        self.__children: List[Context] = []

        self.__event_listeners: Dict[str, List[Callable[[Event], None]]] = {
            "all": []
        }

        self.__history: List[Event] = []

        self.__event_lock = threading.Lock()
        self.__status_changed = threading.Event()

        # No max workers due to possible lock synchronization issues
        self.__executor = ThreadPoolExecutor()

    def child_context(self) -> Context:
        ctx = Context()
        with self.__event_lock:
            self.__children.append(ctx)

        # All events happening in the children contexts are broadcasted
        # to their parents as well so the root context receives
        # all events
        ctx.add_listener(lambda e: self.broadcast(e))
        return ctx

    @property
    def is_root(self) -> bool:
        return self.__parent_id is None

    @property
    def status(self) -> str:
        with self.__event_lock:
            if self.__exception:
                return "error"
            elif self.__output is not None:
                return "success"
            else:
                return "running"

    def add_listener(
        self,
        listener: Callable[[Event], None],
        event_type: Optional[str] = None,
    ):
        with self.__event_lock:
            if event_type is None:
                self.__event_listeners["all"].append(listener)
            else:
                if event_type not in self.__event_listeners:
                    self.__event_listeners[event_type] = []
                self.__event_listeners[event_type].append(listener)

    def broadcast(self, event: Event):
        with self.__event_lock:
            self.__history.append(event)

            for listener in self.__event_listeners["all"]:
                self.__executor.submit(listener, event)
            if event.event_type in self.__event_listeners:
                for listener in self.__event_listeners[event.event_type]:
                    self.__executor.submit(listener, event)

    def exception(self, e: Exception):
        self.broadcast(Event("error", e))

        with self.__event_lock:
            self.__exception = e
        self.__status_changed.set()

    @property
    def output(self) -> Any:
        with self.__event_lock:
            return self.__output

    @output.setter
    def output(self, value: Any):
        with self.__event_lock:
            if self.__output:
                raise ValueError("Output already set")
            self.__output = value
        self.__status_changed.set()

    def wait(self, timeout: Optional[float] = None):
        while True:
            self.__status_changed.wait(timeout=timeout or 0.1)
            if timeout or self.status != "running":
                break

        self.__status_changed.clear()
