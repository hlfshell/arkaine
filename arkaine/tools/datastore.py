from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Union

from arkaine.internal.to_json import recursive_to_json


class ThreadSafeDataStore:
    """
    A thread-safe key-value store that provides synchronized access to a
    dictionary.

    This class implements a thread-safe wrapper around a dictionary, ensuring
    all operations are atomic through the use of a threading lock. It supports
    standard dictionary operations as well as additional utility methods for
    common operations like incrementing values or appending to lists. The most
    notable feature is the addition of the `operate` method, which allows for
    atomic operations on nested values. As such append, concat, and update
    methods are provided that can handle deep nesting. Also thread safe
    increment and decrement methods are provided.

    The store supports nested dictionary access through key paths and provides
    methods for atomic operations on stored values.

    Note:
        All methods acquire a lock before accessing the underlying data
        structure, ensuring thread safety but potentially impacting performance
        under high contention.
    """

    def __init__(
        self,
        data: Optional[Dict[str, Any]] = None,
        context: Optional[Union[str, "Context"]] = None,
        label: Optional[str] = None,
    ):
        """Initialize an empty thread-safe data store."""
        self.__lock = threading.Lock()
        self.__data: Dict[str, Any] = data or {}
        if isinstance(context, str):
            self.__context = context
        else:
            self.__context = context.id
        self.__label = label
        self.__threadpool = ThreadPoolExecutor()

        self.__listeners: List[
            Callable[[ThreadSafeDataStore, str, Any], None]
        ] = []

    @property
    def context(self) -> str:
        return self.__context

    @property
    def label(self) -> str:
        return self.__label

    def add_listener(
        self, listener: Callable[[ThreadSafeDataStore, str, Any], None]
    ):
        with self.__lock:
            self.__listeners.append(listener)

    def __broadcast_update(self, key: str, value: Any):
        for subscriber in self.__listeners:
            self.__threadpool.submit(subscriber, self, key, value)

    def __getitem__(self, name: str) -> Any:
        with self.__lock:
            return self.__data[name]

    def __setitem__(self, name: str, value: Any):
        with self.__lock:
            self.__data[name] = value
            self.__broadcast_update(name, value)

    def __contains__(self, name: str) -> bool:
        with self.__lock:
            return name in self.__data

    def __delitem__(self, name: str):
        with self.__lock:
            del self.__data[name]
            self.__broadcast_update(name, None)

    def __iter__(self):
        with self.__lock:
            return iter(self.__data)

    def __str__(self) -> str:
        with self.__lock:
            if not self.__data:
                return "{}"

            items = []
            for key, value in self.__data.items():
                items.append(f"\t{key}: {value}")

            return "{\n" + ",\n".join(items) + "\n}"

    def __repr__(self) -> str:
        return self.__str__()

    def __del__(self):
        self.__threadpool.shutdown(wait=False)

    def get(self, key: str, default: Any = None) -> Any:
        with self.__lock:
            return self.__data.get(key, default)

    def operate(
        self, keys: Union[str, List[str]], operation: Callable[[Any], Any]
    ) -> None:
        """
        Perform an atomic operation on a value in the store, supporting nested
        access.

        Args:
            keys: A single key or list of keys forming a path to the target
                value
            operation: A callable that takes the current value and returns the
                new value

        Raises:
            ValueError: If a non-terminal key in the path doesn't point to a
                dictionary
            KeyError: If the target key doesn't exist
        """
        if isinstance(keys, str):
            keys = [keys]

        with self.__lock:
            current = self.__data
            for i, key in enumerate(keys[:-1]):
                if key not in current or not isinstance(current[key], dict):
                    path = "".join(f"[{k}]" for k in keys[: i + 1])
                    raise ValueError(f"{path} is not a dictionary")
                current = current[key]

            final_key = keys[-1]
            if final_key not in current:
                path = "".join(f"[{k}]" for k in keys)
                raise KeyError(f"Key {path} does not exist")

        value = operation(current[final_key])
        current[final_key] = value
        self.__broadcast_update(final_key, value)

    def update(self, key: str, operation: Callable[[Any], Any]) -> Any:
        """
        Update a value atomically using the provided operation.

        Args:
            key: The key to update
            operation: A callable that takes the current value and returns the new value

        Returns:
            The new value after applying the operation

        Raises:
            KeyError: If the key doesn't exist
        """
        with self.__lock:
            value = operation(self.__data[key])
            self.__data[key] = value
            self.__broadcast_update(key, value)
            return value

    def items(self) -> List[tuple[str, Any]]:
        """Return a list of the store's (key, value) pairs."""
        with self.__lock:
            return list(self.__data.items())

    def __len__(self) -> int:
        with self.__lock:
            return len(self.__data)

    def values(self) -> List[Any]:
        """Return a list of the store's values."""
        with self.__lock:
            return list(self.__data.values())

    def keys(self) -> List[str]:
        """Return a list of the store's keys."""
        with self.__lock:
            return list(self.__data.keys())

    def init(self, key: str, value: Any):
        with self.__lock:
            if key not in self.__data:
                self.__data[key] = value
                self.__broadcast_update(key, value)

    def increment(self, key: str, amount=1):
        return self.update(key, lambda x: x + amount)

    def decrement(self, key: str, amount=1):
        return self.update(key, lambda x: x - amount)

    def append(self, keys: Union[str, List[str]], value: Any) -> None:
        def append(x):
            x.append(value)
            return x

        self.operate(keys, append)

    def concat(self, keys: Union[str, List[str]], value: Any) -> None:
        self.operate(keys, lambda x: x + value)

    def to_json(self) -> Dict[str, Any]:
        with self.__lock:
            data = {}
            for key, value in self.__data.items():
                data[key] = recursive_to_json(value)

        return {
            "context": self.context,
            "label": self.label,
            "data": data,
        }

    @classmethod
    def from_json(cls, data: dict) -> "ThreadSafeDataStore":
        """Create a ThreadSafeDataStore from JSON data."""
        store = cls(data["data"], data["context"], data["label"])
        return store
