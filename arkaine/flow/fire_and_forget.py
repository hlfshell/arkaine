from threading import Thread
from typing import Any, Callable, Optional, Union

from arkaine.tools.context import Context
from arkaine.tools.tool import Tool
from arkaine.tools.toolify import toolify
from arkaine.utils.store.context import GlobalContextStore


class FireAndForget(Tool):
    """
    A tool that wraps another tool or function and executes it asynchronously
    without waiting for results.

    This tool is useful for launching background tasks where the immediate
    result is not needed. It returns immediately after launching the wrapped
    tool.

    The tool launch will be its own context, not part of the parent context.

    If a retry is requested and allowed, this tool will first check to see if
    it can acquire the context that it returned. If it can not, it will simply
    complete as if it succeeded. If it can, it will then call retry on that
    context. From there, the retry will be handled as normal for that
    tool/context.

    Args:
        tool (Union[Tool, Callable[[Context, Any], Any]]): The tool or function
            to execute

        name (Optional[str]): The name of the fire and forget tool. Defaults to
            tool_name::firenforget

        description (Optional[str]): Description of what the tool accomplishes.
            Defaults to the wrapped tool description

        id (Optional[str]): The unique identifier for the tool

        allow_retry (bool): Whether or not to allow the tool to be retried.
        Defaults to True.

    Returns:
        The string id of the context of the launched tool.
    """

    def __init__(
        self,
        tool: Union[Tool, Callable[[Context, Any], Any]],
        name: Optional[str] = None,
        description: Optional[str] = None,
        id: Optional[str] = None,
        allow_retry: bool = True,
    ):
        if name is None:
            name = f"{tool.name}::firenforget"
        if description is None:
            description = tool.description
        self.__allow_retry = allow_retry

        self.tool = tool if isinstance(tool, Tool) else toolify(tool)

        super().__init__(
            name=name,
            args=tool.args,
            description=description,
            func=self.fire_off,
            examples=tool.examples,
            id=id,
        )

    def fire_off(self, context: Context, **kwargs) -> dict:
        # Launch the tool asynchronously
        ctx = self.tool.async_call(context, kwargs)

        return ctx.id

    def retry(self, context: Context) -> Any:
        """
        Retry the fire and forget execution.
        """
        if not self.__allow_retry:
            return

        if context.attached is None:
            raise ValueError("no tool assigned to context")

        if context.attached != self:
            raise ValueError(
                f"context is not for {self.name}, is instead for "
                f"{context.attached.name}"
            )

        output = context.output
        context.clear(executing=True)

        target_ctx = GlobalContextStore.get(output)
        if target_ctx is None:
            print(
                f"Warning: context {output} not found in "
                f"global store, can not retry from {context.id}"
            )
            context.output = output
        else:
            Thread(target=target_ctx.retry).start()

        return output
