import pytest

from arkaine.tools.context import Context
from arkaine.tools.tool import Tool, Argument
from arkaine.flow.dowhile import DoWhile


@pytest.fixture
def counter_tool():
    class CounterTool(Tool):
        def __init__(self):
            super().__init__(
                name="counter",
                description="Increments a counter in state",
                args=[
                    Argument(
                        "increment", "Increment amount", "int", required=True
                    )
                ],
                func=self.execute,
            )

        def execute(self, context, increment: int):
            ctx = context.parent
            ctx.init("count", 0)
            ctx.increment("count", increment)
            return ctx["count"]

    return CounterTool()


@pytest.fixture
def error_tool():
    class ErrorOnValueTool(Tool):
        def __init__(self):
            super().__init__(
                name="error_on_value",
                description="Raises error when count reaches specified value",
                args=[
                    Argument("value", "starting value", "int", required=True)
                ],
                func=self.execute,
            )

        def execute(self, context, value: int):
            ctx = context.parent
            if value >= 3 and "failed" not in ctx:
                ctx.init("failed", True)
                raise ValueError("Failed")
            else:
                return value + 1

    return ErrorOnValueTool()


def test_dowhile_basic_functionality(counter_tool):
    # Run until count reaches 5
    condition = lambda ctx, output: output >= 5
    prepare_args = lambda ctx, kwargs: {"increment": 1}

    do_while = DoWhile(
        counter_tool,
        condition=condition,
        prepare_args=prepare_args,
        name="count_to_five",
    )

    context = Context(do_while)
    result = do_while(context, 1)

    assert result == 5
    assert context["iteration"] == 5  # Started at 1, took 5 steps
    assert len(context["args"]) == 5
    assert all(arg == {"increment": 1} for arg in context["args"])


def test_dowhile_max_iterations(counter_tool):
    condition = lambda ctx, output: output >= 10
    prepare_args = lambda ctx, kwargs: {"increment": 1}

    do_while = DoWhile(
        counter_tool,
        condition=condition,
        prepare_args=prepare_args,
        max_iterations=3,
    )

    context = Context(do_while)
    with pytest.raises(ValueError, match="max iterations surpassed"):
        output = do_while(context, 1)

    assert context["iteration"] == 4


def test_dowhile_format_output(counter_tool):
    condition = lambda ctx, output: output >= 5
    prepare_args = lambda ctx, kwargs: {"increment": 1}
    format_output = lambda ctx, output: output * 2

    do_while = DoWhile(
        counter_tool,
        condition=condition,
        prepare_args=prepare_args,
        format_output=format_output,
    )

    context = Context(do_while)
    result = do_while(context, 1)

    assert result == 10


def test_dowhile_retry_mechanism(error_tool):
    condition = lambda ctx, output: output >= 10
    prepare_args = lambda ctx, kwargs: {"value": ctx["outputs"][-1] + 1}

    do_while = DoWhile(
        error_tool,
        condition=condition,
        prepare_args=prepare_args,
    )

    context = Context(do_while)

    with pytest.raises(ValueError, match="Failed"):
        do_while(context, 1)

    assert context["iteration"] == 2

    output = do_while.retry(context)

    assert context["iteration"] == 6
    assert output == 10


def test_dowhile_retry_wrong_context(counter_tool):
    condition = lambda ctx, output: output >= 5
    prepare_args = lambda ctx, kwargs: {"increment": 1}

    do_while = DoWhile(
        counter_tool,
        condition=condition,
        prepare_args=prepare_args,
    )

    wrong_context = Context(counter_tool)  # Context for wrong tool

    with pytest.raises(ValueError, match="context is not for"):
        do_while.retry(wrong_context)


def test_dowhile_dynamic_args(counter_tool):
    condition = lambda ctx, output: output >= 5
    # Increment grows with each iteration
    prepare_args = lambda ctx, kwargs: {"increment": ctx["iteration"] + 1}

    do_while = DoWhile(
        counter_tool,
        condition=condition,
        prepare_args=prepare_args,
    )

    context = Context(do_while)
    result = do_while(context, 1)

    assert result >= 5
    assert context["args"] == [
        {"increment": 1},
        {"increment": 2},
        {"increment": 3},
    ]


def test_dowhile_toolify_function():
    def simple_func(context, value: int) -> int:
        return value + 1

    condition = lambda ctx, output: output >= 3
    prepare_args = lambda ctx, kwargs: {"value": ctx["outputs"][-1] + 1}

    do_while = DoWhile(
        simple_func,
        condition=condition,
        prepare_args=prepare_args,
    )

    context = Context(do_while)
    result = do_while(context, 1)

    assert result == 4
