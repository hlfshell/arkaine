import io
from typing import TextIO

import pytest

from arkaine.events import AgentCalled, AgentLLMResponse, AgentPrompt
from arkaine.logging.logger import Colors, Logger
from arkaine.tools.events import ToolCalled, ToolException, ToolReturn
from arkaine.tools.tool import Argument, Context, Tool


class MockTool(Tool):
    def __init__(self, name: str = "mock_tool"):
        super().__init__(
            name=name,
            description="A mock tool for testing",
            args=[
                Argument(
                    name="test_arg",
                    description="A test argument",
                    type="string",
                    required=True,
                )
            ],
            func=lambda: None,
        )


@pytest.fixture
def output_stream() -> TextIO:
    return io.StringIO()


@pytest.fixture
def logger(output_stream: TextIO) -> Logger:
    return Logger(output_stream=output_stream, use_colors=True)


@pytest.fixture
def tool() -> Tool:
    return MockTool()


@pytest.fixture
def context(tool: Tool) -> Context:
    return Context(tool=tool)


def test_logger_initialization():
    """Test logger initializes with default values"""
    logger = Logger()
    assert logger.use_colors is True
    assert logger.indent_size == 2


def test_logger_color_disabled(output_stream: TextIO):
    """Test logger respects color disable flag"""
    logger = Logger(output_stream=output_stream, use_colors=False)
    context = Context(MockTool())

    event = ToolCalled({"arg": "value"})
    logger.log_event(context, event)

    output = output_stream.getvalue()
    assert Colors.RED not in output
    assert Colors.GREEN not in output
    assert Colors.RESET not in output


def test_tool_event_logging(
    logger: Logger, context: Context, output_stream: TextIO
):
    """Test logging of tool-related events"""
    # Test tool called event
    tool_called = ToolCalled({"test_arg": "value"})
    logger.log_event(context, tool_called)

    # Test tool return event
    tool_return = ToolReturn("test result")
    logger.log_event(context, tool_return)

    output = output_stream.getvalue()
    assert "test_arg" in output
    assert "value" in output
    assert "test result" in output


def test_agent_event_logging(
    logger: Logger, context: Context, output_stream: TextIO
):
    """Test logging of agent-related events"""
    # Test agent called event
    agent_called = AgentCalled({"test_arg": "value"})
    logger.log_event(context, agent_called)

    # Test agent prompt event
    agent_prompt = AgentPrompt("test prompt")
    logger.log_event(context, agent_prompt)

    # Test agent LLM response event
    agent_response = AgentLLMResponse("test response")
    logger.log_event(context, agent_response)

    output = output_stream.getvalue()
    assert "test prompt" in output
    assert "test response" in output


def test_exception_logging(
    logger: Logger, context: Context, output_stream: TextIO
):
    """Test logging of exceptions"""
    exception = ValueError("Test error")
    event = ToolException(exception)
    logger.log_event(context, event)

    output = output_stream.getvalue()
    assert "Test error" in output
    assert Colors.RED in output


def test_json_formatting(
    logger: Logger, context: Context, output_stream: TextIO
):
    """Test JSON formatting of complex data structures"""
    data = {"key": "value", "nested": {"inner": "data"}}
    event = ToolReturn(data)
    logger.log_event(context, event)

    output = output_stream.getvalue()
    assert '"key": "value"' in output
    assert '"nested"' in output
    assert '"inner": "data"' in output


def test_tool_attachment(logger: Logger, tool: Tool):
    """Test attaching a tool to the logger"""
    logger.attach_tool(tool)

    # To verify a tool is attached, I should be able to determine
    # that it was called
    context = Context(tool)
    tool_called = ToolCalled({})
    logger.log_event(context, tool_called)

    output = logger.output_stream.getvalue()
    assert tool.id in output


def test_indentation(logger: Logger, context: Context, output_stream: TextIO):
    """Test proper indentation of multi-line output"""
    data = {"key1": "value1", "key2": {"nested": "value2"}}
    event = ToolReturn(data)
    logger.log_event(context, event)

    output = output_stream.getvalue()
    lines = output.split("\n")

    # Make assertion more flexible to handle different indentation styles
    assert any(
        line.strip().startswith('"') and line.startswith(" ") for line in lines
    ), "Expected to find indented JSON lines"


def test_thread_safety(logger: Logger, context: Context):
    """Test thread-safe logging with multiple concurrent events"""
    import threading
    import time

    def log_events():
        for i in range(5):
            event = ToolCalled({"count": i})
            logger.log_event(context, event)
            time.sleep(0.01)

    threads = [threading.Thread(target=log_events) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    output = logger.output_stream.getvalue()
    # Verify all events were logged (5 events * 3 threads = 15 events)
    assert output.count("mock_tool") == 15
