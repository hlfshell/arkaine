from unittest.mock import Mock

import pytest

from arkaine.llms.llm import LLM
from arkaine.toolbox.research.researcher import (
    DefaultResourceJudge,
    Finding,
    GenerateFinding,
    Researcher,
)
from arkaine.tools.context import Context
from arkaine.tools.tool import Tool
from arkaine.utils.resource import Resource


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

        def completion(self, prompt) -> str:
            return "Mocked response"

    return MockLLM()


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
def mock_query_generator(mock_tool):
    query_gen = mock_tool(
        name="query_generator", return_value=["query1", "query2", "query3"]
    )
    return query_gen


@pytest.fixture
def mock_resource_search(mock_tool, mock_resources):
    search = mock_tool(name="resource_search", return_value=mock_resources)
    return search


@pytest.fixture
def mock_resource_judge(mock_resources, mock_tool):
    judge = mock_tool(name="resource_judge", return_value=mock_resources[:2])
    return judge


@pytest.fixture
def mock_findings_generator(mock_tool):
    generator = mock_tool(
        name="findings_generator",
        return_value=[
            Finding(
                source="http://example.com/1",
                summary="Summary of Resource 1",
                content="Finding content from Resource 1",
            )
        ],
    )
    return generator


@pytest.fixture
def researcher(
    mock_llm,
    mock_query_generator,
    mock_resource_search,
    mock_resource_judge,
    mock_findings_generator,
):
    """Create a properly configured researcher for testing."""
    # Create a researcher with mocked components
    researcher = Researcher(
        name="test_researcher",
        description="Test researcher",
        llm=mock_llm,
        query_generator=mock_query_generator,
        search_resources=mock_resource_search,
        judge_resources=mock_resource_judge,
        generating_findings=mock_findings_generator,
    )

    # Replace the ParallelList instances with mocks
    researcher._resource_search = Mock()
    researcher._resource_judge = Mock()
    researcher._finding_generation = Mock()

    # Configure the mocks to return appropriate values
    researcher._resource_search.return_value = {
        "topic": "test",
        "resources": [],
    }
    researcher._resource_judge.return_value = {"topic": "test", "resources": []}
    researcher._finding_generation.return_value = []

    return researcher


def test_researcher_initialization(mock_resource_search, mock_llm):
    """Test that the Researcher can be initialized with minimal arguments."""
    # Only providing the required arguments
    researcher = Researcher(
        search_resources=mock_resource_search,
        llm=mock_llm,
    )
    assert researcher is not None
    assert researcher.name == "researcher"

    # With custom name
    researcher = Researcher(
        name="custom_researcher",
        search_resources=mock_resource_search,
        llm=mock_llm,
    )
    assert researcher.name == "custom_researcher"


def test_missing_requirements(
    mock_llm, mock_resource_search, mock_resource_judge
):
    """Test that required components are enforced."""
    # Missing search_resources
    with pytest.raises(ValueError) as excinfo:
        Researcher(llm=mock_llm)
    assert str(excinfo.value) == "search_resources is required"

    # Missing llm when judge_resources is not provided
    with pytest.raises(ValueError) as excinfo:
        Researcher(search_resources=mock_resource_search)
    assert (
        str(excinfo.value)
        == "llm is required if judge_resources is not provided"
    )
    # Missing llm when generating_findings is not provided
    with pytest.raises(ValueError) as excinfo:
        Researcher(
            search_resources=mock_resource_search,
            judge_resources=mock_resource_judge,
        )
    assert (
        str(excinfo.value)
        == "llm is required if generating_findings is not provided"
    )


def test_batch_resources(mock_resource_search, mock_llm, mock_tool):
    """Test the _batch_resources method."""
    # Create a real researcher object
    researcher = Researcher(
        name="test_researcher",
        search_resources=mock_resource_search,
        llm=mock_llm,
    )

    # Create test resources
    resources = [
        Resource(
            source=f"http://example.com/{i}",
            name=f"Resource {i}",
            type="webpage",
            description=f"Description of Resource {i}",
            content=f"Content of Resource {i}",
        )
        for i in range(3)
    ]

    # Create a context with a parent context
    parent = Context(mock_tool())
    parent.args = {"topic": "test topic"}
    context = parent.child_context(researcher)

    # Test the _batch_resources method directly
    result = researcher._batch_resources(
        context, [resources[:2], resources[2:]]
    )

    # Check the result structure
    assert "topic" in result
    assert result["topic"] == "test topic"
    assert "resources" in result

    # All resources should be present (with duplicates removed)
    all_resources = [r for group in result["resources"] for r in group]
    assert len(all_resources) == 3
    assert set(r.source for r in all_resources) == {r.source for r in resources}


