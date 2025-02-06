from __future__ import annotations
from abc import ABC, abstractmethod
from concurrent.futures import ALL_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from uuid import uuid4

from arkaine.chat.conversation import Conversation, ConversationStore, Message
from arkaine.internal.registrar.registrar import Registrar
from arkaine.llms.llm import LLM
from arkaine.tools.context import Context
from arkaine.tools.tool import Tool
from arkaine.tools.types import ToolCalls, ToolResults


class Chat(ABC):

    def __init__(
        self,
        llm: LLM,
        store: ConversationStore,
        tools: List[Tool] = [],
        agent_name: str = "Arkaine",
        user_name: str = "User",
        conversation_auto_active: float = 60.0,
        name: str = "chat_agent",
        tool_timeout: float = 30.0,
        id: Optional[str] = None,
    ):
        super().__init__()

        if id is None:
            id = str(uuid4())

        self.__id = id
        self.__name = name
        self.__type = "chat"

        self.description = f"A chat agent between {agent_name} and {user_name}"

        self._llm = llm
        self._store = store
        self._agent_name = agent_name
        self._user_name = user_name
        self._conversation_auto_active = conversation_auto_active
        self._tool_timeout = tool_timeout
        self._tools = {tool.tname: tool for tool in tools}

        self._executor = ThreadPoolExecutor()
        self._on_call_listeners: List[Callable[[Chat, Context], None]] = []

        Registrar.register(self)

    def __del__(self):
        if self.__executor:
            self.__executor.shutdown(wait=False)

    @property
    def id(self) -> str:
        return self.__id

    @property
    def name(self) -> str:
        return self.__name

    @property
    def type(self) -> str:
        return self.__type

    def to_json(self) -> Dict[str, Any]:
        return {
            "id": self.__id,
            "name": self.name,
            "description": self.description,
            "type": self.__type,
        }

    @abstractmethod
    def chat(
        self, message: Message, conversation: Conversation, context: Context
    ) -> Union[str, Message]:
        pass

    def _get_active_conversation(self, new_message: Message) -> Conversation:
        try:
            conversations = self._store.get_conversations(
                order="newest",
                limit=1,
                participants=[self._agent_name, new_message.author],
            )
            last_conversation = (
                None if len(conversations) == 0 else conversations[0]
            )
            if last_conversation is None:
                return Conversation()

            if (
                last_conversation.last_message_on
                + timedelta(seconds=self._conversation_auto_active)
                > datetime.now()
            ):
                return last_conversation

            # If the conversation is a bit old, then ask the LLM if it is a
            # continuation of the last conversation
            if last_conversation.is_continuation(self._llm, new_message):
                return last_conversation
            else:
                return Conversation()

        except Exception as e:
            print(f"Error getting active conversation: {e}")
            return Conversation()

    def _chat_func(
        self,
        context: Context,
        message: Union[str, Message],
        conversation: Optional[Conversation] = None,
    ) -> str:
        if isinstance(message, str):
            message = Message(
                author=self._user_name,
                content=message,
            )

        if conversation is None:
            # Load the last conversation
            conversation = self._get_active_conversation(message)

        conversation.append(message)

        response = self.chat(message, conversation, context=context)
        if response is None:
            response = ""
        if isinstance(response, str):
            response = Message(author=self._agent_name, content=response)

        conversation.append(response)
        conversation.label(self._llm)

        self._store.save_conversation(conversation)

        return response.content

    def _call_tools(self, tool_calls: List[ToolCalls]) -> ToolResults:
        results: List[Tuple[str, Dict[str, Any], Any]] = []
        processes: List[Tuple[str, Dict[str, Any], Future]] = []

        # Launch all tool calls
        for name, args in tool_calls:
            ctx = self._tools[name].async_call(args)
            processes.append((name, args, ctx.future()))

        done, _ = wait(
            [f for _, _, f in processes],
            timeout=self._tool_timeout,
            return_when=ALL_COMPLETED,
        )

        for name, args, future in processes:
            try:
                if future in done:
                    result = future.result()
                else:
                    result = None
                results.append((name, args, result))
            except Exception as e:
                results.append((name, args, e))

        return results

    def extract_arguments(self, args, kwargs) -> Tuple[Context, Dict[str, Any]]:
        context = None
        if args and isinstance(args[0], Context):
            context = args[0]
            args = args[1:]

        if len(args) == 1 and not kwargs and isinstance(args[0], dict):
            kwargs = args[0]
            args = ()

        if "context" in kwargs:
            if context is not None:
                raise ValueError("context passed twice")
            context = kwargs.pop("context")

        tool_args = ["message", "conversation"]
        for i, value in enumerate(args):
            if i < len(tool_args):
                if tool_args[i] in kwargs:
                    raise TypeError(
                        f"Got multiple values for argument '{tool_args[i]}'"
                    )
                kwargs[tool_args[i]] = value

        return context, kwargs

    def _init_context_(self, context: Optional[Context], kwargs) -> Context:
        if context is None:
            ctx = Context(self)
        else:
            ctx = context

        if ctx.executing:
            ctx = context.child_context(self)
            ctx.executing = True
        else:
            if not ctx.attached:
                ctx.attached = self
            ctx.executing = True

        ctx.args = kwargs

        for listener in self._on_call_listeners:
            self._executor.submit(listener, self, ctx)

        return ctx

    def add_on_call_listener(self, listener: Callable[[Chat, Context], None]):
        self._on_call_listeners.append(listener)

    def __call__(self, *args, **kwargs) -> Union[str, Message]:
        context, kwargs = self.extract_arguments(args, kwargs)

        with self._init_context_(context, kwargs) as ctx:
            # Try to extract message and conversation from kwargs,
            # defaulting to None if not found
            message = kwargs.pop("message", None)
            conversation = kwargs.pop("conversation", None)

            if message is None:
                raise ValueError("message is required")

            if not isinstance(message, str) and not isinstance(
                message, Message
            ):
                raise ValueError("message must be a string or a Message")

            if conversation is not None and not isinstance(
                conversation, Conversation
            ):
                raise ValueError("conversation must be a Conversation")

            ctx.args = {
                "message": message,
                "conversation": conversation,
            }

            output = self._chat_func(ctx, message, conversation)
            ctx.output = output

            return output
