import pathlib
from os import path
from typing import Any, Callable, List, Optional

from arkaine.llms.llm import LLM, Prompt
from arkaine.tools.agent import Agent
from arkaine.tools.tool import Argument, Context, Example, Tool
from arkaine.utils.templater import PromptTemplate


class ArgsFormatter(Tool):
    """
    A tool wrapper that allows you to add or remove Arguments from tools,
    and/or alter the argument values being passed to a wrapped tool.

    Attributes:
        tool (Tool): The tool to be wrapped. kwargs_formatter
        (Callable[[Context, Any], Any]): A function to format the keyword
            arguments.
        add_args (Optional[List[Argument]]): Additional arguments to be added
            to the tool.
        remove_args (Optional[List[str]]): Arguments to be removed
            from the tool.
        name (Optional[str]): Custom name for the tool - otherwise it defaults
            to the tool's name
        description (Optional[str]): Custom description for the tool,
            defaulting to the tool's description if None is provided.
        examples (Optional[List[Example]]): Custom examples for the tool. If
            not provided, uses the wrapped tool's examples.
    """

    def __init__(
        self,
        tool: Tool,
        kwargs_formatter: Callable[[Context, Any], Any],
        add_args: Optional[List[Argument]] = None,
        remove_args: Optional[List[str]] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        examples: Optional[List[Example]] = None,
    ):
        self._tool = tool
        self._kwargs_formatter = kwargs_formatter
        self._name = name

        args = [arg for arg in tool.args]
        if add_args:
            args.extend(add_args)
        if remove_args:
            args = [arg for arg in args if arg.name not in remove_args]

        name = name or tool.name
        description = description or tool.description
        examples = examples or tool.examples

        super().__init__(name, description, args, self.format, examples)

    def format(self, context: Context, **kwargs: Any) -> Any:
        if self._kwargs_formatter:
            kwargs = self._kwargs_formatter(context, **kwargs)

        return self._tool()


class Formatter(Tool):
    """
    A tool wrapper that formats the output of a wrapped tool. This is useful
    if a tool developed by another developer and you find yourself needing to
    massage the output into a format more friendly to your chosen Agent or
    LLM.

    Attributes:
        tool (Tool): The tool to be wrapped.
        formatter (Callable[[Context, Any], Any]): A function to format the
            output of the tool. Takes the execution context and tool output as
            arguments and returns the formatted result.
        name (Optional[str]): Custom name for the tool. If not provided, uses
            the wrapped tool's name.
        description (Optional[str]): Custom description for the tool. If not
            provided, uses the wrapped tool's description.
        examples (Optional[List[Example]]): Custom examples for the tool. If
            not provided, uses the wrapped tool's examples.
    """

    def __init__(
        self,
        tool: Tool,
        formatter: Callable[[Context, Any], Any],
        name: Optional[str] = None,
        description: Optional[str] = None,
        examples: Optional[List[Example]] = None,
    ):
        self._tool = tool
        self._formatter = formatter

        name = name or tool.name
        description = description or tool.description
        examples = examples or tool.examples

        super().__init__(name, description, tool.args, self.format, examples)

    def format(self, context: Context, **kwargs: Any) -> Any:
        return self._formatter(context, **kwargs)


class FormattingAgent(Agent):
    """
    An agent that reformats the output of a tool using an LLM.

    Attributes:
        tool (Tool): The tool whose output needs to be reformatted.
        llm (LLM): TThe language model to use for reformatting.
        original_format_explanation (str): A description of the input format
            that the tool produces. This helps the LLM understand the structure
            of the data it's working with.
        formatted_format_explanation (str): A description of the desired output
            format that the agent should produce.
        name (Optional[str]): Custom name for the agent. Defaults to the tool's
            name if not provided.
        description (Optional[str]): Custom description for the agent. Defaults
            to the tool's description if not provided.
        examples (Optional[List[Example]]): Custom examples for the agent.
            Defaults to the tool's examples if not provided. tool's examples if
            not provided.
        process_answer (Optional[Callable[[str], Any]]): Optional function to
            process the LLM's response before returning it.
        prompt (Optional[PromptTemplate]): Custom prompt template. If not
            provided, a short default prompt is used.

    The prompt template should use the following placeholders:
        - {original_format}: Description of the input format
        - {formatted_format}: Description of the desired output format
        - {output}: The actual output from the tool that needs to be
          reformatted - this will be set on invocation.
    """

    def __init__(
        self,
        tool: Tool,
        llm: LLM,
        original_format_explanation: str,
        formatted_format_explanation: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        examples: Optional[List[Example]] = None,
        process_answer: Optional[Callable[[Context, str], Any]] = None,
        prompt: Optional[PromptTemplate] = None,
    ):
        self._tool = tool
        self._original_format_explanation = original_format_explanation
        self._formatted_format_explanation = formatted_format_explanation
        self._process_answer = process_answer

        name = name or tool.name
        description = description or tool.description
        examples = examples or tool.examples

        if prompt is None:
            self._prompt = PromptTemplate.from_file(
                path.join(
                    pathlib.Path(__file__).parent,
                    "prompts",
                    "formatting_agent.prompt",
                )
            )
        else:
            self._prompt = prompt

        super().__init__(name, description, tool.args, llm, examples)

    def invoke(self, context: Context, **kwargs) -> Any:
        output = self._tool(context=context, **kwargs)
        return super().invoke(context, output=output)

    def prepare_prompt(self, context: Context, **kwargs: Any) -> Prompt:
        return self._prompt.format(
            original_format=self._original_format_explanation,
            formatted_format=self._formatted_format_explanation,
            output=kwargs["output"],
        )

    def extract_result(self, context: Context, output: str) -> Any:
        if self._process_answer:
            return self._process_answer(context, output)
        return output
