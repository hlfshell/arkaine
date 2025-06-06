from time import time
from unittest.mock import Mock, patch

import pytest

from arkaine.llms.llm import LLM
from arkaine.toolbox.research.iterative_researcher import (
    IterativeResearcher,
    DefaultTopicGenerator,
    TopicGenerator,
)
from arkaine.toolbox.research.finding import Finding
from arkaine.tools.argument import Argument
from arkaine.tools.context import Context
from arkaine.tools.result import Result
from arkaine.tools.tool import Tool
from arkaine.tools.toolify import toolify
from arkaine.utils.resource import Resource


@pytest.fixture
def mock_tool():
    def _create_mock_tool(name="mock_tool", return_value="mock result"):
        func = Mock()
        func.return_value = return_value
        return Tool(
            name=name,
            description="A mock tool for testing",
            args=[],
            func=func,
            examples=[],
            id=None,
            result=None,
        )

    return _create_mock_tool


@pytest.fixture
def mock_llm():
    class MockLLM(LLM):
        def __init__(self):
            super().__init__(
                name="mock_llm",
                id="mock-llm-id",
            )

        def context_length(self) -> int:
            return 4096

        def completion(self, prompt: str) -> str:
            return "Mocked response"

    return MockLLM()


@pytest.fixture
def mock_findings():
    return [
        Finding(
            source="http://example.com/1",
            summary="Summary of Finding 1",
            content="Content of Finding 1",
        ),
        Finding(
            source="http://example.com/2",
            summary="Summary of Finding 2",
            content="Content of Finding 2",
        ),
    ]


@pytest.fixture
def mock_resources():
    return [
        Resource(
            source="http://example.com/1",
            name="Resource 1",
            type="webpage",
            description="Description of Resource 1",
            content="Content of Resource 1",
        ),
        Resource(
            source="http://example.com/2",
            name="Resource 2",
            type="webpage",
            description="Description of Resource 2",
            content="Content of Resource 2",
        ),
        Resource(
            source="http://example.com/3",
            name="Resource 3",
            type="webpage",
            description="Description of Resource 3",
            content="Content of Resource 3",
        ),
    ]


@pytest.fixture
def mock_resource_search(mock_tool, mock_resources):
    search = mock_tool(name="resource_search", return_value=mock_resources)
    return search


@pytest.fixture
def mock_researcher(mock_llm, mock_findings):
    def mock_researcher_func(context, topic=""):
        return mock_findings

    return mock_researcher_func


@pytest.fixture
def mock_topic_generator(mock_llm):
    class MockQuestionGenerator(TopicGenerator):
        def __init__(self):
            super().__init__(
                name="GenerateTopics",
                description=("Generate a list of topics to research.",),
                args=[
                    Argument(
                        name="topics",
                        description=(
                            "Topics that have already been researched",
                        ),
                        type="list[str]",
                        required=True,
                    ),
                    Argument(
                        name="findings",
                        description=(
                            "Findings that have already been researched, "
                            "from which we can generate follow up questions."
                        ),
                        type="list[Finding]",
                        required=True,
                    ),
                ],
                result=Result(
                    type="list[str]",
                    description="List of generated questions",
                ),
                llm=mock_llm,
            )

        def prepare_prompt(self, context, *args, **kwargs):
            return "Question prompt"

        def extract_result(self, context, output):
            return ["Question 1", "Question 2"]

    return MockQuestionGenerator()


def test_deep_researcher_initialization(mock_llm, mock_researcher):
    """Test that DeepResearcher can be initialized with various configurations."""
    # Default initialization with just LLM
    deep_researcher = IterativeResearcher(llm=mock_llm)
    assert deep_researcher is not None
    assert deep_researcher.max_depth == 3
    assert deep_researcher.max_time_seconds == 600

    # Custom initialization
    deep_researcher = IterativeResearcher(
        llm=mock_llm,
        name="custom_deep_researcher",
        max_depth=5,
        max_time_seconds=300,
        researcher=mock_researcher,
    )
    assert deep_researcher.name == "custom_deep_researcher"
    assert deep_researcher.max_depth == 5
    assert deep_researcher.max_time_seconds == 300


