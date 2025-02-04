from __future__ import annotations

import os
from threading import Lock, Thread
from typing import Dict, List, Optional, Union

from arkaine.internal.registrar import Registrar
from arkaine.internal.store.context import Check, ContextStore, Query
from arkaine.tools.context import Context


class GlobalContextStore(ContextStore):
    __store: ContextStore = None
    __lock = Lock()
    __enabled = False
    __thread_lock = Lock()
    __thread: Thread = None

    def __init__(self):
        raise ValueError("GlobalContextStore cannot be instantiated")

    @classmethod
    def set_store(cls, store: ContextStore):
        with cls.__lock:
            cls.__store = store

    @classmethod
    def get_store(cls) -> ContextStore:
        with cls.__lock:
            return cls.__store

    @classmethod
    def enable_autosave(cls):
        Registrar.add_on_tool_call(cls._autosave)
        Registrar.add_on_llm_call(cls._autosave)

    @classmethod
    def _autosave(cls, _, ctx: Context):
        with cls.__lock:
            if not cls.__enabled:
                return
            cls.__store.save(ctx)

            # When the context is finished, save it.
            # TODO - this needs a lot of work to deal with
            # timing issues!
            ctx.add_on_end_listener(lambda ctx: cls.__store.save(ctx))

    @classmethod
    def disable_autosave(cls):
        with cls.__lock:
            if not cls.__enabled:
                return
            cls.__enabled = False


class InMemoryContextStore(ContextStore):
    """
    MemoryContextStore is a simple in-memory context store.
    """

    def __init__(self, contexts: Dict[str, Context] = {}):
        super().__init__()
        self._contexts: Dict[str, Context] = contexts

    def get_context(self, id: str) -> Optional[Context]:
        return self._contexts.get(id)

    def query_contexts(
        self, query: Union[Query, List[Query], Check, List[Check]]
    ) -> List[Context]:
        if isinstance(query, List):
            q = Query()
            for i in query:
                q += i
            query = q
        elif isinstance(query, Check):
            query = Query([query])

        return [
            context for context in self._contexts.values() if query(context)
        ]

    def save(self, context: Context) -> None:
        self._contexts[context.id] = context

    @staticmethod
    def load(self) -> "ContextStore":
        raise NotImplementedError("InMemoryContextStore is not persistent")

    def __enter__(self) -> InMemoryContextStore:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        pass


class FileContextStore(InMemoryContextStore):

    def __init__(self, folder_path: str, contexts: Dict[str, Context]):
        super().__init__()
        self._folder_path = folder_path
        self._contexts = contexts

    @staticmethod
    def load(cls, folder_path: str) -> "ContextStore":
        contexts = {}
        for root, _, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                context = Context.load(file_path)
                contexts[context.id] = context

        return cls(folder_path, contexts)

    def save(self, context: Context) -> None:
        super().save()
        context.save(os.path.join(self._folder_path, context.id))
