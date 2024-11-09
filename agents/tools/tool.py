from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

# ToolArguments are a dict of the arguments passed to a function, with the key
# being the argument name and the value being the argument value.
ToolArguments = Dict[str, Any]

# ToolResults are a type representing a set of of possible tool calls,
# arguments provided, and their results, representing a history of queries from
# an LLM to their tools. The format is a list of tuples; each tuple represents
# the name of the tool, a ToolArguments, and finally the return result of that
# tool.
ToolResults = List[Tuple[str, ToolArguments, Any]]


class Argument:
    def __init__(
        self, name: str, description: str, type: str, required: bool = False
    ):
        self.name = name
        self.description = description
        self.type = type
        self.required = required

    def __str__(self) -> str:
        return f"{self.name} - {self.type} - Required: {self.required} - {self.description}"


class Example:
    def __init__(
        self,
        name: str,
        args: Dict[str, str],
        output: Optional[str] = None,
        description: Optional[str] = None,
        explanation: Optional[str] = None,
    ):
        self.name = name
        self.args = args
        self.output = output
        self.description = description
        self.explanation = explanation

    @classmethod
    def ExampleBlock(function_name: str, example: Example) -> str:
        out = ""
        if example.description:
            out += f"{example.description}\n"
        out += f"{function_name}("

        first_arg = True
        for arg, value in example.args.items():
            if not first_arg:
                out += ", "
            out += f"{arg}={value}"
        out += ")"
        if example.output:
            out += f"\nReturns:\n{example.output}"

        if example.explanation:
            out += f"\nExplanation: {example.explanation}"

        return out


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        args: List[Argument],
        func: Callable,
        examples: List[Example] = [],
    ):
        self.name = name
        self.description = description
        self.args = args
        self.func = func
        self.examples = examples

    def __call__(self, args: Dict[str, Any]):
        self.check_arguments(args)
        return self.func(args)

    def examples_text(
        self, example_format: Optional[Callable[[Example], str]] = None
    ) -> List[str]:
        if not example_format:
            example_format = Example.ExampleBlock

        return [example_format(self.name, example) for example in self.examples]

    def __str__(self) -> str:
        return Tool.stringify(self)

    def check_arguments(self, args: Dict[str, Any]):
        missing_args = []
        extraneous_args = []

        arg_names = [arg.name for arg in self.args]
        for arg in args.keys():
            if arg not in arg_names:
                extraneous_args.append(arg)

        for arg in self.args:
            if arg.required and arg.name not in args:
                missing_args.append(arg.name)

        if missing_args or extraneous_args:
            raise InvalidArgumentException(
                self.name, missing_args, extraneous_args
            )

    @staticmethod
    def stringify(tool: Tool) -> str:
        # Start with the tool name and description
        output = f"> Tool Name: {tool.name}\n"
        output += (
            "Tool Description: "
            f"{tool.name}({', '.join([arg.name + ': ' + arg.type for arg in tool.args]            )})\n\n"
        )

        # Add the function description, indented with 4 spaces
        output += f"    {tool.description}\n"

        # Add the Tool Args section
        output += "    \n"
        output += "Tool Args: {"

        # Create the properties dictionary
        properties = {
            arg.name: {"title": arg.name, "type": arg.type} for arg in tool.args
        }

        # Create the required list
        required = [arg.name for arg in tool.args if arg.required]

        # Add properties and required to the output
        output += f'"properties": {properties}, '
        output += f'"required": {required}, '
        output += '"type": "object"}'

        return output


class InvalidArgumentException(Exception):
    def __init__(
        self,
        tool_name: str,
        missing_required_args: List[str],
        extraneous_args: List[str],
    ):
        self.__tool_name = tool_name
        self.__missing_required_args = missing_required_args
        self.__extraneous_args = extraneous_args

    def __str__(self):
        out = f"Function {self.__tool_name} was improperly called\n"

        if self.__missing_required_args:
            out += (
                "Missing required arguments: "
                + ", ".join(self.__missing_required_args)
                + "\n"
            )
        if self.__extraneous_args:
            out += (
                "Extraneous arguments: "
                + ", ".join(self.__extraneous_args)
                + "\n"
            )

        return out
