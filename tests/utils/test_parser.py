import pytest

from arkaine.utils.parser import Label, Parser


@pytest.fixture
def basic_parser():
    labels = [
        Label(name="Action Input", required_with=["Action"], is_json=True),
        Label(name="Action", required_with=["Action Input"]),
        Label(name="Thought"),
        Label(name="Result", required=True),
    ]
    return Parser(labels)


@pytest.fixture
def similar_labels_parser():
    labels = [
        Label(name="Action"),
        Label(name="Action Input"),
        Label(name="Action Input Validation"),
        Label(name="Actions"),  # Plural version to test boundary matching
    ]
    return Parser(labels)


def test_basic_functionality(basic_parser):
    text = """
    Action: process_data
    Action Input: {"input_files": ["a.txt", "b.txt"]}
    Thought: Processing files
    Result: Done
    """
    result, errors = basic_parser.parse(text)

    assert len(errors) == 0
    assert result["action"] == "process_data"
    assert result["action input"] == {"input_files": ["a.txt", "b.txt"]}


def test_missing_required_field(basic_parser):
    text = """
    Action: test
    Action Input: {"test": true}
    Thought: thinking
    """
    result, errors = basic_parser.parse(text)

    assert "Required label 'result' missing" in errors[0]


def test_dependency_validation(basic_parser):
    text = """
    Action: test
    Thought: thinking
    Result: done
    """
    result, errors = basic_parser.parse(text)

    assert "'action' requires 'action input'" in errors[0].lower()


def test_malformed_json(basic_parser):
    text = """
    Action: test
    Action Input: {invalid json here}
    Result: done
    """
    result, errors = basic_parser.parse(text)

    assert any("JSON error in 'Action Input'" in err for err in errors)


def test_multiple_entries(basic_parser):
    text = """
    Action: test1
    Action Input: {"test": 1}
    
    Action: test2
    Action Input: {"test": 2}
    
    Result: done
    """
    result, errors = basic_parser.parse(text)
    print(result)

    assert len(result["action"]) == 2
    assert len(result["action input"]) == 2
    assert result["action"] == ["test1", "test2"]


def test_similar_label_names(similar_labels_parser):
    text = """
    Action Input Validation: checking
    Action Input: {"data": 123}
    Action: process
    Actions: multiple actions here
    """
    result, errors = similar_labels_parser.parse(text)

    assert "action input validation" in result
    assert result["action input validation"] == "checking"
    assert result["actions"] == "multiple actions here"


def test_empty_values(basic_parser):
    text = """
    Action:
    Action Input:
    Thought:
    Result:
    """
    result, errors = basic_parser.parse(text)

    assert all(len(entries) == 0 for entries in result.values())
    assert set(result.keys()) == {
        "action",
        "action input",
        "thought",
        "result",
    }


def test_weird_formatting(basic_parser):
    text = """
    Action:    test   
    Action    Input   :   {"test": true}   
    Result:done
    """
    result, errors = basic_parser.parse(text)

    assert result["action"] == "test"
    assert result["action input"] == {"test": True}
    assert result["result"] == "done"


def test_multiline_content(basic_parser):
    text = """
    Action: test
    Action Input: {
        "test": true,
        "nested": {
            "data": "value"
        }
    }
    Thought: This is a
    multiline
    thought process
    Result: done
    """
    result, errors = basic_parser.parse(text)
    print(result)

    assert len(result["thought"].split("\n")) == 3
    assert result["action input"]["nested"]["data"] == "value"


def test_mixed_separators(basic_parser):
    text = """
    Action: test1
    Action Input~ {"test": 1}
    Thought - thinking
    Result: done
    """
    result, errors = basic_parser.parse(text)

    assert len(errors) == 0
    assert result["action"] == "test1"
    assert result["thought"] == "thinking"


def test_case_insensitivity(basic_parser):
    text = """
    ACTION: test
    action INPUT: {"test": true}
    THOUGHT: thinking
    Result: done
    """
    result, errors = basic_parser.parse(text)

    assert len(errors) == 0
    assert result["action"] == "test"


def test_string_label_conversion():
    parser = Parser(["Label1", "Label2"])
    text = """
    Label1: test
    Label2: value
    """
    result, errors = parser.parse(text)

    assert len(errors) == 0
    assert result["label1"] == "test"
    assert result["label2"] == "value"


def test_markdown_code_blocks(basic_parser):
    text = """
    Action: test
    Action Input: ```json
    {
        "test": true
    }
    ```
    Result: done
    """
    result, errors = basic_parser.parse(text)

    assert len(errors) == 0
    assert result["action input"] == {"test": True}


def test_markdown_wrapped_content(basic_parser):
    text = """
    Action: test
    Action Input: ```plaintext
    {
        "test": true
    }
    ```
    Thought: ```
    Processing the data
    with multiple lines
    ```
    Result: ```markdown
    # Done
    - Successfully processed
    ```
    """
    result, errors = basic_parser.parse(text)

    assert len(errors) == 0
    assert result["action input"] == {"test": True}
    assert "Processing the data" in result["thought"]
    assert "# Done" in result["result"]


def test_nested_markdown_blocks(similar_labels_parser):
    text = """
    Action Input Validation: ```python
    def validate():
        return True
    ```
    Actions: ```shell
    $ run command
    $ another command
    ```
    Action: ```
    nested_action
    ```
    """
    result, errors = similar_labels_parser.parse(text)

    assert len(errors) == 0
    assert "def validate():" in result["action input validation"]
    assert "$ run command" in result["actions"]
    assert result["action"] == "nested_action"


