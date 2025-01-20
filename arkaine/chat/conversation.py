from __future__ import annotations

import heapq
import json
import pathlib
from abc import ABC, abstractmethod
from datetime import datetime
from os import path
from threading import Lock
from typing import Dict, List, Literal, Optional
from uuid import uuid4

from arkaine.llms.llm import LLM
from arkaine.utils.templater import PromptTemplate


class Message:

    def __init__(
        self,
        author: str,
        content: str,
        on: Optional[datetime] = None,
        id: Optional[str] = None,
    ):
        self.__id = id if id else str(uuid4())
        self.author = author
        self.content = content
        self.on = on if on else datetime.now()

    @property
    def id(self) -> str:
        return self.__id

    def to_json(self):
        return {
            "id": self.__id,
            "author": self.author,
            "content": self.content,
            "on": self.on.isoformat(),
        }

    @classmethod
    def from_json(cls, json: Dict[str, str]) -> Message:
        return cls(
            id=json["id"],
            author=json["author"],
            content=json["content"],
            on=datetime.fromisoformat(json["on"]),
        )

    def __str__(self):
        out = f"Msg {self.__id}\n"
        out += f"{self.author} @ ({self.on.strftime('%Y-%m-%d %H:%M:%S')}):\n"
        out += f"    {self.content}\n"
        return out

    def __repr__(self):
        return self.__str__()

    def __lt__(self, other: Message) -> bool:
        return self.on < other.on

    def __gt__(self, other: Message) -> bool:
        return self.on > other.on

    def __eq__(self, other: Message) -> bool:
        return self.on == other.on


class Conversation:

    # A conversation is a collection of messages in time
    # order with identified "speakers".

    def __init__(
        self,
        messages: List[Message] = [],
        name: Optional[str] = None,
        description: Optional[str] = None,
        id: Optional[str] = None,
    ):
        self.__id = id if id else str(uuid4())
        self.__messages: List[Message] = []
        self.__name = name
        self.__description = description
        self.__lock = Lock()

        for message in messages:
            self.add_message(message)

    @property
    def id(self) -> str:
        return self.__id

    @property
    def name(self) -> str:
        return self.__name

    @property
    def description(self) -> str:
        return self.__description

    @property
    def participants(self) -> List[str]:
        with self.__lock:
            return list(set([m.author for m in self.__messages]))

    @property
    def last_message_on(self) -> datetime:
        with self.__lock:
            return self.__messages[-1].on

    def add_message(self, message: Message):
        with self.__lock:
            heapq.heappush(self.__messages, message)

    def to_json(self) -> Dict[str, str]:
        return {
            "id": self.__id,
            "name": self.__name,
            "description": self.__description,
            "messages": [m.to_json() for m in self.__messages],
        }

    @classmethod
    def from_json(cls, json: Dict[str, str]) -> Conversation:
        return cls(
            messages=[Message.from_json(m) for m in json["messages"]],
            name=json["name"],
            description=json["description"],
            id=json["id"],
        )

    def append(self, message: Message):
        with self.__lock:
            self.__messages.append(message)

    def label(self, llm: LLM):
        prompt = PromptTemplate(_ConversationPrompts.label())

        attempts = 0
        while attempts < 3:
            try:
                attempts += 1

                response = llm.completion(
                    prompt.render(
                        {
                            "messages": self.to_markdown(),
                        }
                    )
                )

                # Parse response in a resilient way
                lines = response.strip().split("\n")
                title = None
                description = None

                for line in lines:
                    line = line.strip()
                    if line.startswith("TITLE:"):
                        title = line[6:].strip()
                    elif line.startswith("DESCRIPTION:"):
                        description = line[12:].strip()

                if title and description:
                    with self.__lock:
                        self.__name = title
                        self.__description = description
                        return
                else:
                    raise ValueError(
                        "Could not parse title and description from response"
                    )

            except Exception as e:
                print(f"Failed to generate name and description: {e}")
                return
        print(
            "Failed to generate name and description for "
            f"conversation {self.__id} after 3 attempts"
        )

    def is_continuation(self, llm: LLM, message: Message) -> bool:
        prompt = PromptTemplate(_ConversationPrompts.continuation())

        if self.__messages:
            last_message_time = self.__messages[-1].on
            time_difference = (
                message.on - last_message_time
            ).total_seconds() / 60
            ago = "<1" if time_difference < 1 else str(int(time_difference))
        else:
            ago = "<1"

        response = llm.completion(
            prompt.render(
                {
                    "messages": self.to_markdown(),
                    "new_message": message.content,
                    "time": ago,
                }
            )
        )
        return "continuation: true" in response.strip().lower()

    def to_markdown(self) -> str:
        with self.__lock:
            if self.__name:
                out = f"# {self.__name}\n"
            else:
                out = "# Conversation\n"

            if self.__description:
                out += f"{self.__description}\n"

            out += "---\n"

            if self.__messages:
                for msg in self.__messages:
                    out += f"### {msg.author} @ "
                    out += f"({msg.on.strftime('%Y-%m-%d %H:%M:%S')}):\n"
                    out += f"{msg.content}\n"
                    out += "---\n"

            return out

    def __len__(self) -> int:
        with self.__lock:
            return len(self.__messages)

    def __str__(self) -> str:
        if self.__name:
            out = f"{self.__name}\n"
        else:
            out = "Conversation\n"

        out += f"Between {', '.join(self.participants)}\n"
        out += f"With {len(self)} messages\n"
        return out

    def __iter__(self):
        with self.__lock:
            return iter(self.__messages)

    def __getitem__(self, index: int) -> Message:
        with self.__lock:
            return self.__messages[index]


