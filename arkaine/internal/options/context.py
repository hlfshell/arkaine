"""Module for managing global context options in a thread-safe manner."""

from threading import Lock
from typing import Optional

from arkaine.internal.store.context import ContextStore


class ContextOptions:
    """
    Thread-safe singleton class for managing global context options.
    Provides centralized control over context behavior across the application.
    """

    __instance: Optional["ContextOptions"] = None
    __lock = Lock()

    # Debug enables/disables the debug store on contexts, and whether
    # or not their messages are broadcasted to any possible subscribers
    __debug = False

    __context_store: Optional[ContextStore] = None

    def __new__(cls):
        raise ValueError("ContextOptions cannot be instantiated")

    @classmethod
    def debug(cls, value: Optional[bool] = None) -> bool:
        with cls.__lock:
            if value is not None:
                cls.__debug = value
            return cls.__debug

    @classmethod
    def set_store(cls, store: ContextStore):
        with cls.__lock:
            cls.__context_store = store

    @classmethod
    def get_store(cls) -> ContextStore:
        with cls.__lock:
            if cls.__context_store is None:
                raise ValueError("Context store not set")
            return cls.__context_store
