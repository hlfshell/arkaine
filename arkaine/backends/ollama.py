from typing import Any, Callable, Dict, List, Tuple

from ollama import Client

from arkaine.backends.backend import Backend
from arkaine.backends.common import simple_tool_results_to_prompts
from arkaine.tools.agent import Prompt
from arkaine.tools.context import Context
from arkaine.tools.tool import Tool
from arkaine.tools.types import ToolArguments, ToolResults


class Ollama(Backend):

    def __init__(
        self,
        model: str,
        tools: List[Tool],
        get_prompt: Callable[..., Prompt],
        host: str = "http://localhost:11434",
        default_temperature: float = 0.7,
        request_timeout: float = 120.0,
        verbose: bool = False,
        initial_state: Dict[str, Any] = {},
    ):
        super().__init__(
            None, tools, max_simultaneous_tools=1, initial_state=initial_state
        )

        self.model = model
        self.get_prompt = get_prompt
        self.default_temperature = default_temperature
        self.verbose = verbose
        self.request_timeout = request_timeout

        self.__client = Client(host)

    def __tool_descriptor(self, tool: Tool) -> Dict:
        properties = {}
        required_args = []

        for arg in tool.args:
            properties[arg.name] = {
                "type": arg.type,
                "description": arg.description,
            }
            if arg.required:
                required_args.append(arg.name)

        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required_args,
                },
            },
        }

    def query_model(self, context: Context, prompt: Prompt):
        return self.__client.chat(
            model=self.model,
            messages=prompt,
            tools=[
                self.__tool_descriptor(tool) for tool in self.tools.values()
            ],
        )

    def parse_for_result(
        self, context: Context, response: Dict[str, Any]
    ) -> str:
        return response["message"]["content"]

    def parse_for_tool_calls(
        self,
        context: Context,
        response: Dict[str, Any],
        stop_at_first_tool: bool = False,
    ) -> List[Tuple[str, ToolArguments]]:
        tool_calls_raw = response["message"].get("tool_calls")

        if not tool_calls_raw:
            return []

        tool_calls: List[Tuple[str, ToolArguments]] = []
        for tool_call in tool_calls_raw:
            name = tool_call["function"]["name"]
            args = tool_call["function"]["arguments"]

            tool_calls.append((name, args))

            if stop_at_first_tool:
                return tool_calls

        return tool_calls

    def tool_results_to_prompts(
        self,
        context: Context,
        prompt: Prompt,
        results: ToolResults,
    ) -> List[Prompt]:
        return simple_tool_results_to_prompts(prompt, results, "assistant")

    def prepare_prompt(self, context: Context, **kwargs) -> Prompt:
        return self.get_prompt(kwargs)