def test_combine_resources(mock_resource_search, mock_llm, mock_tool):
    """Test the _combine_resources method."""
    # Create a real researcher object
    researcher = Researcher(
        name="test_researcher",
        search_resources=mock_resource_search,
        llm=mock_llm,
    )

    # Create test resources
    resources = [
        Resource(
            source=f"http://example.com/{i}",
            name=f"Resource {i}",
            type="webpage",
            description=f"Description of Resource {i}",
            content=f"Content of Resource {i}",
        )
        for i in range(3)
    ]

    # Create a context with a parent context
    parent = Context(mock_tool())
    context = parent.child_context(researcher)
    parent.args = {"topic": "test topic"}

    # Test the _combine_resources method directly
    result = researcher._combine_resources(
        context, [resources[:2], resources[2:]]
    )

    # Check the result structure
    assert "topic" in result
    assert result["topic"] == "test topic"
    assert "resources" in result

    # All resources should be flattened into a single list
    assert isinstance(result["resources"], list)
    assert len(result["resources"]) == 3
    assert set(r.source for r in result["resources"]) == {
        r.source for r in resources
    }


def test_combine_findings(mock_resource_search, mock_llm):
    """Test the _combine_findings method."""
    # Create a real researcher object
    researcher = Researcher(
        name="test_researcher",
        search_resources=mock_resource_search,
        llm=mock_llm,
    )

    # Create test findings
    findings1 = [
        Finding("source1", "summary1", "content1"),
        Finding("source2", "summary2", "content2"),
    ]
    findings2 = [Finding("source3", "summary3", "content3")]

    # Also include an error case (not a list)
    mixed_findings = [findings1, findings2, Exception("Error")]

    # Create a context
    context = Context(researcher)

    # Test the _combine_findings method directly
    result = researcher._combine_findings(context, mixed_findings)

    # Should combine all valid findings
    assert len(result) == 3
    assert all(isinstance(f, Finding) for f in result)
    assert set(f.source for f in result) == {"source1", "source2", "source3"}


def test_default_resource_judge(mock_llm, mock_resources):
    """Test the DefaultResourceJudge."""
    # Setup the judge
    judge = DefaultResourceJudge(mock_llm)

    # Mock the LLM output with a correctly formatted response
    # Only one resource is recommended.
    mock_llm.return_value = """
    RESOURCE: http://example.com/1
    REASON: This is relevant because it contains important information.
    RECOMMEND: yes

    RESOURCE: http://example.com/2
    REASON: This is not relevant because it's off-topic.
    RECOMMEND: no
    """

    # Create a context and run the judge
    context = Context(judge)

    # Add resources to context
    context["resources"] = {r.source: r for r in mock_resources}

    result = judge.extract_result(context, mock_llm.return_value)

    # We should get only the first resource
    assert len(result) == 1
    assert result[0].source == "http://example.com/1"

    # Check that parsed judgements are stored in context
    assert "parsed_resource_judgements" in context
    assert len(context["parsed_resource_judgements"]) == 2


def test_generate_finding(mock_llm, mock_resources):
    """Test the GenerateFinding component."""
    # Setup the finding generator
    finding_gen = GenerateFinding(mock_llm)

    # Mock the LLM output with a correctly formatted response
    mock_llm.return_value = """
    SUMMARY: This is a summary of the resource.
    FINDING: This is the finding content.
    """

    # Create a context and run the finding generator
    context = Context(finding_gen)
    context.args = {"resource": mock_resources[0]}

    result = finding_gen.extract_result(context, mock_llm.return_value)

    # We should get a finding
    assert len(result) == 1
    assert isinstance(result[0], Finding)
    assert result[0].source == "Resource 1 - http://example.com/1"

    # The summary and content should be strings, not lists
    assert result[0].summary == "This is a summary of the resource."
    assert result[0].content == "This is the finding content."


