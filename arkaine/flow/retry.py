import time
from typing import Any, List, Optional, Tuple, Type, Union

from arkaine.tools.context import Context
from arkaine.tools.tool import Tool


class Retry(Tool):
    """
    A wrapper tool that retries failed executions of another tool.

    This tool will catch exceptions and retry the execution up to a specified
    number of times. It can be configured to only retry on specific exception
    types and to wait between retries.

    Args:
        tool (Tool): The base tool to wrap and retry on failure
        max_retries (int): Maximum number of retry attempts (not counting
        initial try)
        exceptions (Union[Type[Exception], List[Type[Exception]]], optional):
            Specific exception type(s) to retry on. If None, retries on any
            Exception.
        delay (float, optional): Time in seconds to wait between retries.
            Defaults to 0 (no delay).
        name (str, optional): Custom name for the tool.
            Defaults to "{tool.name}::retry_{max_retries}".
        description (str, optional): Custom description.
            Defaults to base tool's description.
    """

    def __init__(
        self,
        tool: Tool,
        max_retries: int,
        exceptions: Optional[
            Union[Type[Exception], List[Type[Exception]]]
        ] = None,
        delay: float = 0,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ):
        self._tool = tool
        self._max_retries = max_retries
        self._delay = delay

        # Handle single exception or list of exceptions
        if exceptions is None:
            self._exceptions = (Exception,)
        elif isinstance(exceptions, list):
            self._exceptions = tuple(exceptions)
        else:
            self._exceptions = (exceptions,)

        if not name:
            name = f"{tool.name}::retry_{max_retries}"

        if not description:
            description = tool.description

        super().__init__(
            name=name,
            args=tool.args,
            description=description,
            func=self.retry_invoke,
            examples=tool.examples,
        )

    def retry_invoke(self, context: Context, **kwargs):
        """
        Execute the wrapped tool with retry logic.

        Args:
            context (Context): The execution context

            **kwargs: Arguments to pass to the wrapped tool

        Returns:
            Any: The result from a successful execution

        Raises:
            Exception: The last exception encountered after all retries are
            exhausted
        """
        attempts = 0
        last_exception = None

        while attempts <= self._max_retries:
            context["attempt"] = attempts + 1
            try:
                return self._tool(context, **kwargs)
            except self._exceptions as e:
                last_exception = e
                attempts += 1

                if attempts <= self._max_retries:
                    if self._delay > 0:
                        time.sleep(self._delay)
                    continue
                break

        # If we get here, we've exhausted all retries
        raise last_exception

    def retry(self, context: Context) -> Any:
        if context.attached is None:
            raise ValueError("no tool assigned to context")

        if context.attached != self:
            raise ValueError(
                f"context is not for {self.name}, is instead for "
                f"{context.attached.name}"
            )

        if context.children is None:
            # In this branch, we never actually succeeded in running the tool
            # and thus never generated any children; therefore we stop here
            # and just re-call.
            original_output = context.output
            context.clear(executing=True)

            return self(context, original_output)
        else:
            # In this branch, we have already generated children and thus
            # we can just retry the last child tool.
            child_ctx = context.children[-1]
            context.children = []

            return self._tool.retry(child_ctx)


def retry(
    max_retries: int = 3,
    delay: float = 0,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception,
    name: Optional[str] = None,
    description: Optional[str] = None,
):
    """
    A decorator that wraps a Tool to add retry functionality.

    Args:
        max_retries (int): Maximum number of retry attempts. Defaults to 3.
        delay (float): Delay in seconds between retries. Defaults to 0.
        exceptions (Union[Type[Exception], Tuple[Type[Exception], ...]]):
            Exception type(s) to catch and retry on. Defaults to Exception.
    """

    def decorator(tool: Tool):
        # Save original invoke method

        return Retry(
            tool,
            max_retries,
            exceptions,
            delay,
            name,
            description,
        )

    return decorator
