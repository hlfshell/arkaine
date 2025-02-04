from __future__ import annotations

from threading import Event as ThreadEvent
from time import sleep
from typing import List

import pytest

from arkaine.tools.tools import Event, Tool
from arkaine.tools.context import Context


@pytest.fixture
def tool():
    """Provide a mock tool for testing"""

    class MockTool(Tool):
        def __init__(self):
            super().__init__(
                name="Mock Tool",
                description="A mock tool for testing",
                args=[],
                func=lambda: "mock result",
            )

    return MockTool()


@pytest.fixture
def context(tool):
    """Provide a fresh context before each test"""
    return Context(tool=tool, parent=None)


def test_context_initialization(context, tool):
    """Test that a new context is properly initialized"""
    assert context.tool == tool
    assert context._Context__parent is None
    assert context._Context__children == []
    assert context._Context__history == []
    assert context.status == "running"
    assert context.output is None


def test_child_context_creation(context, tool):
    """Test that child contexts are properly created and linked"""
    child = context.child_context(tool)

    # Child should be in parent's children list
    assert child in context._Context__children

    # Child should have correct tool and parent references
    assert child.tool == tool
    assert child._Context__parent == context


def test_event_broadcasting(context):
    """Test that events are properly broadcasted through the context chain"""
    received_events = []

    def listener(ctx, event):
        received_events.append((ctx, event))

    context.add_event_listener(listener, event_type="all")
    test_event = Event("test", "test_data")
    context.broadcast(test_event)

    # Give a small amount of time for the event to be processed
    sleep(0.1)

    assert len(received_events) == 1
    assert received_events[0][0] == context
    assert received_events[0][1] == test_event
    assert test_event in context._Context__history


def test_event_propagation(tool, context):
    """Test that events propagate from child to parent contexts"""
    parent_events: List[Event] = []
    child_events: List[Event] = []
    parent_received_ctx = []
    child_received_ctx = []

    def parent_listener(ctx, event: Event):
        parent_received_ctx.append(ctx)
        parent_events.append(event)

    def child_listener(ctx, event: Event):
        child_received_ctx.append(ctx)
        child_events.append(event)

    child = context.child_context(tool)

    context.add_event_listener(parent_listener)
    child.add_event_listener(child_listener)

    test_event = Event("test", "test_data")
    child.broadcast(test_event)

    # Give a small amount of time for the event to be processed
    sleep(0.1)

    # Event should be in both contexts
    assert len(parent_events) == 1
    assert len(child_events) == 1
    assert parent_events[0] == test_event
    assert child_events[0] == test_event
    assert parent_received_ctx[0] == child
    assert child_received_ctx[0] == child


def test_context_status(tool, context):
    """Test that context status properly reflects its state"""
    # Initial state should be running
    assert context.status == "running"

    # Test error state
    context.exception = Exception("test error")
    assert context.status == "error"

    # Create new context to test success state
    context = Context(tool)
    context.output = "test output"
    assert context.status == "complete"


def test_context_wait(context):
    """Test that context wait properly blocks until completion"""
    completion_event = ThreadEvent()

    def delayed_completion():
        sleep(0.1)
        context.output = "test output"
        completion_event.set()

    # Start a thread that will complete the context after a delay
    context._Context__executor.submit(delayed_completion)

    # Wait should block until the context is complete
    context.wait(timeout=0.2)

    assert completion_event.is_set()
    assert context.status == "complete"
    assert context.output == "test output"


def test_context_to_json(tool, context):
    """Test that context JSON serialization works correctly"""
    # Test empty context
    json_data = context.to_json()
    assert json_data["id"] is not None
    assert json_data["parent_id"] is None
    assert json_data["root_id"] == context.id
    assert json_data["tool_id"] is not None
    assert json_data["status"] == "running"
    assert json_data["output"] is None
    assert json_data["history"] == []
    assert json_data["children"] == []
    assert json_data["error"] is None

    # Test context with output
    context.output = "test output"
    json_data = context.to_json()
    assert json_data["status"] == "complete"
    assert json_data["output"] == "test output"

    # Test context with error
    context = Context(tool)
    test_error = ValueError("test error")
    context.exception = test_error
    json_data = context.to_json()
    assert json_data["status"] == "error"
    assert str(test_error) in json_data["error"]


def test_context_to_json_with_events(context):
    """Test that context JSON serialization properly handles events"""
    # Add a simple event
    test_event = Event("test", "test_data")
    context.broadcast(test_event)

    json_data = context.to_json()
    assert len(json_data["history"]) == 1
    event_json = json_data["history"][0]
    assert event_json["type"] == "test"
    assert event_json["data"] == "test_data"
    assert "timestamp" in event_json


def test_context_to_json_with_children(tool, context):
    """Test that context JSON serialization properly handles child contexts"""
    child = context.child_context(tool)
    child.output = "child output"

    json_data = context.to_json()
    assert len(json_data["children"]) == 1
    child_json = json_data["children"][0]
    assert child_json["output"] == "child output"
    assert child_json["status"] == "complete"


def test_context_to_json_complex_data(tool, context):
    """Test that context JSON serialization handles complex data types"""

    # Test with object that has to_json method
    class TestObject:
        def to_json(self):
            return {"test": "value"}

    context.broadcast(Event("test", TestObject()))
    json_data = context.to_json()
    event_json = json_data["history"][0]
    assert event_json["data"] == {"test": "value"}

    # Test with non-serializable object
    class NonSerializable:
        def __str__(self):
            return "string representation"

    context = Context(tool)  # Create new context
    context.broadcast(Event("test", NonSerializable()))
    json_data = context.to_json()
    event_json = json_data["history"][0]
    assert event_json["data"] == "string representation"


def test_instance_level_datastore(context):
    """Test instance-level data store functionality"""
    context["var"] = "instance value"
    assert context["var"] == "instance value"


def test_execution_level_datastore(context):
    """Test execution-level data store functionality"""
    context.x["var"] = "execution value"
    assert context.x["var"] == "execution value"


def test_debug_datastore(context):
    """Test debug data store functionality"""
    context.debug["var"] = "debug value"
    assert context.debug["var"] == "debug value"
