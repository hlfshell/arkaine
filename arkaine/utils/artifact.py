from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import json
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
import tempfile
from threading import Lock
from typing import Dict, List, Optional, Tuple, Type, Union

import google.generativeai as genai
from PIL import Image as PILImage
from uuid import uuid4


class Library(ABC):
    """
    Library is a collection of artifacts in a singular place. The goal is for
    Library to know about all artifacts in its purview, as well as offering
    some search capabilities for it.
    """

    def __init__(self, name: str, path: str):
        super().__init__()
        self.__name = name
        self.__path = path

    @property
    def path(self) -> str:
        return self.__path

    @property
    def name(self) -> str:
        return self.__name

    def to_json(self) -> Dict[str, str]:
        return {
            "path": self.__path,
            "name": self.__name,
        }

    @classmethod
    def from_json(cls, json: Dict[str, str]) -> Library:
        return cls(json["name"], json["path"])

    @abstractmethod
    def get_artifact(self, id: str) -> Artifact:
        pass

    @abstractmethod
    def save_artifact(self, artifact: Artifact):
        pass

    @abstractmethod
    def search_artifacts(self, query: Any) -> List[Artifact]:
        pass


class InMemoryLibrary(Library):
    def __init__(self, name: str, path: str, embedding_store: EmbeddingStore):
        super().__init__(name, path)
        self.__embedding_store = embedding_store

        self.__lock = Lock()

        self.__artifacts = {}
        self.load()

    def get_artifact(self, id: str) -> Artifact:
        with self.__lock:
            return self.__artifacts[id]

    def search_artifacts(self, query: str) -> List[Artifact]:
        embedding = self.__embedding_store.model.embed(query)
        return self.__embedding_store.search(embedding)

    def save_artifact(self, artifact: Artifact):
        with self.__lock:
            self.__artifacts[artifact.id] = artifact

            artifact.save()

    def load(self):
        with self.__lock:
            for artifact in os.listdir(self.__path):
                self.__artifacts[artifact] = Artifact(
                    self.__path, artifact, self.__embedding_store
                )


class LibraryRegistry:
    __instance = None
    __creation_lock = Lock()

    def __init__(self):
        self.__registry = {}

    @classmethod
    def get_registry(cls, *args, **kwargs):
        with cls.__creation_lock:
            if cls.__instance is None:
                cls.__instance = super(LibraryRegistry, cls).__new__(
                    cls, *args, **kwargs
                )
        return cls.__instance

    def register(self, library: Library):
        with self.__lock:
            if library.__name__ not in self.__registry:
                self.__registry[library.__name__] = library


class ArtifactTypeRegistry:
    """
    ArtifactRegistry is a singleton class that allows classes to be registered
    as a potential artifact to be utilized. The goal is to allow working with
    various types of artifacts to pass to models or save for the user easy and
    in a way that is easy for end users.
    """

    __instance = None
    __creation_lock = Lock()

    def __init__(self):
        self.__registry = {}
        self.__lock = Lock()

    @classmethod
    def get_registry(cls, *args, **kwargs):
        with cls.__creation_lock:
            if cls.__instance is None:
                cls.__instance = super(ArtifactTypeRegistry, cls).__new__(
                    cls, *args, **kwargs
                )
        return cls.__instance

    def register(self, artifact: Type[Metadata]):
        with self.__lock:
            if artifact.__name__ not in self.__registry:
                self.__registry[artifact.__name__] = artifact
            else:
                raise ValueError(
                    f"Artifact {artifact.__class__.__name__} already registered"
                )

    @classmethod
    def from_metadata(cls, metadata: Dict[str, str]) -> Metadata:
        """
        Given a standard metadata object (JSON dict assumed), build the object
        with the associated class in the registry. Note that this is just the
        metadata object, not the artifact itself.
        """
        registry = cls.get_registry()
        with cls.__creation_lock:
            if metadata["type"] not in registry.__registry:
                raise ValueError(f"Artifact {metadata['type']} not registered")
            return registry.__registry[metadata["type"]].from_metadata(metadata)


class Artifact:

    def __init__(
        self,
        library_dir: str,
        id: Optional[str] = None,
        metadata: Optional[Union[Metadata, Dict[str, str]]] = None,
    ):
        self.__id = id
        self.__location = os.path.join(library_dir, self.__id)

        # Extract the filename from the location provided
        # IF it exists - it will be document.EXT
        # List all files and see if we have a document.EXT
        files = os.listdir(self.__location)
        # Starts with document?
        if any(file.startswith("document") for file in files):
            for file in files:
                if file.startswith("document"):
                    try:
                        self.file_type = os.path.splitext(file)[1]
                        break
                    except Exception:
                        self.file_type = ""
                        break
        else:
            raise ValueError("Document not found")

        if metadata is not None and not isinstance(metadata, dict):
            self.__metadata = metadata
        elif metadata:
            # Load the metadata.json which contains all of the other
            # information
            if not os.path.exists(self.__location):
                raise ValueError("Artifact not found")

            metadata_path = os.path.join(self.__location, "metadata.json")
            if not os.path.exists(metadata_path):
                raise ValueError("Metadata not found")

            with open(metadata_path, "r") as f:
                metadata = json.load(f)

        # This can only be reached if we were passed a dict of metadata,
        # or we loaded it from the
        if not self.__metadata:
            metadata = ArtifactTypeRegistry.from_metadata(metadata, self)

        self.__metadata = metadata

    @property
    def id(self) -> str:
        return self.__id

    @property
    def name(self) -> str:
        return self.__metadata.name

    @property
    def metadata(self) -> Dict[str, str]:
        return self.__metadata

    @property
    def location(self) -> str:
        return self.__location

    def to_json(self) -> Dict[str, str]:
        return {
            "id": self.__id,
            "library": self.__library.id,
        }


class Metadata(ABC):

    @abstractmethod
    def id(self) -> str:
        pass

    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    @classmethod
    def from_metadata(
        cls, metadata: Dict[str, str], artifact: Optional[Artifact]
    ) -> Metadata:
        pass

    @abstractmethod
    def to_json(self) -> Dict[str, str]:
        pass