def test_format_findings():
    """Test the _format_findings method."""
    deep_researcher = IterativeResearcher(llm=Mock())
    context = Context(deep_researcher)

    findings1 = [
        Finding("source1", "summary1", "content1"),
        Finding("source2", "summary2", "content2"),
    ]
    findings2 = [Finding("source3", "summary3", "content3")]

    # Test with valid findings
    result = deep_researcher._format_findings(context, [findings1, findings2])
    assert len(result) == 3
    assert all(isinstance(f, Finding) for f in result)

    # Test with empty lists
    result = deep_researcher._format_findings(context, [[], []])
    assert len(result) == 0

    # Test with non-list items
    result = deep_researcher._format_findings(context, ["not a list", None, []])
    assert len(result) == 0

    # Test with lists containing non-Finding items
    result = deep_researcher._format_findings(context, [[1, 2, 3], findings1])
    assert len(result) == 2  # Only findings1 should be included


def test_execute_research_cycle(mock_llm, mock_researcher, mock_findings):
    """Test the _execute_research_cycle method."""
    iterative_researcher = IterativeResearcher(
        llm=mock_llm, researcher=mock_researcher
    )

    context = Context(iterative_researcher)
    topics = ["What is AI?", "How does machine learning work?"]
    execute_research_cycle = toolify(
        iterative_researcher._execute_research_cycle
    )
    child_context = context.child_context(execute_research_cycle)

    # Mock the ParallelList researchers
    # iterative_researcher.__researcher = Mock()
    # iterative_researcher.__researcher.return_value = mock_findings

    # Execute the research cycle
    result = execute_research_cycle(child_context, topics)

    # Verify results
    assert "all_topics" in context
    assert context["all_topics"] == topics
    assert "findings" in context
    assert context["findings"] == mock_findings * 2
    assert result == mock_findings * 2

    # Test with empty questions
    context = Context(iterative_researcher)
    result = execute_research_cycle(child_context, [])
    assert result == []


def test_should_stop_max_depth(mock_llm):
    """Test that _should_stop returns True when max_depth is reached."""
    deep_researcher = IterativeResearcher(llm=mock_llm, max_depth=3)
    context = Context(deep_researcher)
    context["iteration"] = 3  # At max depth

    result = deep_researcher._should_stop(context, None)
    assert result is True


def test_should_stop_max_time(mock_llm):
    """Test that _should_stop returns True when max_time is exceeded."""
    deep_researcher = IterativeResearcher(llm=mock_llm, max_time_seconds=1)
    context = Context(deep_researcher)
    context["iteration"] = 1

    # Set start_time to be more than max_time_seconds ago
    context["researcher_start_time"] = time() - 2

    result = deep_researcher._should_stop(context, None)
    assert result is True


def test_should_stop_no_questions(mock_llm, mock_topic_generator):
    """
    Test that _should_stop returns True when no more questions are generated.
    """

    mock_topic_generator.extract_result = Mock()
    mock_topic_generator.extract_result.return_value = []

    deep_researcher = IterativeResearcher(
        llm=mock_llm, topic_generator=mock_topic_generator
    )
    context = Context(deep_researcher)
    context["iteration"] = 1
    context["researcher_start_time"] = time()

    result = deep_researcher._should_stop(context, None)
    assert result is True


def test_should_continue(mock_llm, mock_topic_generator):
    """
    Test that _should_stop returns False when conditions to continue are
    met.
    """

    mock_topic_generator.extract_result = Mock()
    mock_topic_generator.extract_result.return_value = [
        "New topic 1",
        "New topic 2",
    ]

    deep_researcher = IterativeResearcher(
        llm=mock_llm, topic_generator=mock_topic_generator
    )
    context = Context(deep_researcher)
    context["iteration"] = 1
    context["researcher_start_time"] = time()

    result = deep_researcher._should_stop(context, None)
    assert result is False
    assert "next_topics" in context
    assert context["next_topics"] == ["New topic 1", "New topic 2"]