def test_parse_blocks():
    text = """
    Action: first_action
    Action Input: {"id": 1}
    Thought: First thought
    Result: First result
    
    Action: second_action
    Action Input: {"id": 2}
    Thought: Second thought
    Result: Second result
    """

    parser = Parser(
        [
            Label(name="action", is_block_start=True),
            Label(name="action input", is_json=True),
            Label(name="thought"),
            Label(name="result"),
        ]
    )
    blocks, errors = parser.parse_blocks(text)

    assert len(errors) == 0
    assert len(blocks) == 2

    # First block
    assert blocks[0]["action"] == "first_action"
    assert blocks[0]["action input"] == {"id": 1}
    assert blocks[0]["thought"] == "First thought"
    assert blocks[0]["result"] == "First result"

    # Second block
    assert blocks[1]["action"] == "second_action"
    assert blocks[1]["action input"] == {"id": 2}
    assert blocks[1]["thought"] == "Second thought"
    assert blocks[1]["result"] == "Second result"


def normalize(text):
    # Remove extra whitespace and blank lines for comparison.
    return [line.strip() for line in text.strip().splitlines() if line.strip()]


def test_parse_blocks_with_markdown():
    parser = Parser(
        [
            Label(name="summary", is_block_start=True),
            Label(name="finding"),
        ]
    )
    text = """
    ```
    SUMMARY: A one sentence summary of the finding
    FINDING:
    The body of your finding, paragraph(s) of detailed, information dense facts.

    * Fact 1
    * Fact 2
    * Fact 3

    SUMMARY: A one sentence summary of the next finding
    FINDING:
    # Header
        The body of our second finding

    [Link Text](https://www.example.com)
    ```
    """

    blocks, errors = parser.parse_blocks(text)
    print(blocks)
    print(errors)

    # Normalize both the expected and actual output
    expected_finding_0 = (
        "The body of your finding, paragraph(s) of detailed, information dense "
        "facts.\n"
        "* Fact 1\n"
        "* Fact 2\n"
        "* Fact 3"
    )

    assert len(errors) == 0
    assert len(blocks) == 2

    # First block checks
    assert blocks[0]["summary"] == "A one sentence summary of the finding"
    assert normalize(blocks[0]["finding"]) == normalize(expected_finding_0)

    # Second block checks
    expected_finding_1 = (
        "# Header\n"
        "The body of our second finding\n"
        "[Link Text](https://www.example.com)"
    )
    assert blocks[1]["summary"] == "A one sentence summary of the next finding"
    assert normalize(blocks[1]["finding"]) == normalize(expected_finding_1)


def test_parse_blocks_with_delayed_values():
    text = """
    Action:
    first_action
    
    Action Input:
    {
      "id": 1,
      "data": "test"
    }
    
    Thought:
      This is a thought
      that spans multiple lines
      with indentation
    
    Result: First result
    
    Action:
    
    second_action
    
    Action Input:
    
    {
      "id": 2
    }
    
    Result:
    Second result
    with continuation
    """

    parser = Parser(
        [
            Label(name="action", is_block_start=True),
            Label(name="action input", is_json=True),
            Label(name="thought"),
            Label(name="result"),
        ]
    )
    blocks, errors = parser.parse_blocks(text)

    assert len(errors) == 0
    assert len(blocks) == 2

    # First block
    assert blocks[0]["action"] == "first_action"
    assert blocks[0]["action input"] == {"id": 1, "data": "test"}
    assert "This is a thought" in blocks[0]["thought"]
    assert "spans multiple lines" in blocks[0]["thought"]
    assert blocks[0]["result"] == "First result"

    # Second block
    assert blocks[1]["action"] == "second_action"
    assert blocks[1]["action input"] == {"id": 2}
    assert blocks[1]["result"] == "Second result\nwith continuation"


def test_parse_blocks_with_multiple_entries_in_block():
    text = """
    Action: first_action
    Action Input: {"id": 1}
    Thought: First thought
    
    Action: second_action
    Action Input: {"id": 2}
    Thought: Second thought
    Thought: Third thought, second for block 2
    """

    parser = Parser(
        [
            Label(name="action", is_block_start=True),
            Label(name="action input", is_json=True),
            Label(name="thought"),
        ]
    )
    blocks, errors = parser.parse_blocks(text)

    assert len(errors) == 0
    assert len(blocks) == 2

    assert blocks[0]["action"] == "first_action"
    assert blocks[0]["action input"] == {"id": 1}
    assert blocks[0]["thought"] == "First thought"

    assert blocks[1]["action"] == "second_action"
    assert blocks[1]["action input"] == {"id": 2}
    assert len(blocks[1]["thought"]) == 2
    assert blocks[1]["thought"][0] == "Second thought"
    assert blocks[1]["thought"][1] == "Third thought, second for block 2"


def test_parse_blocks_with_multiple_block_starts():
    text = """
    Action: first_action
    Action Input: {"id": 1}
    Thought: First thought

    Action: second_action
    Action Input: {"id": 2}
    Thought: Second thought
    """

    with pytest.raises(
        ValueError, match="Only one block start label is allowed"
    ):
        Parser(
            [
                Label(name="action", is_block_start=True),
                Label(name="action input", is_json=True),
                Label(name="thought", is_block_start=True),
            ]
        )


def test_parse_blocks_without_block_start():
    text = """
    Action: first_action
    Action Input: {"id": 1}
    Thought: First thought
    """

    parser = Parser(
        [
            Label(name="action"),
            Label(name="action input", is_json=True),
            Label(name="thought"),
        ]
    )
    with pytest.raises(
        ValueError,
        match="No block start label defined - must have at least one",
    ):
        parser.parse_blocks(text)
