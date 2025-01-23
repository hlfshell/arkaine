from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import TYPE_CHECKING, Callable, Dict, List

if TYPE_CHECKING:
    from arkaine.tools.tool import Context, Tool


class Registrar:
    _lock = Lock()
    _enabled = False
    __executor = ThreadPoolExecutor()

    _tools: 'Dict[str, "Tool"]' = {}

    __on_tool_listeners: List[Callable[["Tool"], None]] = []
    __on_tool_call_listeners: List[Callable[["Tool", "Context"], None]] = []

    def __new__(cls):
        raise ValueError("Registrar cannot be instantiated")

    @classmethod
    def register(cls, tool: "Tool"):
        with cls._lock:
            if tool.id in cls._tools:
                pass
            cls._tools[tool.id] = tool

            for listener in cls.__on_tool_listeners:
                cls.__executor.submit(listener, tool)

            tool.add_on_call_listener(cls._on_tool_call)

    @classmethod
    def _on_tool_call(cls, tool: "Tool", ctx: "Context"):
        """
        Whenever a tool we are aware of is called, notify the listener
        """
        with cls._lock:
            if cls._enabled:
                for listener in cls.__on_tool_call_listeners:
                    cls.__executor.submit(listener, tool, ctx)

    @classmethod
    def add_on_tool_register(cls, listener: Callable[["Tool"], None]):
        with cls._lock:
            cls.__on_tool_listeners.append(listener)

    @classmethod
    def get_tools(cls):
        with cls._lock:
            return list(cls._tools.values())

    @classmethod
    def get_tool(cls, identifier: str) -> "Tool":
        with cls._lock:
            for tool in cls._tools.values():
                if tool.id == identifier:
                    return tool
                if tool.name == identifier:
                    return tool
            raise ValueError(f"Tool with identifier {identifier} not found")

    @classmethod
    def add_tool_call_listener(
        cls, listener: Callable[["Tool", "Context"], None]
    ):
        with cls._lock:
            cls.__on_tool_call_listeners.append(listener)

    @classmethod
    def enable(cls):
        with cls._lock:
            cls._enabled = True

    @classmethod
    def disable(cls):
        with cls._lock:
            cls._enabled = False

    @classmethod
    def set_auto_registry(cls, enabled: bool):
        with cls._lock:
            cls._enabled = enabled

    @classmethod
    def is_enabled(cls):
        with cls._lock:
            return cls._enabled
