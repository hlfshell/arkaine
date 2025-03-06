from __future__ import annotations

import inspect
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, List, Optional
from uuid import uuid4

from arkaine.internal.registrar import Registrar
from arkaine.tools.argument import Argument, InvalidArgumentException
from arkaine.tools.context import Context
from arkaine.tools.events import (
    ToolCalled,
    ToolReturn,
)
from arkaine.tools.example import Example
from arkaine.tools.result import Result
from arkaine.tools.types import ToolArguments


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        args: List[Argument],
        func: Callable,
        examples: List[Example] = [],
        id: Optional[str] = None,
        result: Optional[Result] = None,
    ):
        self.__id = id or str(uuid4())
        self.name = name
        self.description = description
        self.args = args
        self.func = func
        self.examples = examples
        self._on_call_listeners: List[Callable[[Tool, Context], None]] = []
        self.result = result
        self._executor = ThreadPoolExecutor()
        self.__type = "tool"

        Registrar.register(self)

    def __del__(self):
        if self._executor:
            self._executor.shutdown(wait=False)

    @property
    def id(self) -> str:
        return self.__id

    @property
    def type(self) -> str:
        return self.__type

    @property
    def tname(self) -> str:
        """
        Short for tool name, it removes wrapper and modifying monikers
        by only grabbing the name prior to any "::"
        """
        return self.name.split("::")[0]

    def get_context(self) -> Context:
        """
        get_context returns a blank context for use with this tool.
        """
        return Context(self)

    def _init_context_(self, context: Optional[Context], kwargs) -> Context:
        if context is None:
            ctx = Context(self)
        else:
            ctx = context

        if ctx.executing:
            ctx = context.child_context(self)
            ctx.executing = True
        else:
            if not ctx.attached:
                ctx.attached = self
            ctx.executing = True

        ctx.args = kwargs
        ctx.broadcast(ToolCalled(kwargs))

        for listener in self._on_call_listeners:
            self._executor.submit(listener, self, ctx)

        return ctx

    def invoke(self, context: Context, **kwargs) -> Any:
        params = inspect.signature(self.func).parameters
        if "context" in params:
            if params["context"].kind == inspect.Parameter.VAR_POSITIONAL:
                return self.func(context, **kwargs)
            else:
                return self.func(context=context, **kwargs)
        else:
            return self.func(**kwargs)

    def extract_arguments(self, args, kwargs):
        # Extract context if present as first argument
        context = None
        if args and isinstance(args[0], Context):
            context = args[0]
            args = args[1:]  # Remove context from args

        # Handle single dict argument case
        if len(args) == 1 and not kwargs and isinstance(args[0], dict):
            kwargs = args[0]
            args = ()

        # Map remaining positional args to their parameter names
        tool_args = [arg.name for arg in self.args]
        for i, value in enumerate(args):
            if i < len(tool_args):
                if tool_args[i] in kwargs:
                    raise TypeError(
                        f"Got multiple values for argument '{tool_args[i]}'"
                    )
                kwargs[tool_args[i]] = value

        # Check to see if context is in the kwargs
        if "context" in kwargs:
            if context is not None:
                raise ValueError("context passed twice")
            context = kwargs.pop("context")

        return context, kwargs

    def __call__(self, *args, **kwargs) -> Any:
        context, kwargs = self.extract_arguments(args, kwargs)

        with self._init_context_(context, kwargs) as ctx:
            kwargs = self.fulfill_defaults(kwargs)
            self.check_arguments(kwargs)
            ctx.broadcast(ToolCalled(self.name))

            results = self.invoke(ctx, **kwargs)
            ctx.output = results
            ctx.broadcast(ToolReturn(results))
            return results

    def async_call(self, *args, **kwargs) -> Context:
        context, kwargs = self.extract_arguments(args, kwargs)

        if context is None:
            context = Context()
        else:
            # If we are passed a context, we need to determine if its a new
            # context or if it is an existing one that means we need to create
            # a child context. We don't mark it as executing so that the call
            # itself can do this. If it isn't executing we'll just continue
            # using the current context.
            if context.executing:
                context = context.child_context(self)

        def wrapped_call(context: Context, **kwargs):
            try:
                self.__call__(context, **kwargs)
            except Exception as e:
                context.exception = e

        # Use the existing thread pool instead of creating raw threads
        self._executor.submit(wrapped_call, context, **kwargs)

        return context

    def retry(self, context: Context) -> Any:
        """
        Retry the tool call. This function is expected to be overwritten by
        implementing class tools that have more complicated logic to make
        retrying more effective.
        """

        # Ensure that the context passed is in fact a context for this tool
        if context.attached is None:
            raise ValueError(f"no tool assigned to context")
        elif context.attached != self:
            raise ValueError(
                f"context is not for {self.name}, is instead for "
                f"{context.attached.name}"
            )

        # Clear the context for re-running.
        args = context.args
        context.clear()

        # Retry the tool call
        return self.__call__(context, args)

    def examples_text(
        self, example_format: Optional[Callable[[Example], str]] = None
    ) -> List[str]:
        if not example_format:
            example_format = Example.ExampleBlock

        return [example_format(self.name, example) for example in self.examples]

    def __str__(self) -> str:
        return Tool.stringify(self)

    def __repr__(self) -> str:
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
                tool_name=self.name,
                missing_required_args=missing_args,
                extraneous_args=extraneous_args,
            )

    @staticmethod
    def stringify(tool: Tool) -> str:
        # Start with the tool name and description
        output = f"> Tool Name: {tool.name}\n"

        # Break the long line into multiple lines
        args_str = ", ".join([f"{arg.name}: {arg.type}" for arg in tool.args])
        output += f"Tool Description: {tool.name}({args_str})\n\n"

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

    def add_on_call_listener(self, listener: Callable[[Tool, Context], None]):
        self._on_call_listeners.append(listener)

    def to_json(self) -> dict:
        return {
            "id": self.__id,
            "name": self.name,
            "description": self.description,
            "type": self.__type,
            "args": [arg.to_json() for arg in self.args],
            "examples": [example.to_json() for example in self.examples],
            "result": self.result.to_json() if self.result else None,
        }
