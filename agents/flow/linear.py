import inspect
from typing import Any, Callable, List, Optional, Union

from agents.tools.events import ToolReturn
from agents.tools.tool import Argument, Context, Example, Tool


class Linear(Tool):
    """
    A tool that chains multiple tools or functions together in a sequential
    pipeline.

    This tool executes a series of tools or functions in sequence, with
    optional formatting between steps. Each tool's or function's output becomes
    the input for the next in the chain. Optional formatters can transform the
    output of each step before it's passed to the next, including the final
    step.

    Args:
        name (str): The name of the linear chain tool

        description (str): A description of what the chain accomplishes

        arguments (List[Argument]): List of arguments required by the chain

        examples (List[Example]): Example usage scenarios for the chain

        steps (List[Union[Tool, Callable[[Context, Any], Any]]]): Ordered list
            of tools or functions to execute in sequence

        formatters (List[Optional[Callable[[Context, Any], Any]]]): List of
            formatter functions that can transform the output between steps.
            Should be the same length as steps or one additional. Use None for
            steps that don't need formatting. Typically you want to format the
            output to ensure it's a dict of variables for the next tool. In
            terms of indexing, the formatter is called PRIOR to the
            equivalently indexed step. If the index is +1 of the size of the
            steps list, this final formatter is called AFTER the last step and
            returned.

    Note:
        If using functions instead of tools, ensure the context is passed and
        utilized correctly, and that the function returns a Context as well.
    """

    def __init__(
        self,
        name: str,
        description: str,
        arguments: List[Argument],
        steps: List[Union[Tool, Callable[[Context, Any], Any]]],
        examples: List[Example] = [],
    ):
        self.steps = steps

        super().__init__(
            name=name,
            args=arguments,
            description=description,
            func=self.invoke,
            examples=examples,
        )

    def invoke(self, context: Context, **kwargs) -> Any:
        output = kwargs
        # We save the initial kwargs to the root context
        # so that tools or functions within the chain
        # can access them for reference.
        context.x["init_input"] = output

        if not context["args"]:
            context["args"] = {}

        # The start index is what tools we're going to call.
        # We start with 0, unless this context is a retry/resume
        # at which point we back it up one go and then start
        # from there.
        start_index = (
            0 if "step_index" in context else context["step_index"] - 1
        )
        # Similarly, we load up the last input, or use the passed in
        # if this is a normal call.
        output = (
            kwargs
            if start_index not in context["args"]
            else context["args"][start_index]
        )

        for index, step in enumerate(self.steps):
            # For resumes, we ignore prior steps
            if index < start_index:
                continue

            context["step_index"] = index
            context["args"][index] = output

            if isinstance(step, Tool):
                output = step(context=context, **output)
            else:
                with self._init_context_(context, output) as ctx:
                    # Determine if we should expand the output
                    expand = False
                    if isinstance(output, dict):
                        params = inspect.signature(step).parameters.keys()
                        if set(params).issubset(set(output.keys())):
                            expand = True

                    # Does the step have a context keyword?
                    if "context" in inspect.signature(step).parameters:
                        if expand:
                            output = step(context=ctx, **output)
                        else:
                            output = step(ctx, output)
                    else:
                        if expand:
                            output = step(**output)
                        else:
                            output = step(output)

                    ctx.output = output
                    ctx.broadcast(ToolReturn(output))

        return output

    def rerun(self, context: Context):
        """
        Rerun a context from this point forward. Note that if the context
        specified is part of a larger tree of contexts,
        """
        if not self.can_resume:
            raise ValueError("This context cannot rerun - clear it first")

        return self.__call__(context, context.kwargs)
