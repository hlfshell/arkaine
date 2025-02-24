import pytest
import time
from typing import Dict, Any

from arkaine.tools.context import Context
from arkaine.tools.tool import Tool, Argument
from arkaine.flow.parallel_list import ParallelList


@pytest.fixture
def base_tool():
    class SleeperTool(Tool):
        def __init__(self):
            super().__init__(
                name="sleeper",
                description="Sleeps for the specified duration",
                args=[Argument("duration", "Duration", "float", required=True)],
                func=self.execute,
            )

        def execute(self, context, duration: float):
            time.sleep(duration)
            return duration

    return SleeperTool()


@pytest.fixture
def error_tool():
    # A stateful error tool: it fails on the first attempt for even numbers,
    # then succeeds on a retry
    class SometimesFailsTool(Tool):
        def __init__(self):
            super().__init__(
                name="sometimes_fails",
                description="Fails on first attempt for even numbers",
                args=[Argument("value", "Value", "int", required=True)],
                func=self.execute,
            )

        def execute(self, context, value: int):
            p_ctx = context.parent
            if "attempts" not in p_ctx:
                p_ctx["attempts"] = {}
            if value % 2 == 0 and value not in p_ctx["attempts"]:
                p_ctx["attempts"][value] = 1
                raise ValueError("Even numbers fail")
            return value

    return SometimesFailsTool()


def test_parallel_list_initialization(base_tool):
    # Default initialization
    pl = ParallelList(base_tool)
    expected_name = f"{base_tool.name}::parallel_list"
    assert pl.name == expected_name
    assert "Executes" in pl.description

    # Since ParallelList now always uses a single input key (produced via extract_arguments),
    # verify that a dict containing list values is wrapped under "input".
    ctx = Context(pl)
    _, extracted = pl.extract_arguments((ctx, {"duration": [0.1]}), {})
    assert "input" in extracted
    assert extracted["input"] == [{"duration": 0.1}]

    # Test custom name and description (custom args are no longer supported)
    pl_custom = ParallelList(
        base_tool, name="custom_parallel", description="Custom description"
    )
    assert pl_custom.name == "custom_parallel"
    assert pl_custom.description == "Custom description"


def test_all_completion_strategy(base_tool):
    pl = ParallelList(base_tool, max_workers=4)
    context = Context(pl)
    # Pass input as a dict (format: dict-of-lists)
    inputs = {"duration": [0.1, 0.2]}
    results = pl(context, inputs)
    assert len(results) == 2
    assert 0.1 in results
    assert 0.2 in results


def test_any_completion_strategy(base_tool):
    pl = ParallelList(base_tool, completion_strategy="any", max_workers=2)
    context = Context(pl)
    inputs = {"duration": [0.5, 0.1]}
    results = pl(context, inputs)
    # Expect one completed result and one None due to cancellation
    assert 0.1 in results or 0.5 in results
    assert any(r is None for r in results)


def test_n_completion_strategy(base_tool):
    pl = ParallelList(
        base_tool, completion_strategy="n", completion_count=2, max_workers=3
    )
    context = Context(pl)
    inputs = {"duration": [0.3, 0.2, 0.1, 0.4]}
    results = pl(context, inputs)
    # Should have 2 completed tasks and 2 still None (unfinished)
    completed = sum(1 for r in results if r is not None)
    assert completed == 2


def test_error_handling_strategies(error_tool):
    # Fail-fast: should raise immediately when an error occurs.
    pl_fail = ParallelList(error_tool, error_strategy="fail")
    context_fail = Context(pl_fail)
    inputs_fail = {"value": [2, 3]}
    with pytest.raises(ValueError):
        pl_fail(context_fail, inputs_fail)

    # Ignore errors: should return a list with exceptions for failures.
    pl_ignore = ParallelList(error_tool, error_strategy="ignore")
    context_ignore = Context(pl_ignore)
    inputs_ignore = {"value": [2, 3]}
    results = pl_ignore(context_ignore, inputs_ignore)
    assert isinstance(results[0], ValueError)
    assert results[1] == 3


def test_input_extraction():
    class MultiplyTool(Tool):
        def __init__(self):
            super().__init__(
                name="multiply",
                description="Multiplies the input by 2",
                args=[Argument("value", "Value", "int", required=True)],
                func=self.execute,
            )

        def execute(self, context, value: int):
            return value * 2

    pl = ParallelList(MultiplyTool(), max_workers=2)
    context = Context(pl)
    results = pl(context, {"value": [1, 2, 3]})
    assert results == [2, 4, 6]


def test_retry_mechanism(error_tool):
    pl = ParallelList(
        error_tool, error_strategy="ignore", completion_strategy="all"
    )
    context = Context(pl)
    inputs = {"value": [2, 3, 4]}
    results = pl(context, inputs)
    # First run: even numbers (2 and 4) fail on their first attempt.
    assert [isinstance(r, Exception) for r in results] == [True, False, True]

    # Retry: only failed tasks get retried and should now succeed.
    retry_results = pl.retry(context)
    assert retry_results == [2, 3, 4]
    assert all(isinstance(r, int) for r in context["results"])


