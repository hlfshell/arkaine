from typing import Any, Callable, Optional, Union

from arkaine.tools.tool import Context, Tool
from arkaine.tools.toolify import toolify


class OnError(Tool):
    """
    A tool that wraps another tool and executes an error handler if the primary
    tool raises an exception.

    This tool executes a primary tool and, if it fails with an exception,
    triggers a specified error handler tool/function. The error handler
    receives both the original context and the exception that occurred.

    For a retry, the execution/child context of the on_error tool, if there, is
    cleared and retry is called on the wrapped tool as normal.

    Note that if the on_error function is called, can optionally record the
    exception or the output of the on_error function via the

    Args:
        tool (Union[Tool, Callable[[Context, Any], Any]]): The primary tool or
            function to execute

        on_error (Union[Tool, Callable[[Context, Any], Any]]): The
            tool or function to handle errors. It receives the context and the
            exception that occurred.

        on_error_formatter (Optional[Callable[Context, Exception], Any]): An
            optional function that receives the exception of the context and
            can return anything to pass to the on_error tool.

        set_exception (bool): If True, the exception thrown by the based tool
            is recorded against the OnError's context. If False, it will only
            show an exception if an exception is thrown by the on_error tool.

        name (Optional[str]): The name of the error handling tool. Defaults to
            tool_name::onerror

        description (Optional[str]): Description of what the tool accomplishes.
            Defaults to the wrapped tool description

        id (Optional[str]): The unique identifier for the tool
    """

    def __init__(
        self,
        tool: Union[Tool, Callable[[Context, Any], Any]],
        on_error: Union[Tool, Callable[[Context, Exception], Any]],
        on_error_formatter: Optional[
            Callable[[Context, Exception], Any]
        ] = None,
        set_exception: bool = False,
        name: Optional[str] = None,
        description: Optional[str] = None,
        id: Optional[str] = None,
    ):
        if name is None:
            name = f"{tool.name}::onerror"
        if description is None:
            description = tool.description

        self.__tool = tool
        self.__on_error_formatter = on_error_formatter
        self.__set_exception = set_exception

        super().__init__(
            tool=tool,
            name=name,
            description=description,
            id=id,
            function=self._trigger,
        )

    def _trigger(self, context: Context, *args: Any, **kwargs: Any) -> Any:
        trigger_exception = False
        try:
            output = self.__tool(context, *args, **kwargs)

            if context.exception:
                trigger_exception = True
        except:  # noqa: E722
            trigger_exception = True
        finally:
            if trigger_exception:
                if self.__set_exception:
                    context.exception = context.exception

                if self.__on_error_formatter:
                    on_error_input = self.__on_error_formatter(
                        context, context.exception
                    )
                else:
                    on_error_input = context.exception

                return self.__on_error(context, on_error_input)
            else:
                return output

    def retry(self, context: Context, *args: Any, **kwargs: Any) -> Any:
        if context.tool is None:
            raise ValueError("no tool assigned to context")
        if context.tool != self:
            raise ValueError(
                f"context is not for {self.name}, is instead for "
                f"{context.tool.name}"
            )

        args = context.args
        context.clear()

        if len(context.children) > 1:
            context.children.pop()

        if context.children[0].tool:
            context.children[0].tool.retry(context.children[0], args)
