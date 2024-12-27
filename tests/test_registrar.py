from typing import List, Optional
from unittest.mock import Mock

import pytest

from arkaine.registrar.registrar import Registrar
from arkaine.tools.tool import Argument, Context, Tool


def dummy_tool_func(**kwargs):
    return "test result"


@pytest.fixture
def mock_tool():
    tool = Tool(
        name="test_tool",
        description="A test tool",
        args=[
            Argument(
                name="test_arg",
                description="A test argument",
                type="string",
                required=True,
            )
        ],
        func=dummy_tool_func,
    )
    return tool


def test_registrar_cannot_be_instantiated():
    with pytest.raises(ValueError, match="Registrar cannot be instantiated"):
        Registrar()


def test_tool_registration(mock_tool):
    # Clear any existing tools
    Registrar._tools.clear()

    # Register the tool
    Registrar.register(mock_tool)

    # Verify the tool was registered
    assert mock_tool.id in Registrar._tools
    assert Registrar._tools[mock_tool.id] == mock_tool


def test_duplicate_tool_registration(mock_tool):
    # Clear any existing tools
    Registrar._tools.clear()

    # Register the same tool twice
    Registrar.register(mock_tool)
    Registrar.register(mock_tool)

    # Verify the tool is still registered only once
    assert len(Registrar._tools) == 1
    assert mock_tool.id in Registrar._tools


def test_tool_call_notification():
    # Clear any existing tools and listeners
    Registrar._tools.clear()
    Registrar._on_tool_call_listeners.clear()

    # Create a mock listener
    mock_listener = Mock()
    Registrar._on_tool_call_listeners.append(mock_listener)

    # Create and register a tool
    tool = Tool(
        name="test_tool", description="A test tool", args=[], func=lambda: None
    )

    # Enable the registrar
    Registrar.enable()

    # Create a context and trigger the tool call notification
    ctx = Context(tool)
    Registrar._on_tool_call(ctx)

    # Verify the listener was called with the context
    mock_listener.assert_called_once()
    assert mock_listener.call_args[0][0] == ctx


def test_enable_disable():
    # Test enable
    Registrar.enable()
    assert Registrar.is_enabled() is True

    # Test disable
    Registrar.disable()
    assert Registrar.is_enabled() is False


def test_set_auto_registry():
    # Test setting auto registry to True
    Registrar.set_auto_registry(True)
    assert Registrar.is_enabled() is True

    # Test setting auto registry to False
    Registrar.set_auto_registry(False)
    assert Registrar.is_enabled() is False
