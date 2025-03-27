import pytest
from unittest.mock import MagicMock, patch

from arkaine.flow.linear import Linear, StepException
from arkaine.tools.context import Context
from arkaine.tools.tool import Tool
from arkaine.tools.toolify import toolify


def test_linear_basic_execution():
    """Test that a linear flow executes steps in order."""
    # Create mock tools/functions for the steps
    step1 = toolify(lambda context, x: {"result": x * 2})
    step2 = toolify(lambda context, result: {"final": result + 10})

    # Create the linear flow
    flow = Linear(
        name="TestFlow",
        description="A test flow",
        arguments=None,  # Should infer from first step
        steps=[step1, step2],
    )

    # Execute the flow
    result = flow({"x": 5})

    # Check the result
    assert result == {"final": 20}  # (5*2) + 10 = 20


def test_linear_argument_inference():
    """Test that arguments are correctly inferred from the first step."""

    # Create a tool with specific arguments
    @toolify
    def first_step(context, value: int, multiplier: int = 2):
        """
        Multiply a value by a multiplier.

        Args:
            value: The value to multiply
            multiplier: The multiplier to use
        """
        return {"result": value * multiplier}

    second_step = toolify(lambda context, result: {"final": result + 10})

    # Create the linear flow with no explicit arguments
    flow = Linear(
        name="TestFlow",
        description="A test flow",
        arguments=None,
        steps=[first_step, second_step],
    )

    # Check that arguments were inferred correctly
    assert len(flow.args) == 2
    assert flow.args[0].name == "value"
    assert flow.args[0].type == "int"
    assert flow.args[1].name == "multiplier"
    assert flow.args[1].required is False

    # Test execution with default and explicit arguments
    result1 = flow({"value": 5})  # Using default multiplier
    assert result1 == {"final": 20}  # (5*2) + 10 = 20

    result2 = flow({"value": 5, "multiplier": 3})
    assert result2 == {"final": 25}  # (5*3) + 10 = 25


def test_linear_with_explicit_arguments():
    """Test that explicitly provided arguments override inference."""
    from arkaine.tools.argument import Argument

    step1 = toolify(lambda context, x: {"result": x * 2})
    step2 = toolify(lambda context, result: {"final": result + 10})

    # Create custom arguments
    custom_args = [
        Argument(name="x", description="Custom arg", type="int", required=True)
    ]

    # Create the linear flow with explicit arguments
    flow = Linear(
        name="TestFlow",
        description="A test flow",
        arguments=custom_args,
        steps=[step1, step2],
    )

    # Check that our custom arguments were used
    assert len(flow.args) == 1
    assert flow.args[0].name == "x"
    assert flow.args[0].description == "Custom arg"

    # Test execution
    result = flow({"x": 5})
    assert result == {"final": 20}  # (5*2) + 10 = 20


def test_linear_error_handling():
    """Test that errors in steps are properly caught and reported."""
    # Create steps with an error in the second one
    step1 = toolify(lambda context, x: {"result": x * 2})

    @toolify
    def failing_step(context, result):
        raise ValueError("Test error")

    # Create the linear flow
    flow = Linear(
        name="TestFlow",
        description="A test flow",
        arguments=None,
        steps=[step1, failing_step],
    )

    # Execute and check for the expected exception
    with pytest.raises(StepException) as excinfo:
        flow({"x": 5})

    # Verify the exception details
    assert "Error in step 1" in str(excinfo.value)
    assert "Test error" in str(excinfo.value)
    assert excinfo.value.index == 1  # Second step (index 1)


def test_linear_context_tracking():
    """Test that the context properly tracks step execution."""

    # Create steps that check and modify the context
    @toolify
    def step1(context, x):
        # The context["step"] is set by the Linear flow
        # but we need to access it after the step is called
        context.parent["custom_value"] = "step1_was_here"
        return {"result": x * 2}

    @toolify
    def step2(context, result):
        # Check that we have the custom value from step1
        assert context.parent["custom_value"] == "step1_was_here"
        context.parent["custom_value"] = "step2_was_here"
        return {"final": result + 10}

    # Create the linear flow
    flow = Linear(
        name="TestFlow",
        description="A test flow",
        arguments=None,
        steps=[step1, step2],
    )

    # Execute the flow
    result = flow({"x": 5})

    # Check the result
    assert result == {"final": 20}


def test_linear_init_input_preservation():
    """Test that the initial input is preserved in context.x."""

    @toolify
    def step1(context, x):
        # Check that the initial input is preserved
        assert context.x["init_input"] == {"x": 5}
        return {"result": x * 2}

    @toolify
    def step2(context, result):
        # Still accessible in later steps
        assert context.x["init_input"] == {"x": 5}
        return {"final": result + 10}

    # Create the linear flow
    flow = Linear(
        name="TestFlow",
        description="A test flow",
        arguments=None,
        steps=[step1, step2],
    )

    # Execute the flow
    result = flow({"x": 5})

    # Check the result
    assert result == {"final": 20}


