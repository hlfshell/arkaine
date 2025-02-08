from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional
from arkaine.tools.attachable import Attachable
from arkaine.internal.to_json import recursive_to_json
from uuid import uuid4

if TYPE_CHECKING:
    from arkaine.llms.llm import LLM
    from arkaine.tools.context import Context
    from arkaine.tools.tool import Tool


class Update:
    def __init__(
        self, target: str, type: str, data: Any, id: Optional[str] = None
    ):
        self.__id = id if id else str(uuid4())
        self.__target = target
        self.__type = type
        self.__data = data
        self.__time = datetime.now()

    @property
    def id(self):
        return self.__id

    @property
    def target(self):
        return self.__target

    @property
    def type(self):
        return self.__type

    @property
    def data(self):
        return self.__data

    @property
    def time(self):
        return self.__time

    def to_json(self):
        return recursive_to_json(
            {
                "id": self.__id,
                "target": self.__target,
                "type": self.__type,
                "data": self.__data,
                "time": self.__time,
            }
        )


class Registrar:
    _lock = Lock()
    _enabled = False
    __executor = ThreadPoolExecutor()

    _producers: Dict[str, Dict[str, Attachable]] = {}

    _on_producer_listeners: List[Callable[[Attachable], None]] = []
    _on_producer_call_listeners: List[
        Callable[[Attachable, "Context"], None]
    ] = []

    __update_listeners: Dict[str, List[Callable[[Update], None]]] = {}
    __update_listeners["all"] = []

    def __new__(cls):
        raise ValueError("Registrar cannot be instantiated")

    @classmethod
    def register(cls, item: Attachable):
        if not isinstance(item, Attachable):
            raise ValueError(f"Invalid class to register: {type(item)}")

        with cls._lock:
            if item.type not in cls._producers:
                cls._producers[item.type] = {}
            cls._producers[item.type][item.id] = item

            for listener in cls._on_producer_listeners:
                cls.__executor.submit(listener, item)

            if hasattr(item, "on_call_listener"):
                item.add_on_call_listener(cls._on_producer_call)

    @classmethod
    def broadcast_update(cls, update: Update):
        """Broadcast an update to all registered listeners of that type"""
        with cls._lock:
            for listener in cls.__update_listeners["all"]:
                cls.__executor.submit(listener, update)
            if update.type in cls.__update_listeners:
                for listener in cls.__update_listeners[update.type]:
                    cls.__executor.submit(listener, update)

    @classmethod
    def add_on_update_listener(
        cls, type: str, listener: Callable[[Update], None]
    ):
        with cls._lock:
            if type not in cls.__update_listeners:
                cls.__update_listeners[type] = []
            cls.__update_listeners[type].append(listener)

    @classmethod
    def _on_producer_call(cls, producer: Attachable, ctx: "Context"):
        """
        Whenever a producer we are aware of is called, notify the listener
        """
        with cls._lock:
            if cls._enabled:
                for listener in cls.__on_producer_call_listeners:
                    cls.__executor.submit(listener, producer, ctx)

    @classmethod
    def add_on_producer_register(cls, listener: Callable[[Attachable], None]):
        with cls._lock:
            cls._on_producer_listeners.append(listener)

    @classmethod
    def add_on_producer_call(
        cls, listener: Callable[[Attachable, "Context"], None]
    ):
        with cls._lock:
            cls._on_producer_call_listeners.append(listener)

    @classmethod
    def get_producers(cls):
        with cls._lock:
            return cls._producers

    @classmethod
    def get_tools(cls):
        with cls._lock:
            if "tool" not in cls._producers:
                return []
            return list(cls._producers["tool"].values())

    @classmethod
    def get_producer_by_type(cls, identifier: str, type: str) -> Attachable:
        error = ValueError(f"{type} with identifier {identifier} not found")

        with cls._lock:
            if type not in cls._producers:
                raise error
            for producer in cls._producers[type].values():
                if producer.id == identifier:
                    return producer
                if producer.name == identifier:
                    return producer
            raise error

    @classmethod
    def get_tool(cls, identifier: str) -> "Tool":
        return cls.get_producer_by_type(identifier, "tool")

    @classmethod
    def get_llms(cls):
        with cls._lock:
            if "llm" not in cls._producers:
                return []
            return list(cls._producers["llm"].values())

    @classmethod
    def get_llm(cls, name: str) -> "LLM":
        return cls.get_producer_by_type(name, "llm")

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
