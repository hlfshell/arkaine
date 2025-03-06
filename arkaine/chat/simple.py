import pathlib
from os import path
from threading import Lock
from typing import Any, List, Optional, Tuple, Union

from arkaine.backends.backend import Backend
from arkaine.backends.react import ReActBackend
from arkaine.chat.chat import Chat
from arkaine.chat.conversation import Conversation, ConversationStore, Message
from arkaine.llms.llm import LLM
from arkaine.tools.context import Context
from arkaine.tools.tool import Tool
from arkaine.utils.templater import PromptTemplate


class SimpleChat(Chat):
    """
    SimpleChat is a simplistic chat agent, that can have multiple
    conversations, each with their own isolated history, tools, and state. It
    is simple as it follows the chat pattern of message->response - tit for tat
    with no context sharing between conversations, and no initiative outside
    of its response. There is only the user and the agent.

    Args:
        llm (LLM): The language model instance to use for generating responses.

        tools (List[Tool]): List of tools available to the chat agent for
            performing tasks.

        store (ConversationStore, optional): Storage system for managing
            conversation histories. If none is provided, every message will
            be considered a new conversation.

        agent_name (str, optional): Name of the chat agent. Defaults to
            "Arkaine".

        user_name (str, optional): Name to refer to the user. Defaults to
            "User".

        backend (BaseBackend, optional): Backend system for processing tasks.
            If None, defaults to ReActBackend.

        conversation_auto_active (float, optional): Time in seconds before a
            conversation is considered inactive. Defaults to 60.0.

        personality (str, optional): Custom personality description for the
            chat agent. If provided, influences the agent's response style.

        tool_name (str, optional): Identifier for the chat agent tool. Defaults
            to "chat_agent".
    """

    def __init__(
        self,
        llm: LLM,
        tools: List[Tool],
        store: Optional[ConversationStore] = None,
        agent_name: str = "Arkaine",
        user_name: str = "User",
        backend: Optional[Backend] = None,
        conversation_auto_active: float = 60.0,
        personality: Optional[str] = None,
        tool_name: str = "chat_agent",
    ):
        super().__init__(
            llm=llm,
            store=store,
            tools=tools,
            agent_name=agent_name,
            user_name=user_name,
            conversation_auto_active=conversation_auto_active,
            name=tool_name,
        )

        self.__tools = tools
        self.__personality = personality
        if backend is None:
            self._backend = ReActBackend(
                llm=self._llm,
                tools=self.__tools,
                agent_explanation=(
                    "You are tasked with figuring out how to"
                    " complete the given task"
                ),
            )
        else:
            self._backend = backend

    def _identify_tasks(
        self,
        context: Context,
        conversation: Conversation,
    ) -> List[Tuple[str, str]]:
        # If conversation is empty, return empty list without calling LLM
        messages = list(conversation)
        if not messages:
            return []

        # Build tools block for prompt
        tools_block = "\n".join(
            [f"- {tool.name}: {tool.description}" for tool in self.__tools]
        )

        # Get the last message from conversation
        last_message = messages[-1].content if messages else ""

        # Build conversation text
        conversation_text = "\n".join(
            [f"{msg.author}: {msg.content}" for msg in messages[:-1]]
        )

        # Render the task identification prompt
        prompt = SimpleChatPrompts.task_identification()
        prompt = PromptTemplate(prompt).render(
            {
                "tools_block": tools_block,
                "conversation": conversation_text,
                "last_message": last_message,
            }
        )

        # Get response from LLM
        raw_response = self._llm(context, prompt)

        # Parse the response
        tasks = []
        if "NO TASKS" in raw_response:
            return tasks

        # Parse tasks with their thoughts and descriptions
        current_thought = None
        current_description = None

        for line in raw_response.splitlines():
            line = line.strip()
            if line.startswith("TASK:"):
                # Reset for new task
                current_thought = None
                current_description = None
            elif line.startswith("Thought:"):
                current_thought = line.split(":", 1)[1].strip()
            elif line.startswith("Description:"):
                current_description = line.split(":", 1)[1].strip()
                if current_thought and current_description:
                    tasks.append((current_thought, current_description))
                    current_thought = None
                    current_description = None

        if "task_ids" not in context:
            context["task_ids"] = []
        context["task_ids"].extend(tasks)

        return [task for thought, task in tasks]

    def _execute_tasks(self, context: Context, tasks: List[str]) -> List[Any]:
        results = []
        # TODO - parallelize this
        for task in tasks:
            result = self._backend.invoke(
                context=context,
                args={"task": task},
            )
            results.append(result)

        return results

    def _generate_response(
        self, context: Context, conversation: Conversation, results: List[str]
    ) -> str:
        prompt = SimpleChatPrompts.generate_response()

        personality = ""
        if self.__personality:
            personality = (
                "5. **Personality**:\n"
                "\t- You are to emulate the following personality throughout "
                "your conversation with the user:\n"
                f"\t- {self.__personality}\n\n"
            )

        tool_information = "None"
        if len(results) > 0:
            tool_information = "\n".join(
                [f"\t Result:\n\t{result}\n" for result in results]
            )

        conversation_text = ""
        for message in conversation[:-1]:  # Ignore the last message
            conversation_text += (
                f"{message.author} @ {message.on}:\n"
                f"{message.content}\n---\n"
            )

        last_message = conversation[-1].content

        raw_response = self._llm(
            context,
            PromptTemplate(prompt).render(
                {
                    "personality": personality,
                    "agent_name": self._agent_name,
                    "user_name": self._user_name,
                    "tool_information": tool_information,
                    "conversation": conversation_text,
                    "prior_message": last_message,
                }
            ),
        )

        # Parse the response to extract thought and response
        thought = ""
        response = ""

        # Split into lines and process
        lines = raw_response.strip().split("\n")
        current_section = None

        for line in lines:
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Check for section headers
            if line.lower().startswith("thought:"):
                current_section = "thought"
                thought = line[7:].strip()  # Remove "Thought:" prefix
                continue
            elif line.lower().startswith("response:"):
                current_section = "response"
                response = line[9:].strip()  # Remove "Response:" prefix
                continue

            # Append content to current section
            if current_section == "thought":
                thought += " " + line
            elif current_section == "response":
                response += " " + line

        # Store thought in context if needed
        if "thoughts" not in context:
            context["thoughts"] = []
        context["thoughts"].append(thought)

        return response.strip()

    def chat(
        self,
        message: Union[str, Message],
        conversation: Conversation,
        context: Optional[Context] = None,
    ) -> Message:
        if isinstance(message, str):
            message = Message(
                author=self._user_name,
                content=message,
            )

        tasks = self._identify_tasks(context, conversation)

        results = []
        if len(tasks) > 0:
            results = self._execute_tasks(context, tasks)

        response = self._generate_response(context, conversation, results)

        return Message(
            author=self._agent_name,
            content=response,
        )


class SimpleChatPrompts:
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
    def task_identification(cls) -> str:
        return cls._load_prompt("task_identification")

    @classmethod
    def generate_response(cls) -> str:
        return cls._load_prompt("generate_response")
