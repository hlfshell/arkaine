from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from arkaine.connectors.schedule import Schedule
from arkaine.internal.registrar import Registrar
from arkaine.toolbox.scheduler import Scheduler, SchedulerNL
from arkaine.tools.tool import Tool


# Fixtures
@pytest.fixture
def mock_tool():
    """Create a mock tool for testing."""

    class MockTool(Tool):
        def __init__(self):
            super().__init__(
                name="mock_tool",
                description="Mock tool for testing",
                args=[],
                func=self.mock_func,
            )
            self.called_with = None

        def mock_func(self, items):
            self.called_with = items

        def async_call(self, items):
            # Override async_call to directly call mock_func
            self.mock_func(items)

    return MockTool()


@pytest.fixture
def clean_registrar():
    """Clear and restore registrar between tests."""
    original_tools = Registrar._tools.copy()
    Registrar._tools.clear()
    yield Registrar
    Registrar._tools.clear()
    Registrar._tools.update(original_tools)


@pytest.fixture
def mock_schedule():
    """Create a mock schedule for testing."""
    schedule = MagicMock(spec=Schedule)
    schedule.running = False
    schedule.tasks = []
    return schedule


@pytest.fixture
def scheduler(mock_schedule):
    """Create a scheduler instance with a mock schedule."""
    return Scheduler(schedule=mock_schedule)


@pytest.fixture
def scheduler_with_recurrence(mock_schedule):
    """Create a scheduler instance that allows recurrence."""
    return Scheduler(schedule=mock_schedule, allow_recurrence=True)


@pytest.fixture
def mock_llm():
    """Create a mock LLM for testing."""
    llm = MagicMock()
    llm.name = "mock_llm"
    return llm


# Basic Scheduler Tests
def test_scheduler_initialization(mock_schedule):
    """Test basic scheduler initialization."""
    scheduler = Scheduler(schedule=mock_schedule)
    assert scheduler is not None
    assert mock_schedule.run.called


def test_scheduler_no_schedule():
    """Test scheduler requires schedule instance."""
    with pytest.raises(ValueError, match="Schedule instance is required"):
        Scheduler(schedule=None)


def test_scheduler_task_now(scheduler, mock_tool, clean_registrar):
    """Test scheduling a task for immediate execution."""
    clean_registrar.register(mock_tool)

    result = scheduler.schedule_task(
        context=None,
        tool_name="mock_tool",
        tool_args={"arg1": "value1"},
        trigger_at="now",
    )

    assert result["tool"] == "mock_tool"
    assert isinstance(result["next_trigger"], datetime)
    assert "task_id" in result


def test_scheduler_task_future(scheduler, mock_tool, clean_registrar):
    """Test scheduling a task for future execution."""
    clean_registrar.register(mock_tool)

    future_time = (datetime.now() + timedelta(hours=1)).isoformat()
    result = scheduler.schedule_task(
        context=None,
        tool_name="mock_tool",
        tool_args={"arg1": "value1"},
        trigger_at=future_time,
    )

    assert result["tool"] == "mock_tool"
    assert isinstance(result["next_trigger"], datetime)
    assert "task_id" in result


def test_scheduler_task_with_recurrence(
    scheduler_with_recurrence, mock_tool, clean_registrar
):
    """Test scheduling a recurring task."""
    clean_registrar.register(mock_tool)

    result = scheduler_with_recurrence.schedule_task(
        context=None,
        tool_name="mock_tool",
        tool_args={"arg1": "value1"},
        trigger_at="now",
        recur_every="daily",
    )

    assert result["tool"] == "mock_tool"
    assert result["recurrence"] == "daily"
    assert isinstance(result["next_trigger"], datetime)


def test_scheduler_invalid_tool(scheduler, clean_registrar, mock_tool):
    """Test scheduling with non-existent tool."""
    # Ensure the mock tool is registered
    clean_registrar.register(mock_tool)

    with pytest.raises(ValueError) as exc_info:
        scheduler.schedule_task(
            context=None,
            tool_name="nonexistent_tool",
            tool_args={},
            trigger_at="now",
        )
    assert "Tool with identifier nonexistent_tool not found" in str(
        exc_info.value
    )


def test_scheduler_invalid_datetime(scheduler, mock_tool, clean_registrar):
    """Test scheduling with invalid datetime format."""
    clean_registrar.register(mock_tool)

    with pytest.raises(
        ValueError, match="trigger_at must be 'now' or a datetime"
    ):
        scheduler.schedule_task(
            context=None,
            tool_name="mock_tool",
            tool_args={},
            trigger_at="invalid_datetime",
        )


