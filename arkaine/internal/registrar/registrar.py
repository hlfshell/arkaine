from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import TYPE_CHECKING, Callable, Dict, List, Union

if TYPE_CHECKING:
    from arkaine.llms.llm import LLM
    from arkaine.tools.tool import Context, Tool


class Registrar:
    _lock = Lock()
    _enabled = False
    __executor = ThreadPoolExecutor()

    _tools: 'Dict[str, "Tool"]' = {}
    _llms: 'Dict[str, "LLM"]' = {}

    __on_tool_listeners: List[Callable[["Tool"], None]] = []
    __on_tool_call_listeners: List[Callable[["Tool", "Context"], None]] = []
    __on_llm_listeners: List[Callable[["LLM"], None]] = []
    __on_llm_call_listeners: List[Callable[["LLM", "Context"], None]] = []

    def __new__(cls):
        raise ValueError("Registrar cannot be instantiated")

    @classmethod
    def register(cls, item: Union["Tool", "LLM"]):
        with cls._lock:
            if hasattr(item, "tname"):
                if item.id in cls._tools:
                    pass
                cls._tools[item.id] = item

                for listener in cls.__on_tool_listeners:
                    cls.__executor.submit(listener, item)

                item.add_on_call_listener(cls._on_tool_call)
            elif hasattr(item, "completion"):
                cls._llms[item.name] = item

                for listener in cls.__on_llm_listeners:
                    cls.__executor.submit(listener, item)

                item.add_on_call_listener(cls._on_llm_call)
            else:
                raise ValueError(f"Invalid class to register: {type(item)}")

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
    def _on_llm_call(cls, llm: "LLM", ctx: "Context"):
        """
        Whenever a LLM we are aware of is called, notify the listener
        """
        with cls._lock:
            if cls._enabled:
                for listener in cls.__on_llm_call_listeners:
                    cls.__executor.submit(listener, llm, ctx)

    @classmethod
    def add_on_tool_register(cls, listener: Callable[["Tool"], None]):
        with cls._lock:
            cls.__on_tool_listeners.append(listener)

    @classmethod
    def add_on_llm_register(cls, listener: Callable[["LLM"], None]):
        with cls._lock:
            cls.__on_llm_listeners.append(listener)

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
    def get_llms(cls):
        with cls._lock:
            return list(cls._llms.values())

    @classmethod
    def get_llm(cls, name: str) -> "LLM":
        with cls._lock:
            if name in cls._llms:
                return cls._llms[name]
            raise ValueError(f"LLM with identifier {name} not found")

    @classmethod
    def add_tool_call_listener(
        cls, listener: Callable[["Tool", "Context"], None]
    ):
        with cls._lock:
            cls.__on_tool_call_listeners.append(listener)

    @classmethod
    def add_llm_call_listener(
        cls, listener: Callable[["LLM", "Context"], None]
    ):
        with cls._lock:
            cls.__on_llm_call_listeners.append(listener)

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
