from threading import Event as ThreadEvent
from time import sleep
from typing import List

import pytest

from agents.context import Context, Event


@pytest.fixture
def context():
    """Provide a fresh context before each test"""
    return Context()


def test_context_initialization(context):
    """Test that a new context is properly initialized"""
    assert context._Context__parent_id is None
    assert context._Context__children == []
    assert context._Context__history == []
    assert context.status == "running"
    assert context.output is None


def test_child_context_creation(context):
    """Test that child contexts are properly created and linked"""
    child = context.child_context()

    # Child should be in parent's children list
    assert child in context._Context__children

    # Child should have different ID than parent
    assert child._Context__id != context._Context__id


def test_event_broadcasting(context):
    """Test that events are properly broadcasted through the context chain"""
    received_events: List[Event] = []

    def listener(event: Event):
        received_events.append(event)

    context.add_listener(listener)
    test_event = Event("test", "test_data")
    context.broadcast(test_event)

    # Give a small amount of time for the event to be processed
    sleep(0.1)

    assert len(received_events) == 1
    assert received_events[0] == test_event
    assert test_event in context._Context__history


def test_event_propagation(context):
    """Test that events propagate from child to parent contexts"""
    parent_events: List[Event] = []
    child_events: List[Event] = []

    def parent_listener(event: Event):
        parent_events.append(event)

    def child_listener(event: Event):
        child_events.append(event)

    child = context.child_context()

    context.add_listener(parent_listener)
    child.add_listener(child_listener)

    test_event = Event("test", "test_data")
    child.broadcast(test_event)

    # Give a small amount of time for the event to be processed
    sleep(0.1)

    # Event should be in both contexts
    assert len(parent_events) == 1
    assert len(child_events) == 1
    assert parent_events[0] == test_event
    assert child_events[0] == test_event


def test_context_status(context):
    """Test that context status properly reflects its state"""
    # Initial state should be running
    assert context.status == "running"

    # Test error state
    context.exception(Exception("test error"))
    assert context.status == "error"

    # Create new context to test success state
    context = Context()
    context.output = "test output"
    assert context.status == "success"


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
    assert context.status == "success"
    assert context.output == "test output"


def test_context_to_json(context):
    """Test that context JSON serialization works correctly"""
    # Test empty context
    json_data = context.to_json()
    assert json_data["id"] is not None
    assert json_data["parent_id"] is None
    assert json_data["status"] == "running"
    assert json_data["output"] is None
    assert json_data["history"] == []
    assert json_data["children"] == []
    assert json_data["error"] is None

    # Test context with output
    context.output = "test output"
    json_data = context.to_json()
    assert json_data["status"] == "success"
    assert json_data["output"] == "test output"

    # Test context with error
    context = Context()  # Create new context since output can't be set twice
    test_error = ValueError("test error")
    context.exception(test_error)
    json_data = context.to_json()
    assert json_data["status"] == "error"
    assert json_data["error"] == str(test_error)


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


def test_context_to_json_with_children(context):
    """Test that context JSON serialization properly handles child contexts"""
    child = context.child_context()
    child.output = "child output"

    json_data = context.to_json()
    assert len(json_data["children"]) == 1
    child_json = json_data["children"][0]
    assert child_json["output"] == "child output"
    assert child_json["status"] == "success"


def test_context_to_json_complex_data(context):
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

    context = Context()  # Create new context
    context.broadcast(Event("test", NonSerializable()))
    json_data = context.to_json()
    event_json = json_data["history"][0]
    assert event_json["data"] == "string representation"

    # Test with completely non-serializable object
    class CompletelyNonSerializable:
        def __str__(self):
            raise Exception("Can't convert to string")

    context = Context()  # Create new context
    context.broadcast(Event("test", CompletelyNonSerializable()))
    json_data = context.to_json()
    event_json = json_data["history"][0]
    assert event_json["data"] == "Unable to serialize data"
