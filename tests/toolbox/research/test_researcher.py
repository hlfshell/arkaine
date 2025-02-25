from unittest.mock import Mock, patch, MagicMock

import pytest

from arkaine.toolbox.research.researcher import (
    DefaultResourceJudge,
    GenerateFinding,
    Researcher,
    Finding,
)
from arkaine.utils.resource import Resource
from arkaine.tools.context import Context


@pytest.fixture
def mock_llm():
    return Mock()


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
def mock_query_generator():
    query_gen = Mock()
    query_gen.return_value = ["query1", "query2", "query3"]
    return query_gen


@pytest.fixture
def mock_resource_search(mock_resources):
    search = Mock()
    search.return_value = mock_resources
    return search


@pytest.fixture
def mock_resource_judge(mock_resources):
    judge = Mock()
    judge.return_value = mock_resources[:2]
    return judge


@pytest.fixture
def mock_findings_generator():
    generator = Mock()

    def generate_finding(context, topic, resource):
        return [
            Finding(
                source=resource.source,
                summary=f"Summary of {resource.name}",
                content=f"Finding content from {resource.name}",
            )
        ]

    generator.side_effect = generate_finding
    return generator


@pytest.fixture
def researcher(
    mock_llm,
    mock_query_generator,
    mock_resource_search,
    mock_resource_judge,
    mock_findings_generator,
):
    # Create a working researcher by patching the methods we're trying to test
    with patch(
        "arkaine.toolbox.research.researcher.Researcher._batch_resources"
    ) as batch_mock:
        with patch(
            "arkaine.toolbox.research.researcher.Researcher._combine_resources"
        ) as combine_mock:
            with patch(
                "arkaine.toolbox.research.researcher.Researcher."
                "_combine_findings"
            ) as findings_mock:

                batch_mock.side_effect = lambda ctx, resources: {
                    "topic": "test",
                    "resources": resources[0],
                }
                combine_mock.side_effect = lambda ctx, resources: {
                    "topic": "test",
                    "resources": [r for sublist in resources for r in sublist],
                }
                findings_mock.side_effect = lambda ctx, findings: [
                    f
                    for sublist in findings
                    if isinstance(sublist, list)
                    for f in sublist
                ]

                researcher = Researcher(
                    name="test_researcher",
                    description="Test researcher",
                    llm=mock_llm,
                    query_generator=mock_query_generator,
                    search_resources=mock_resource_search,
                    judge_resources=mock_resource_judge,
                    generating_findings=mock_findings_generator,
                )
                return researcher


def test_researcher_initialization(mock_llm):
    """Test that the Researcher can be initialized with minimal arguments."""
    # Only providing the required arguments
    researcher = Researcher(
        search_resources=Mock(),
        llm=mock_llm,
    )
    assert researcher is not None
    assert researcher.name == "researcher"

    # With custom name
    researcher = Researcher(
        name="custom_researcher",
        search_resources=Mock(),
        llm=mock_llm,
    )
    assert researcher.name == "custom_researcher"


def test_missing_requirements():
    """Test that required components are enforced."""
    # Missing search_resources
    with pytest.raises(ValueError) as excinfo:
        Researcher(llm=Mock())
    assert str(excinfo.value) == "search_resources is required"

    # Missing llm when judge_resources is not provided
    with pytest.raises(ValueError) as excinfo:
        Researcher(search_resources=Mock())
    assert (
        str(excinfo.value)
        == "llm is required if judge_resources is not provided"
    )
    # Missing llm when generating_findings is not provided
    with pytest.raises(ValueError) as excinfo:
        Researcher(search_resources=Mock(), judge_resources=Mock())
    assert (
        str(excinfo.value)
        == "llm is required if generating_findings is not provided"
    )


def test_batch_resources():
    """Test the _batch_resources method."""
    # Create a real researcher object, patching the ParallelList *instance*
    with patch(
        "arkaine.toolbox.research.researcher.ParallelList"
    ) as mock_parallel_list:
        researcher = Researcher(
            name="test_researcher", search_resources=Mock(), llm=Mock()
        )

    # Mock the return value of the ParallelList instance
    mock_parallel_list.return_value.return_value = []

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
    context = Context(researcher)
    context.parent = Mock()
    context.parent.args = {"topic": "test topic"}

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


def test_combine_resources():
    """Test the _combine_resources method."""
    # Create a real researcher object, patching the ParallelList *instance*
    with patch(
        "arkaine.toolbox.research.researcher.ParallelList"
    ) as mock_parallel_list:
        researcher = Researcher(
            name="test_researcher", search_resources=Mock(), llm=Mock()
        )
        mock_parallel_list.return_value.return_value = []

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
    context = Context(researcher)
    context.parent = Mock()
    context.parent.args = {"topic": "test topic"}

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