class ConversationStore(ABC):

    def __init__(self):
        super().__init__()

    @abstractmethod
    def get_conversation(self, id: str) -> Optional[Conversation]:
        pass

    @abstractmethod
    def save_conversation(self, conversation: Conversation):
        pass

    @abstractmethod
    def get_conversations(
        self,
        participants: Optional[List[str]] = None,
        after: Optional[datetime] = None,
        limit: Optional[int] = None,
        order: Literal["newest", "oldest"] = "newest",
    ) -> List[Conversation]:
        pass


class InMemoryConversationStore(ConversationStore):

    def __init__(self):
        super().__init__()
        self._conversations: Dict[str, Conversation] = {}
        self.__participants: Dict[str, set[str]] = {}
        self.__lock = Lock()

    def get_conversation(self, id: str) -> Conversation:
        with self.__lock:
            return self._conversations[id]

    def save_conversation(self, conversation: Conversation):
        self._add_conversation(conversation)

    def _add_conversation(self, conversation: Conversation):
        with self.__lock:
            self._conversations[conversation.id] = conversation
            for speaker in conversation.participants:
                if speaker not in self.__participants:
                    self.__participants[speaker] = set()
                self.__participants[speaker].add(conversation.id)

    def get_conversations(
        self,
        participants: Optional[List[str]] = None,
        after: Optional[datetime] = None,
        limit: Optional[int] = None,
        order: Literal["newest", "oldest"] = "newest",
    ) -> List[Conversation]:
        with self.__lock:
            # Start with all conversations
            conversations = list(self._conversations.values())

            # Filter by speakers if specified
            if participants:
                conversations = [
                    conv
                    for conv in conversations
                    if all(
                        speaker in conv.participants for speaker in participants
                    )
                ]

            # Filter by date if specified
            if after:
                conversations = [
                    conv
                    for conv in conversations
                    if conv.last_message_on > after
                ]

            # Sort by last message date, respecting the order parameter
            conversations.sort(
                key=lambda x: x.last_message_on, reverse=(order == "newest")
            )

            # Apply limit if specified
            if limit:
                conversations = conversations[:limit]

            return conversations


class FileConversationStore(InMemoryConversationStore):

    def __init__(self, path: str):
        super().__init__()
        self.__path = path
        self.__file_write_lock = Lock()

    def reload(self):
        with self.__file_write_lock:
            with open(self.__path, "r") as f:
                conversations = json.load(f)
                for conversation in conversations:
                    self._add_conversation(Conversation.from_json(conversation))

    def save(self):
        with self.__file_write_lock:
            with open(self.__path, "w") as f:
                json.dump(
                    [c.to_json() for c in self._conversations.values()], f
                )

    def save_conversation(self, conversation: Conversation):
        self._add_conversation(conversation)
        self.save()


class _ConversationPrompts:
    _lock = Lock()
    _prompts = {}

    @classmethod
    def _load_prompt(cls, name: str) -> str:
        with cls._lock:
            if name not in cls._prompts:
                filepath = path.join(
                    pathlib.Path(__file__).parent,
                    "prompts",
                    f"{name}.prompt",
                )
                with open(filepath, "r") as f:
                    cls._prompts[name] = f.read()
            return cls._prompts[name]

    @classmethod
    def label(cls) -> str:
        return cls._load_prompt("conversation_label")

    @classmethod
    def continuation(cls) -> str:
        return cls._load_prompt("conversation_continuation")