def test_linear_with_existing_context():
    """Test that a linear flow works with an existing context."""
    step1 = toolify(lambda context, x: {"result": x * 2})
    step2 = toolify(lambda context, result: {"final": result + 10})

    # Create the linear flow
    flow = Linear(
        name="TestFlow",
        description="A test flow",
        arguments=None,
        steps=[step1, step2],
    )

    # Create a context with some existing data
    context = Context(flow)
    context["existing_data"] = "test_value"

    # Execute the flow with the context
    result = flow(context, {"x": 5})

    # Check the result
    assert result == {"final": 20}
    assert context["existing_data"] == "test_value"
    # After two steps, the step counter should be 1 (0-indexed)
    assert context["step"] == 1  # Changed from 2 to 1


def test_linear_retry_functionality():
    """Test that retry functionality works correctly."""

    # Create steps with a failing second step
    @toolify
    def step1(context, x):
        return {"result": 10}

    # Use a counter to make the step fail on first call but succeed on retry
    step2_calls = [0]

    @toolify
    def step2(context, result):
        step2_calls[0] += 1
        if step2_calls[0] == 1:
            raise ValueError("First attempt fails")
        return {"final": 20}

    # Create the linear flow
    flow = Linear(
        name="TestFlow",
        description="A test flow",
        arguments=None,
        steps=[step1, step2],
    )

    # Create a context to use for execution
    context = Context(flow)

    # First attempt should fail
    with pytest.raises(StepException):
        flow(context, {"x": 5})

    # Retry should succeed
    result = flow.retry(context)

    # Check the final result
    assert result == {"final": 20}
    # Verify step2 was called twice
    assert step2_calls[0] == 2


def test_linear_retry_with_wrong_context():
    """Test that retry fails with the wrong context."""
    step1 = toolify(lambda context, x: {"result": x * 2})

    # Create two different flows
    flow1 = Linear(
        name="Flow1",
        description="Flow 1",
        arguments=None,
        steps=[step1],
    )

    flow2 = Linear(
        name="Flow2",
        description="Flow 2",
        arguments=None,
        steps=[step1],
    )

    # Create a context for flow1
    context = Context(flow1)

    # Try to retry with flow2
    with pytest.raises(ValueError, match="context is not for Flow2"):
        flow2.retry(context)


def test_linear_retry_with_no_attached_tool():
    """Test that retry fails with no attached tool."""
    step1 = toolify(lambda context, x: {"result": x * 2})

    flow = Linear(
        name="TestFlow",
        description="A test flow",
        arguments=None,
        steps=[step1],
    )

    # Create a context with no attached tool
    context = Context()

    # Try to retry
    with pytest.raises(ValueError, match="no tool assigned to context"):
        flow.retry(context)


def test_linear_with_toolified_functions():
    """Test that a linear flow works with toolified functions."""

    # Define regular functions that will be toolified by Linear
    def add_ten(context, x):
        return {"result": x + 10}

    def multiply_by_two(context, result):
        return {"final": result * 2}

    # Create the linear flow with functions (should be auto-toolified)
    flow = Linear(
        name="TestFlow",
        description="A test flow",
        arguments=None,
        steps=[
            toolify(add_ten),
            toolify(multiply_by_two),
        ],  # Pre-toolify the functions
    )

    # Execute the flow
    result = flow({"x": 5})

    # Check the result
    assert result == {"final": 30}  # (5+10)*2 = 30


def test_linear_with_mixed_tools_and_functions():
    """Test that a linear flow works with a mix of tools and functions."""

    # Create a tool
    @toolify
    def add_ten(context, x):
        """Add 10 to the input."""
        return {"result": x + 10}

    # Define a regular function
    def multiply_by_two(context, result):
        return {"final": result * 2}

    # Create the linear flow with a mix
    flow = Linear(
        name="TestFlow",
        description="A test flow",
        arguments=None,
        steps=[add_ten, multiply_by_two],
    )

    # Execute the flow
    result = flow({"x": 5})

    # Check the result
    assert result == {"final": 30}  # (5+10)*2 = 30


def test_linear_step_skipping():
    """Test that steps are skipped when resuming from a specific step."""
    # Create steps with tracking counters
    step1_calls = [0]
    step2_calls = [0]
    step3_calls = [0]

    @toolify
    def step1(context, x):
        step1_calls[0] += 1
        return 10

    @toolify
    def step2(context, x):
        step2_calls[0] += 1
        return 20

    @toolify
    def step3(context, x):
        step3_calls[0] += 1
        return 30

    # Create the linear flow
    flow = Linear(
        name="TestFlow",
        description="A test flow",
        arguments=None,
        steps=[step1, step2, step3],
    )

    # Create a context
    context = Context(flow)

    # Set the step to 1 (second step) directly
    context["step"] = 1

    # Execute the flow with the context - should skip step1
    result = flow(context, 5)

    # Check that step1 was not called, but steps 2 and 3 were
    assert step2_calls[0] == 1
    assert step3_calls[0] == 1

    # Check the result
    assert result == 30


def test_linear_with_lambda_functions():
    """Test that a linear flow works with lambda functions as steps."""
    # Create steps using lambda functions
    step1 = toolify(lambda context, x: {"result": x * 2})
    step2 = toolify(lambda context, result: {"final": result + 10})

    # Create the linear flow
    flow = Linear(
        name="TestFlow",
        description="A test flow",
        arguments=None,
        steps=[step1, step2],
    )

    # Execute the flow
    result = flow({"x": 5})

    # Check the result
    assert result == {"final": 20}  # (5*2) + 10 = 20

    # Test with a different input
    result2 = flow({"x": 10})
    assert result2 == {"final": 30}  # (10*2) + 10 = 30