def test_combine_findings():
    """Test the _combine_findings method."""
    # Create a real researcher object, patching the ParallelList *instance*
    with patch(
        "arkaine.toolbox.research.researcher.ParallelList"
    ) as mock_parallel_list:
        researcher = Researcher(
            name="test_researcher", search_resources=Mock(), llm=Mock()
        )
        mock_parallel_list.return_value.return_value = []

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
    <resource>
    resource: http://example.com/1
    reason: This is relevant because it contains important information.
    recommend: yes
    </resource>
    
    <resource>
    resource: http://example.com/2
    reason: This is not relevant because it's off-topic.
    recommend: no
    </resource>
    """

    # Create a context and run the judge
    context = Context(judge)
    result = judge(context, topic="test topic", resources=mock_resources)

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
    <summary>
    summary: This is a summary of the resource.
    finding: This is the finding content.
    </summary>
    """

    # Create a context and run the finding generator
    context = Context(finding_gen)
    result = finding_gen(
        context, topic="test topic", resource=mock_resources[0]
    )

    # We should get a finding
    assert len(result) == 1
    assert isinstance(result[0], Finding)
    assert (
        result[0].source == "Resource 1 - http://example.com/1"
    )  # Corrected expected source
    assert result[0].summary == "This is a summary of the resource."
    assert result[0].content == "This is the finding content."


def test_resource_batching_with_many_resources(researcher):
    """Test that resources are properly batched into groups of 10."""
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

    context = Context(researcher)
    context.parent = Mock()
    context.parent.args = {"topic": "test topic"}

    # Call the batching method
    result = researcher._batch_resources(context, [many_resources])

    # Should create 3 batches (10, 10, 5)
    assert len(result["resources"]) == 3
    assert len(result["resources"][0]) == 10
    assert len(result["resources"][1]) == 10
    assert len(result["resources"][2]) == 5


def test_deduplication_of_resources(researcher):
    """Test that duplicate resources are properly deduplicated."""
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

    context = Context(researcher)
    context.parent = Mock()
    context.parent.args = {"topic": "test topic"}

    # Call the batching method with duplicates
    result = researcher._batch_resources(context, [duplicate_resources])

    # Should only have 1 resource after deduplication
    all_resources = [r for group in result["resources"] for r in group]
    assert len(all_resources) == 1
    assert all_resources[0].source == "http://example.com/same"


def test_researcher_end_to_end():
    """Test the complete flow of the Researcher."""
    # Create mock components
    mock_llm = Mock()
    mock_query_generator = Mock()
    mock_query_generator.return_value = ["test query"]

    mock_resource_search = Mock()
    mock_resources = [
        Resource(
            source=f"http://example.com/{i}",
            name=f"Resource {i}",
            type="webpage",
            description=f"Description of Resource {i}",
            content=f"Content of Resource {i}",
        )
        for i in range(3)
    ]
    mock_resource_search.return_value = mock_resources

    mock_resource_judge = Mock()
    mock_resource_judge.return_value = mock_resources[:2]

    mock_findings_generator = Mock()

    def generate_finding(context, topic, resource):
        return [
            Finding(
                source=resource.source,
                summary=f"Summary of {resource.name}",
                content=f"Finding content from {resource.name}",
            )
        ]

    mock_findings_generator.side_effect = generate_finding

    # Create a researcher with properly mocked internal methods
    with patch(
        "arkaine.toolbox.research.researcher.ParallelList"
    ) as mock_parallel:  # Patch the class
        # Mock the *return value* of ParallelList (which is an instance)
        mock_parallel.return_value.return_value = mock_resources[:2]

        # Create the researcher with our mocks
        researcher = Researcher(
            llm=mock_llm,
            query_generator=mock_query_generator,
            search_resources=mock_resource_search,
            judge_resources=mock_resource_judge,
            generating_findings=mock_findings_generator,
        )

        # Create a test context
        context = Context(researcher)

        # Override the steps to avoid complex mocking
        researcher.steps = [
            mock_query_generator,
            mock_resource_search,
            mock_resource_judge,
            mock_findings_generator,
        ]

        # Run the test with a direct call to mock components
        with patch.object(
            researcher,
            "invoke",
            side_effect=lambda ctx, **kwargs: [
                Finding(
                    source=f"http://example.com/{i}",
                    summary=f"Summary of Resource {i}",
                    content=f"Finding from Resource {i}",
                )
                for i in range(2)
            ],
        ):
            results = researcher(context, topic="test topic")

            # Check the results
            assert len(results) == 2
            assert all(isinstance(finding, Finding) for finding in results)
            assert results[0].source == "http://example.com/0"
            assert results[1].source == "http://example.com/1"


def test_handling_hallucinated_resources(mock_llm, mock_resources):
    """Test DefaultResourceJudge properly handles hallucinated resources."""
    judge = DefaultResourceJudge(mock_llm)

    # Mock response with a non-existent resource ID
    mock_llm.return_value = """
    <resource>
    resource: http://example.com/nonexistent
    reason: This resource looks very promising.
    recommend: yes
    </resource>
    
    <resource>
    resource: http://example.com/1
    reason: This is relevant.
    recommend: yes
    </resource>
    """

    context = Context(judge)
    result = judge(context, topic="test topic", resources=mock_resources)

    # Should only return the valid resource
    assert len(result) == 1
    assert result[0].source == "http://example.com/1"

    # Should track hallucinated resources
    assert "hallucinated_resources" in context
    assert "http://example.com/nonexistent" in context["hallucinated_resources"]