def test_resource_batching_with_many_resources(
    mock_resource_search, mock_llm, mock_tool
):
    """Test that resources are properly batched into groups of 10."""
    # Create a real researcher object
    researcher = Researcher(
        name="test_researcher",
        search_resources=mock_resource_search,
        llm=mock_llm,
    )

    # Create 25 mock resources
    many_resources = [
        Resource(
            source=f"http://example.com/{i}",
            name=f"Resource {i}",
            type="webpage",
            description=f"Description of Resource {i}",
            content=f"Content of Resource {i}",
        )
        for i in range(25)
    ]

    parent = Context(mock_tool())
    parent.args = {"topic": "test topic"}
    context = parent.child_context(researcher)

    # Call the batching method
    result = researcher._batch_resources(context, [many_resources])

    # Should create 3 batches (10, 10, 5)
    assert len(result["resources"]) == 3
    assert len(result["resources"][0]) == 10
    assert len(result["resources"][1]) == 10
    assert len(result["resources"][2]) == 5


def test_deduplication_of_resources(mock_resource_search, mock_llm, mock_tool):
    """Test that duplicate resources are properly deduplicated."""
    # Create a real researcher object
    researcher = Researcher(
        name="test_researcher",
        search_resources=mock_resource_search,
        llm=mock_llm,
    )

    # Create duplicate resources with the same source
    duplicate_resources = [
        Resource(
            source="http://example.com/same",
            name="Resource 1",
            type="webpage",
            description="Description 1",
            content="Content 1",
        ),
        Resource(
            source="http://example.com/same",
            name="Resource 2",  # Different name, same source
            type="webpage",
            description="Description 2",
            content="Content 2",
        ),
    ]

    parent = Context(mock_tool())
    parent.args = {"topic": "test topic"}
    context = parent.child_context(researcher)

    # Call the batching method with duplicates
    result = researcher._batch_resources(context, [duplicate_resources])

    # Should only have 1 resource after deduplication
    all_resources = [r for group in result["resources"] for r in group]
    assert len(all_resources) == 1
    assert all_resources[0].source == "http://example.com/same"


def test_researcher_end_to_end(
    mock_resources,
    mock_llm,
    mock_query_generator,
    mock_resource_search,
    mock_resource_judge,
    mock_findings_generator,
):
    """Test the complete flow of the Researcher."""
    # Create mock components
    mock_llm = mock_llm
    mock_query_generator.func.return_value = ["test query"]

    # Create a researcher with our mocks
    researcher = Researcher(
        llm=mock_llm,
        query_generator=mock_query_generator,
        search_resources=mock_resource_search,
        judge_resources=mock_resource_judge,
        generating_findings=mock_findings_generator,
    )

    # Create a test context
    context = Context(researcher)

    # Mock the invoke method directly on the researcher instance
    researcher.invoke = Mock()
    researcher.invoke.return_value = [
        Finding(
            source="http://example.com/1",
            summary="Summary of Resource 1",
            content="Finding from Resource 1",
        ),
        Finding(
            source="http://example.com/2",
            summary="Summary of Resource 2",
            content="Finding from Resource 2",
        ),
    ]

    # Run the researcher
    results = researcher(context, topic="test topic")

    # Check the results
    assert len(results) == 2
    assert all(isinstance(finding, Finding) for finding in results)
    assert results[0].source == "http://example.com/1"
    assert results[1].source == "http://example.com/2"


def test_handling_hallucinated_resources(mock_llm, mock_resources):
    """Test DefaultResourceJudge properly handles hallucinated resources."""
    judge = DefaultResourceJudge(mock_llm)

    # Mock response with a non-existent resource ID
    mock_llm.return_value = """
    RESOURCE: http://example.com/nonexistent
    REASON: This resource looks very promising.
    RECOMMEND: yes
    
    RESOURCE: http://example.com/1
    REASON: This is relevant.
    RECOMMEND: yes
    """

    context = Context(judge)
    # Add resources to context - use the source as the key, not the ID
    context["resources"] = {r.source: r for r in mock_resources}

    result = judge.extract_result(context, mock_llm.return_value)

    # Should only return the valid resource
    assert len(result) == 1
    assert result[0].source == "http://example.com/1"

    # Should track hallucinated resources
    assert "hallucinated_resources" in context
    assert "http://example.com/nonexistent" in context["hallucinated_resources"]
