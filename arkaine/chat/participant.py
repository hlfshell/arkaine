from __future__ import annotations

import json
from abc import ABC, abstractmethod
from threading import Lock
from typing import Dict, List, Optional, Union
import uuid


class Participant:
    def __init__(
        self,
        name: str,
        is_human: bool,
        role: Optional[str] = None,
        id: Optional[str] = None,
    ):
        self.__id = id if id else str(uuid.uuid4())
        self.__name = name
        self.__role = role
        self.__is_human = is_human

    @property
    def id(self) -> str:
        return self.__id

    @property
    def name(self) -> str:
        return self.__name

    @property
    def role(self) -> Optional[str]:
        return self.__role

    @property
    def is_human(self) -> bool:
        return self.__is_human

    def to_json(self):
        return {
            "id": self.__id,
            "name": self.name,
            "role": self.role,
            "is_human": self.is_human,
        }

    @classmethod
    def from_json(cls, data: Dict[str, str]) -> Participant:
        return cls(
            name=data["name"],
            role=data["role"],
            is_human=data["is_human"],
            id=data["id"],
        )


class ParticipantStore(ABC):
    def __init__(self):
        super().__init__()

    @abstractmethod
    def get_participant(self, id: str) -> Optional[Participant]:
        pass

    @abstractmethod
    def save_participant(self, participant: Participant):
        pass

    @abstractmethod
    def get_participants(
        self,
        id: Optional[Union[str, List[str]]] = None,
        name: Optional[Union[str, List[str]]] = None,
        role: Optional[str] = None,
        is_human: Optional[bool] = None,
    ) -> List[Participant]:
        pass


class InMemoryParticipantStore(ParticipantStore):
    def __init__(self):
        super().__init__()
        self._participants: Dict[str, Participant] = {}
        self.__roles: Dict[str, set[str]] = {}
        self.__lock = Lock()

    def get_participant(self, id: str) -> Optional[Participant]:
        with self.__lock:
            return self._participants.get(id)

    def save_participant(self, participant: Participant):
        self._add_participant(participant)

    def _add_participant(self, participant: Participant):
        with self.__lock:
            self._participants[participant.id] = participant
            if participant.role:
                if participant.role not in self.__roles:
                    self.__roles[participant.role] = set()
                self.__roles[participant.role].add(participant.id)

    def get_participants(
        self,
        id: Optional[Union[str, List[str]]] = None,
        name: Optional[Union[str, List[str]]] = None,
        role: Optional[str] = None,
        is_human: Optional[bool] = None,
    ) -> List[Participant]:
        with self.__lock:
            participants = list(self._participants.values())

            if id:
                id_list = [id] if isinstance(id, str) else id
                participants = [p for p in participants if p.id in id_list]

            if name:
                name_list = [name] if isinstance(name, str) else name
                participants = [p for p in participants if p.name in name_list]

            if role is not None:
                participants = [p for p in participants if p.role == role]

            if is_human is not None:
                participants = [
                    p for p in participants if p.is_human == is_human
                ]

            return participants


class FileParticipantStore(InMemoryParticipantStore):
    def __init__(self, path: str):
        super().__init__()
        self.__path = path
        self.__file_write_lock = Lock()
        self.load()

    def load(self):
        with self.__file_write_lock:
            with open(self.__path, "r") as f:
                participants = json.load(f)
                for participant in participants:
                    self._add_participant(Participant.from_json(participant))

    def save(self):
        with self.__file_write_lock:
            with open(self.__path, "w") as f:
                json.dump([p.to_json() for p in self._participants.values()], f)

    def save_participant(self, participant: Participant):
        self._add_participant(participant)
        self.save()