def test_prepare_args_first_iteration(mock_llm):
    """
    Test that _prepare_args returns initial args on first iteration.
    """
    iterative_researcher = IterativeResearcher(llm=mock_llm)
    context = Context(iterative_researcher)
    context["iteration"] = 1

    initial_args = {"topics": ["Initial question"]}
    result = iterative_researcher._prepare_args(context, initial_args)

    assert result == {"topics": ["Initial question"]}


def test_prepare_args_subsequent_iterations(mock_llm):
    """
    Test that _prepare_args returns next_questions on subsequent iterations.
    """
    iterative_researcher = IterativeResearcher(llm=mock_llm)
    context = Context(iterative_researcher)
    context["iteration"] = 2
    context["next_topics"] = ["Follow-up topic 1", "Follow-up topic 2"]

    initial_args = {"topics": ["Initial question"]}
    result = iterative_researcher._prepare_args(context, initial_args)

    assert result == {"topics": ["Follow-up topic 1", "Follow-up topic 2"]}


def test_default_topic_generator(mock_llm):
    """Test the DefaultTopicGenerator."""
    generator = DefaultTopicGenerator(mock_llm)
    context = Context(generator)

    # Mock the parser.parse_blocks method
    with patch("arkaine.utils.parser.Parser.parse_blocks") as mock_parse:
        mock_parse.return_value = (
            [
                {
                    "reason": "Need more information about X",
                    "topic": "What is X?",
                },
                {
                    "reason": "Need to understand Y",
                    "topic": "How does Y work?",
                },
            ],
            None,
        )

        results = generator.extract_result(context, "Some output")

    assert "topics" in context
    assert len(results) == 2
    assert results[0] == "What is X?"
    assert results[1] == "How does Y work?"
    assert len(context["topics"]) == 2
    assert context["topics"][0]["reason"] == "Need more information about X"
    assert context["topics"][0]["topic"] == "What is X?"
    assert context["topics"][1]["reason"] == "Need to understand Y"
    assert context["topics"][1]["topic"] == "How does Y work?"


def test_default_topic_generator_none_response(mock_llm):
    """Test the DefaultTopicGenerator when it returns NONE."""
    generator = DefaultTopicGenerator(mock_llm)
    context = Context(generator)

    result = generator.extract_result(context, "NONE")

    assert result == []


def test_default_topic_generator_with_errors(mock_llm):
    """Test the DefaultTopicGenerator when parsing has errors."""
    generator = DefaultTopicGenerator(mock_llm)
    context = Context(generator)

    # Mock the parser.parse_blocks method with some errors
    with patch("arkaine.utils.parser.Parser.parse_blocks") as mock_parse:
        mock_parse.return_value = (
            [
                {
                    "reason": "Valid reason",
                    "topic": "Valid topic",
                },
            ],
            [True],
        )

        results = generator.extract_result(context, "Some output")

    # Only the valid topic should be returned
    assert results[0] == "Valid topic"


def test_deep_researcher_end_to_end(
    mock_llm, mock_researcher, mock_topic_generator
):
    """Test the complete flow of IterativeResearcher."""
    # Configure mocks
    mock_findings = [
        Finding("source1", "summary1", "content1"),
        Finding("source2", "summary2", "content2"),
    ]
    mock_researcher.return_value = mock_findings

    # First call returns questions, second call returns empty to stop iteration
    mock_topic_generator.side_effect = [
        ["Follow-up topic 1", "Follow-up topic 2"],
        [],
    ]

    # Create DeepResearcher with our mocks
    iterative_researcher = IterativeResearcher(
        llm=mock_llm,
        researcher=mock_researcher,
        topic_generator=mock_topic_generator,
    )

    # Replace the DoWhile's invoke method
    iterative_researcher.invoke = Mock()
    iterative_researcher.invoke.return_value = mock_findings

    # Run the deep researcher
    context = Context(iterative_researcher)
    results = iterative_researcher(context, topics=["Initial topic"])

    # Verify results
    assert results == mock_findings
    assert iterative_researcher.invoke.called
