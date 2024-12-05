from agents.tools.tool import Tool, Context, Argument, Example

from typing import Any, List, Optional, Callable, Union


class Conditional(Tool):
    """
    A tool for executing conditional logic based on a specified condition. If
    the condition evaluates to True, the 'then' tool or function is executed.
    Otherwise, the 'otherwise' tool or function is executed if provided.

    Args:
        name: The name of the conditional tool.

        description: A brief description of the tool's purpose.

        args: A list of arguments required by the tool.

        condition: A callable that evaluates to a boolean, determining which
            path to take.

        then: The tool or function to execute if the condition is True.

        otherwise: The tool or function to execute if the condition is False
            (optional).

        examples: A list of examples demonstrating the tool's usage.
    """

    def __init__(
        self,
        name: str,
        description: str,
        args: List[Argument],
        condition: Callable[[Context, Any], bool],
        then: Union[Tool, Callable[[Context, Any], Any]],
        otherwise: Optional[Union[Tool, Callable[[Context, Any], Any]]],
        examples: List[Example],
    ):
        self.condition = condition
        self.then = then
        self.otherwise = otherwise

        super().__init__(name, description, args, examples, self.check)

    def check(self, context: Context, **kwargs) -> Any:
        if self.condition(context, kwargs):
            return self.then(context, kwargs)
        else:
            return self.otherwise(context, kwargs) if self.otherwise else None


class MultiConditional(Tool):
    """
    A tool for executing multiple conditional logic paths. Iterates over a list
    of conditions and executes the corresponding tool or function for the first
    condition that evaluates to True. If no conditions are True, the default
    tool or function is executed if provided.

    Args:
        name: The name of the multi-conditional tool.

        description: A brief description of the tool's purpose.

        args: A list of arguments required by the tool.

        conditions: A list of callables, each evaluating to a boolean. The
            indexes of the conditions list correspond to the indexes of the
            tools list.

        tools: A list of tools or functions to execute corresponding to each
            condition.

        default: The tool or function to execute if no conditions are True
            (optional). If not provided, then the tool executes nothing.

        examples: A list of examples demonstrating the tool's usage.
    """

    def __init__(
        self,
        name: str,
        description: str,
        args: List[Argument],
        conditions: List[Optional[Callable[[Context, Any], bool]]],
        tools: List[Union[Tool, Callable[[Context, Any], Any]]],
        default: Optional[Union[Tool, Callable[[Context, Any], Any]]],
        examples: List[Example],
    ):
        self.conditions = conditions
        self.tools = tools
        self.default = default

        super().__init__(name, description, args, examples, self.check)

    def check(self, context: Context, **kwargs) -> None:
        for condition, tool in zip(self.conditions, self.tools):
            if condition(context, kwargs):
                return tool(context, kwargs)

        return self.default(context, kwargs) if self.default else None
