import pytest

from arkaine.tools.tool import (
    Argument,
    Context,
    Example,
    InvalidArgumentException,
    Tool,
)


# Test fixtures
@pytest.fixture
def simple_argument():
    return Argument(
        name="test_arg",
        description="A test argument",
        type="string",
        required=True,
    )


@pytest.fixture
def optional_argument():
    return Argument(
        name="optional_arg",
        description="An optional argument",
        type="int",
        required=False,
        default="42",
    )


@pytest.fixture
def example():
    return Example(
        name="test_example",
        args={"arg1": "value1", "arg2": "value2"},
        output="example output",
        description="A test example",
        explanation="This is how it works",
    )


@pytest.fixture
def mock_tool():
    def mock_function(**kwargs) -> str:
        return f"Called with {kwargs}"

    return Tool(
        name="mock_tool",
        description="A mock tool for testing",
        args=[
            Argument(
                "required_arg", "Required argument", "string", required=True
            ),
            Argument(
                "optional_arg",
                "Optional argument",
                "string",
                required=False,
                default="default",
            ),
        ],
        func=mock_function,
    )


# Argument Tests
def test_argument_initialization(simple_argument):
    """Test that Arguments are properly initialized"""
    assert simple_argument.name == "test_arg"
    assert simple_argument.description == "A test argument"
    assert simple_argument.type == "string"
    assert simple_argument.required is True
    assert simple_argument.default is None


def test_argument_string_format(simple_argument, optional_argument):
    """Test argument string formatting"""
    # Required argument without default
    assert (
        str(simple_argument)
        == "test_arg - string - Required: True - A test argument"
    )

    # Optional argument with default
    expected = (
        "optional_arg - int - Required: False - Default: 42 - "
        "An optional argument"
    )
    assert str(optional_argument) == expected


# Example Tests
def test_example_initialization(example):
    """Test that Examples are properly initialized"""
    assert example.name == "test_example"
    assert example.args == {"arg1": "value1", "arg2": "value2"}
    assert example.output == "example output"
    assert example.description == "A test example"
    assert example.explanation == "This is how it works"


def test_example_block_format(example):
    """Test Example block formatting"""
    block = Example.ExampleBlock("test_function", example)
    expected = (
        "A test example\n"
        "test_function(arg1=value1, arg2=value2)\n"
        "Returns:\nexample output\n"
        "Explanation: This is how it works"
    )
    assert block == expected


# Tool Tests
def test_tool_initialization(mock_tool):
    """Test that Tools are properly initialized"""
    assert mock_tool.name == "mock_tool"
    assert len(mock_tool.args) == 2
    assert mock_tool.args[0].name == "required_arg"
    assert mock_tool.args[1].name == "optional_arg"


def test_tool_call_with_valid_args(mock_tool):
    """Test tool execution with valid arguments"""
    result = mock_tool(required_arg="test")
    assert (
        result
        == "Called with {'required_arg': 'test', 'optional_arg': 'default'}"
    )


def test_tool_call_with_context(mock_tool):
    """Test tool execution with context"""
    ctx = Context(mock_tool)
    result = mock_tool(context=ctx, required_arg="test")
    assert (
        result
        == "Called with {'required_arg': 'test', 'optional_arg': 'default'}"
    )
    assert ctx.output == result


def test_tool_missing_required_arg(mock_tool):
    """Test tool execution with missing required argument"""
    with pytest.raises(InvalidArgumentException) as exc_info:
        mock_tool()
    assert "missing required arguments" in str(exc_info.value).lower()
    assert "required_arg" in str(exc_info.value)


def test_tool_extraneous_arg(mock_tool):
    """Test tool execution with extraneous argument"""
    with pytest.raises(InvalidArgumentException) as exc_info:
        mock_tool(required_arg="test", invalid_arg="value")
    assert "extraneous arguments" in str(exc_info.value).lower()
    assert "invalid_arg" in str(exc_info.value)


def test_tool_fulfill_defaults(mock_tool):
    """Test default argument fulfillment"""
    args = mock_tool.fulfill_defaults({"required_arg": "test"})
    assert args == {"required_arg": "test", "optional_arg": "default"}


def test_tool_string_format(mock_tool):
    """Test tool string formatting"""
    tool_str = str(mock_tool)
    assert "> Tool Name: mock_tool" in tool_str
    assert "Tool Description: mock_tool" in tool_str
    assert "required_arg: string" in tool_str
    assert "optional_arg: string" in tool_str


def test_tool_exception_handling(mock_tool):
    """Test tool exception handling with context"""

    def failing_function(**kwargs):
        raise ValueError("Test error")

    failing_tool = Tool(
        name="failing_tool",
        description="A tool that fails",
        args=[],
        func=failing_function,
    )

    ctx = Context(mock_tool)
    with pytest.raises(ValueError):
        failing_tool(context=ctx)
    assert ctx.status == "error"