def test_scheduler_recurrence_when_disabled(
    scheduler, mock_tool, clean_registrar
):
    """Test scheduling recurring task when recurrence is disabled."""
    clean_registrar.register(mock_tool)

    # Should work but ignore recurrence
    result = scheduler.schedule_task(
        context=None,
        tool_name="mock_tool",
        tool_args={},
        trigger_at="now",
        recur_every="daily",
    )

    assert result["recurrence"] == "daily"
    assert isinstance(result["next_trigger"], datetime)


# SchedulerNL Tests
def test_scheduler_nl_initialization(mock_schedule, mock_llm):
    """Test SchedulerNL initialization."""
    scheduler_nl = SchedulerNL(llm=mock_llm, schedule=mock_schedule)
    assert scheduler_nl is not None


def test_scheduler_nl_missing_dependencies():
    """Test SchedulerNL initialization with missing dependencies."""
    mock_llm = MagicMock()
    with pytest.raises(
        ValueError, match="Either scheduler or schedule must be provided"
    ):
        SchedulerNL(llm=mock_llm)


def test_scheduler_nl_process_valid_response(
    mock_schedule, mock_llm, mock_tool, clean_registrar
):
    """Test SchedulerNL processing valid LLM response."""
    clean_registrar.register(mock_tool)

    # Mock LLM to return valid JSON response
    mock_llm.return_value = (
        '{"tool_name": "mock_tool", '
        '"tool_args": {"arg1": "value1"}, '
        '"trigger_at": "now"}'
    )

    scheduler_nl = SchedulerNL(llm=mock_llm, schedule=mock_schedule)

    # Mock the prepare_prompt method to avoid needing tool descriptions
    with patch.object(scheduler_nl, "prepare_prompt") as mock_prepare:
        mock_prepare.return_value = [{"role": "user", "content": "test"}]
        result = scheduler_nl("Schedule mock_tool for now")

    assert result["tool"] == "mock_tool"
    assert isinstance(result["next_trigger"], datetime)


def test_scheduler_nl_invalid_json_response(mock_schedule, mock_llm):
    """Test SchedulerNL handling invalid JSON from LLM."""
    # Use actually invalid JSON
    mock_llm.return_value = (
        '{"tool_name": "mock_tool", '
        '"tool_args": {"arg1": "value1", '  # Note the trailing comma
        'trigger_at": "now"'  # Missing quote and broken structure
    )

    scheduler_nl = SchedulerNL(llm=mock_llm, schedule=mock_schedule)

    # Mock the prepare_prompt method
    with patch.object(scheduler_nl, "prepare_prompt") as mock_prepare:
        mock_prepare.return_value = [{"role": "user", "content": "test"}]
        with pytest.raises(ValueError):
            scheduler_nl("Schedule something")


def test_scheduler_nl_missing_required_fields(mock_schedule, mock_llm):
    """Test SchedulerNL handling LLM response missing required fields."""
    mock_llm.return_value = """{"tool_name": "mock_tool"}"""

    scheduler_nl = SchedulerNL(llm=mock_llm, schedule=mock_schedule)

    # Mock the prepare_prompt method
    with patch.object(scheduler_nl, "prepare_prompt") as mock_prepare:
        mock_prepare.return_value = [{"role": "user", "content": "test"}]
        with pytest.raises(ValueError):
            scheduler_nl("Schedule something")


def test_scheduler_nl_with_recurrence(
    mock_schedule, mock_llm, mock_tool, clean_registrar
):
    """Test SchedulerNL with recurrence enabled."""
    clean_registrar.register(mock_tool)

    mock_llm.return_value = (
        '{"tool_name": "mock_tool", '
        '"tool_args": {"arg1": "value1"}, '
        '"trigger_at": "now", '
        '"recur_every": "daily"}'
    )

    scheduler_nl = SchedulerNL(
        llm=mock_llm, schedule=mock_schedule, allow_recurrence=True
    )

    # Mock the prepare_prompt method
    with patch.object(scheduler_nl, "prepare_prompt") as mock_prepare:
        mock_prepare.return_value = [{"role": "user", "content": "test"}]
        result = scheduler_nl("Schedule mock_tool daily")

    assert result["tool"] == "mock_tool"
    assert result["recurrence"] == "daily"
