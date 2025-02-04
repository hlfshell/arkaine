from typing import Any, Callable, List, Optional, Union
from uuid import uuid4

from arkaine.tools.events import ToolReturn
from arkaine.tools.tool import Argument, Context, Example, Tool


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

        id: The unique identifier for the tool; defaults to a random UUID.
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
        id: Optional[str] = None,
    ):
        self.__id = id or str(uuid4())
        self.condition = condition
        self.then = then
        self.otherwise = otherwise

        super().__init__(
            name, description, args, self.check, examples, self.__id
        )

    def check(self, context: Context, **kwargs) -> Any:
        if self.condition(context, kwargs):
            context["branch"] = "then"
            return self.then(context, kwargs)
        else:
            context["branch"] = "otherwise"
            return self.otherwise(context, kwargs) if self.otherwise else None

    def retry(self, context: Context) -> Any:
        if context.attached is None:
            raise ValueError("no tool assigned to context")
        elif not isinstance(context.attached, Tool):
            raise ValueError(
                "context.attached must be an instance of Tool, got "
                f"{type(context.attached)}"
            )
        if context.attached != self:
            raise ValueError(
                f"context is not for {self.name}, is instead for "
                f"{context.attached.name}"
            )

        original_args = context.args
        context.clear()

        # If we failed during the conditional check, we would not have a branch
        # assigned and thus no children. In this case, we can just recall this
        # tool with the last args
        if len(context.children) == 0:
            return self(context, **original_args)
        else:
            # If we failed after the conditional check, we need to
            # trigger the selected branch, which is our lone child.
            context.executing = True
            with context:
                child_ctx = context.children[0]
                output = child_ctx.attached.retry(child_ctx)

                context.output = output
                context.broadcast(ToolReturn(output))

                return output


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

        id: The unique identifier for the tool; defaults to a random UUID.
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
        id: Optional[str] = None,
    ):
        self.__id = id or str(uuid4())
        self.conditions = conditions
        self.tools = tools
        self.default = default

        super().__init__(
            name, description, args, self.check, examples, self.__id
        )

    def check(self, context: Context, **kwargs) -> None:
        for condition, tool in zip(self.conditions, self.tools):
            if condition(context, kwargs):
                return tool(context, kwargs)

        return self.default(context, kwargs) if self.default else None

    def retry(self, context: Context) -> Any:
        if context.attached is None:
            raise ValueError("no tool assigned to context")

        if context.attached != self:
            raise ValueError(
                f"context is not for {self.name}, is instead for "
                f"{context.attached.name}"
            )

        original_args = context.args
        context.clear()

        # If we failed during the conditional check, we would not have a branch
        # assigned and thus no children. In this case, we can just recall this
        # tool with the last args
        if len(context.children) == 0:
            return self(context, **original_args)
        else:
            # If we failed after the conditional check, we need to
            # trigger the selected branch, which is our lone child.
            context.executing = True
            with context:
                child_ctx = context.children[0]
                output = child_ctx.attached.retry(child_ctx)

                context.output = output
                context.broadcast(ToolReturn(output))

                return output
