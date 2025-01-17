from datetime import datetime, timedelta
from typing import List, Optional, Union

from arkaine.backends.ollama import Ollama
from arkaine.connectors.chat.conversation import (
    Conversation,
    ConversationStore,
    Message,
)
from arkaine.llms.llm import LLM
from arkaine.llms.openai import OpenAI
from arkaine.toolbox.summarizer import Summarizer
from arkaine.tools import Tool
from arkaine.tools.argument import Argument
from arkaine.tools.result import Result
from arkaine.tools.tool import Context, Tool
from arkaine.tools.types import ToolCall
from arkaine.utils.tool_format import openai as openai_tool_format


class Simple(Tool):
    """
    Simple is a simplistic chat agent, that can have multiple conversations,
    each with their own isolated history, tools, and state. It is simple in two
    ways:

    1. It follows the chat pattern of message->response - tit for tat - with no
        context sharing between conversations, no initiative. There is only the
        user and the agent.

    2. Its tool calling is handled in a simple manner (and is likely the aspect
        that children classes will want to override).

    If the LLM passed is OpenAI or Ollama, which have their own tool calling
    format/support, then the tool calling is handled by the LLM directly rather
    than arkaine parsing code.
    """

    def __init__(
        self,
        llm: LLM,
        tools: List[Tool],
        store: ConversationStore,
        agent_name: str = "Arkaine",
        user_name: str = "User",
        conversation_auto_active: float = 60.0,
    ):
        super().__init__(
            name="chat_agent",
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
                name="response",
                description="The response from the chat agent",
                type="str",
            ),
        )

        self.__llm = llm
        self.__tools = tools
        self.__store = store

        if isinstance(self.__llm, OpenAI):
            pass
        elif isinstance(self.__llm, Ollama):
            pass
        else:
            pass

        self.__conversation_summary_locks = {}

        self.__summarizer = Summarizer(
            llm=self.__llm,
        )

    def get_active_conversation(self, new_message: Message) -> Conversation:
        try:
            converstaions = self.__store.get_conversations(
                order="newest", limit=1
            )
            last_conversation = (
                None if len(converstaions) == 0 else converstaions[0]
            )
            if last_conversation is None:
                return Conversation()

            if (
                last_conversation.last_message_on
                + timedelta(seconds=self.__conversation_auto_active)
                > datetime.now()
            ):
                return last_conversation

            # If the conversation is a bit old, then ask the LLM if it is a
            # continuation of the last conversation
            if last_conversation.is_continuation(self.__llm, new_message):
                return last_conversation
            else:
                return Conversation()

        except Exception as e:
            print(f"Error getting active conversation: {e}")
            return Conversation()

    def __parse_tool_calls(self, response: str) -> List[ToolCall]:
        pass

    def _respond(self, context: Context, conversation: Conversation) -> Message:
        """
        The goal of this function is to generate a response to the conversation, then
        parse if we have any tool calls. If we do, we execute them, gather the data,
        then convert the results back to information for the agent. We then repeat this
        process until we have no more tool calls and the agent's final response is
        returned.
        """
        pass

    def chat(
        self,
        message: Union[str, Message],
        conversation: Conversation,
        context: Optional[Context] = None,
    ) -> Message:
        if isinstance(message, str):
            message = Message(
                role="user",
                content=message,
            )

        conversation.append(message)
        response = self.respond(context, conversation)

        conversation.label(self.__llm)

        self.__store.save_conversation(conversation)

        return response

    def _chat_func(self, context: Context, message: str) -> str:
        # Load the last conversation
        conversation = self.get_active_conversation(message)

        response = self.chat(message, conversation, context=context)

        return response.content
