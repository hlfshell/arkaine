from abc import ABC, abstractmethod
from concurrent.futures import ALL_COMPLETED, Future, wait
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

from arkaine.chat.conversation import Conversation, ConversationStore, Message
from arkaine.llms.llm import LLM
from arkaine.tools.argument import Argument
from arkaine.tools.context import Context
from arkaine.tools.result import Result
from arkaine.tools.tool import Tool
from arkaine.tools.types import ToolCalls, ToolResults


class Chat(Tool, ABC):

    def __init__(
        self,
        llm: LLM,
        store: Optional[ConversationStore] = None,
        tools: List[Tool] = [],
        agent_name: str = "Arkaine",
        user_name: str = "User",
        conversation_auto_active: float = 60.0,
        name: str = "chat_agent",
        tool_timeout: float = 30.0,
    ):

        super().__init__(
            name=name,
            description=f"A chat agent between {agent_name} and {user_name}",
            args=[
                Argument(
                    name="message",
                    description="A message to send to the chat agent",
                    type="str",
                )
            ],
            func=self._chat_func,
            result=Result(
                description="The response from the chat agent",
                type="str",
            ),
        )

        self._llm = llm
        self._store = store
        self._agent_name = agent_name
        self._user_name = user_name
        self._conversation_auto_active = conversation_auto_active
        self._tool_timeout = tool_timeout
        self._tools = {tool.tname: tool for tool in tools}

    def _get_active_conversation(self, new_message: Message) -> Conversation:
        if self._store is None:
            return Conversation()
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

    def _chat_func(self, context: Context, message: Union[str, Message]) -> str:
        if isinstance(message, str):
            message = Message(
                author=self._user_name,
                content=message,
            )

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

        if self._store is not None:
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

    @abstractmethod
    def chat(
        self, message: Message, conversation: Conversation, context: Context
    ) -> Union[str, Message]:
        pass
