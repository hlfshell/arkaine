from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from agents.context import Context, Event

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
        self,
        name: str,
        description: str,
        type: str,
        required: bool = False,
        default: Optional[str] = None,
    ):
        self.name = name
        self.description = description
        self.type = type
        self.required = required
        self.default = default

    def __str__(self) -> str:
        out = f"{self.name} - {self.type} - Required: "
        out += f"{self.required} - "
        if self.default:
            out += f"Default: {self.default} - "
        out += f"{self.description}"

        return out


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

    def __call__(self, context: Optional[Context] = None, **kwargs) -> Any:
        if context and not context.is_root:
            ctx = context.child_context()
        elif context and context.is_root:
            ctx = context
        else:
            ctx = None

        kwargs = self.fulfill_defaults(kwargs)

        try:
            self.check_arguments(kwargs)

            results = self.func(**kwargs)
            if ctx:
                ctx.output = results

            return results
        except Exception as e:
            if ctx:
                ctx.exception(e)
            raise e

    def examples_text(
        self, example_format: Optional[Callable[[Example], str]] = None
    ) -> List[str]:
        if not example_format:
            example_format = Example.ExampleBlock

        return [example_format(self.name, example) for example in self.examples]

    def __str__(self) -> str:
        return Tool.stringify(self)

    def fulfill_defaults(self, args: ToolArguments) -> ToolArguments:
        """
        Given a set of arguments, check to see if any argument that is assigned
        a default value is missing a value and, if so, fill it with the
        default.
        """
        for arg in self.args:
            if arg.name not in args and arg.default:
                args[arg.name] = arg.default

        return args

    def check_arguments(self, args: ToolArguments):
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
            arg.name: {
                "title": arg.name,
                "type": arg.type,
                "default": arg.default,
            }
            for arg in tool.args
        }

        # Create the required list
        required = [arg.name for arg in tool.args if arg.required]

        # Add properties and required to the output
        output += f'"properties": {properties}, '
        output += f'"required": {required}' + "}"

        return output


class ToolCalled(Event):
    def __init__(self, id: str, tool: str, args: ToolArguments):
        super().__init__("tool_called", id)

        self.tool = tool
        self.args = args

    def __str__(self) -> str:
        out = f"{self.id}: {self.tool}("
        for arg, value in self.data.items():
            out += ", ".join(f"{arg}={value}")
        out += ")"

        return out


class ToolStart(Event):
    def __init__(self, id: str, tool: str):
        super().__init__("tool_start", id)

        self.tool = tool


class ToolReturn(Event):
    def __init__(self, id: str, result: Any):
        super().__init__("tool_return", id, result)


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
