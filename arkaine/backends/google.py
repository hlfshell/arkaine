import os
from typing import Any, Callable, Dict, List, Optional, Union

import google.generativeai as genai
from google.ai.generativelanguage import GenerateContentResponse

from arkaine.backends.backend import Backend
from arkaine.backends.common import simple_tool_results_to_prompts
from arkaine.llms.google import Google as GoogleLLM
from arkaine.llms.llm import Prompt
from arkaine.tools.context import Context
from arkaine.tools.tool import Tool
from arkaine.tools.types import ToolCalls, ToolResults
from arkaine.utils.templater import PromptTemplate
from arkaine.utils.tool_format import gemini as gemini_format


class GoogleBackend(Backend):

    MODELS = GoogleLLM.MODELS

    def __init__(
        self,
        template: Union[PromptTemplate, str] = PromptTemplate.default(),
        model: str = "gemini-pro",
        tools: List[Tool] = [],
        initial_state: Dict[str, Any] = {},
        process_answer: Optional[Callable[[Any], Any]] = None,
        api_key: Optional[str] = None,
        context_length: Optional[int] = None,
    ):
        if api_key is None:
            api_key = os.environ.get("GOOGLE_AISTUDIO_API_KEY")
            if api_key is None:
                api_key = os.environ.get("GOOGLE_API_KEY")
            if api_key is None:
                raise ValueError(
                    "No Google API key found. Please set "
                    "GOOGLE_AISTUDIO_API_KEY or GOOGLE_API_KEY "
                    "environment variable"
                )

        genai.configure(api_key=api_key)
        self.__model = genai.GenerativeModel(model_name=model)

        if context_length:
            self.__context_length = context_length
        elif model in GoogleBackend.MODELS:
            self.__context_length = GoogleBackend.MODELS[model][
                "context_length"
            ]
        else:
            raise ValueError(
                f"Unknown model: {model} - must specify context length"
            )

        if isinstance(template, str):
            template = PromptTemplate(template)

        self.template = template

        super().__init__(
            None,
            tools,
            initial_state,
            process_answer,
        )

    def parse_for_tool_calls(
        self,
        context: Context,
        response: GenerateContentResponse,
        stop_at_first_tool: bool = False,
    ) -> ToolCalls:
        """Parse the response for tool calls.

        Args:
            context: The current execution context
            response: The model's response
            stop_at_first_tool: Whether to stop after finding the first tool
                call - ignored for this backend, included for abstract
                interface matching

        Returns:
            A list of (tool_name, tool_args) tuples
        """
        tool_calls = []

        # Extract function calls from response parts
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if function_call := part.function_call:
                    # Convert MapComposite to regular dict
                    args_dict = dict(function_call.args)
                    tool_calls.append((function_call.name, args_dict))

        return tool_calls

    def parse_for_result(
        self, context: Context, response: GenerateContentResponse
    ) -> Optional[Any]:
        return response.candidates[0].content.parts[0].text

    def tool_results_to_prompts(
        self, context: Context, prompt: Prompt, results: ToolResults
    ) -> List[Prompt]:
        return simple_tool_results_to_prompts(prompt, results)

    def prepare_prompt(self, context: Context, **kwargs) -> Prompt:
        return self.template.render(kwargs)

    def query_model(
        self, context: Context, prompt: Prompt
    ) -> GenerateContentResponse:
        """Query the Gemini model with tools.

        Args:
            context: The current execution context
            prompt: The prompt to send to the model

        Returns:
            The model's response
        """
        tool_declarations = [
            gemini_format(tool) for tool in self.tools.values()
        ]

        history = []
        for message in prompt:
            role = message["role"]
            content = message["content"]

            # Map OpenAI roles to Gemini roles
            if role == "system":
                history.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                history.append({"role": "model", "parts": [content]})
            elif role == "user":
                history.append({"role": "user", "parts": [content]})

        chat = self.__model.start_chat(history=history[:-1])

        response = chat.send_message(
            history[-1]["parts"][0],
            tools=tool_declarations,
        )

        return response