def test_majority_completion_strategy(base_tool):
    pl = ParallelList(base_tool, completion_strategy="majority", max_workers=4)
    context = Context(pl)
    # Use 6 inputs so that the current implementation (using floor division)
    # results in 6 // 2 = 3 tasks completing.
    inputs = {"duration": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]}
    results = pl(context, inputs)
    completed = sum(1 for r in results if r is not None)
    assert completed == 3


def test_edge_cases():
    # For a tool that requires a "value" parameter, ensure that an explicit empty list returns [].
    pl_empty = ParallelList(lambda ctx, value: value)
    results = pl_empty(Context(pl_empty), {"value": []})
    assert results == []

    # Test invalid completion strategy.
    with pytest.raises(ValueError):
        ParallelList(lambda ctx, value: None, completion_strategy="invalid")

    # Test missing completion_count when using completion_strategy "n".
    with pytest.raises(ValueError):
        ParallelList(lambda ctx, value: None, completion_strategy="n")


def test_invalid_argument_name(base_tool):
    """
    Test that if an invalid argument name is provided (i.e. not in the allowed names),
    a ValueError is raised.
    """
    pl = ParallelList(base_tool)
    context = Context(pl)
    with pytest.raises(ValueError, match="Invalid argument: speed"):
        pl(context, {"speed": [0.1]})


def test_mismatched_list_lengths():
    """
    Test that providing list arguments with mismatched lengths triggers an error.
    """

    class AdderTool(Tool):
        def __init__(self):
            super().__init__(
                name="adder",
                description="Adds two numbers",
                args=[
                    Argument("a", "First number", "int", required=True),
                    Argument("b", "Second number", "int", required=True),
                ],
                func=self.execute,
            )

        def execute(self, context, a: int, b: int):
            return a + b

    adder_tool = AdderTool()
    pl = ParallelList(adder_tool)
    context = Context(pl)
    with pytest.raises(
        ValueError, match="All arguments that are lists must be the same length"
    ):
        pl(context, {"a": [1, 2], "b": [3]})


def test_plural_argument_extraction():
    """
    Test that a pluralized key (e.g. 'values' instead of 'value') is correctly handled
    via the allowed names mapping.
    """

    class MultiplyTool(Tool):
        def __init__(self):
            super().__init__(
                name="multiply",
                description="Multiplies value by 2",
                args=[Argument("value", "Value", "int", required=True)],
                func=self.execute,
            )

        def execute(self, context, value: int):
            return value * 2

    multiply_tool = MultiplyTool()
    pl = ParallelList(multiply_tool)
    context = Context(pl)
    # Here we use 'values' (which should be plural-mapped to 'value')
    results = pl(context, {"values": [2, 4]})
    assert results == [4, 8]


def test_retry_no_failures(base_tool):
    """
    If there are no failed tasks, then calling retry should simply return the same results.
    """
    pl = ParallelList(
        base_tool,
        error_strategy="ignore",
        completion_strategy="all",
        max_workers=2,
    )
    context = Context(pl)
    inputs = {"duration": [0.1, 0.2, 0.3]}
    results = pl(context, inputs)
    # All tasks succeed so the results should be returned as is.
    assert results == [0.1, 0.2, 0.3]
    retry_results = pl.retry(context)
    assert retry_results == [0.1, 0.2, 0.3]


def test_retry_with_always_failing_tool():
    """
    Test the retry mechanism using a tool that always fails.
    After retry, the results should still be exceptions.
    """

    class AlwaysFailsTool(Tool):
        def __init__(self):
            super().__init__(
                name="always_fails",
                description="Always fails",
                args=[Argument("value", "Value", "int", required=True)],
                func=self.execute,
            )

        def execute(self, context, value: int):
            raise ValueError("I always fail")

    fails_tool = AlwaysFailsTool()
    pl = ParallelList(
        fails_tool, error_strategy="ignore", completion_strategy="all"
    )
    context = Context(pl)
    inputs = {"value": [10, 20]}
    results = pl(context, inputs)
    # First attempt: both should be exceptions.
    assert all(isinstance(r, Exception) for r in results)
    retry_results = pl.retry(context)
    # After retry, they are still failures.
    for r in retry_results:
        assert isinstance(r, Exception)
        assert "I always fail" in str(r)


def test_retry_wrong_context(base_tool):
    """
    Test that calling retry with a context not associated with the parallel list tool
    raises a ValueError.
    """
    pl = ParallelList(base_tool)

    # Create a dummy attachable object (different from the one used by pl)
    class DummyAttachable:
        @property
        def id(self) -> str:
            return "dummy"

        @property
        def name(self) -> str:
            return "DummyTool"

        @property
        def type(self) -> str:
            return "tool"

        @property
        def to_json(self) -> Dict[str, Any]:
            return {"id": self.id, "name": self.name, "type": self.type}

    dummy = DummyAttachable()
    wrong_context = Context(dummy)
    with pytest.raises(ValueError, match="context is not for"):
        pl.retry(wrong_context)
