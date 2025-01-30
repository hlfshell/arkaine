import pytest

from arkaine.internal.parser import Label, Parser


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
    result = basic_parser.parse(text)

    assert len(result["errors"]) == 0
    assert len(result["data"]["action"]) == 1
    assert len(result["data"]["action input"]) == 1
    assert result["data"]["action"][0] == "process_data"
    assert result["data"]["action input"][0] == {
        "input_files": ["a.txt", "b.txt"]
    }


def test_missing_required_field(basic_parser):
    text = """
    Action: test
    Action Input: {"test": true}
    Thought: thinking
    """
    result = basic_parser.parse(text)

    assert "Required label 'result' missing" in result["errors"]


def test_dependency_validation(basic_parser):
    text = """
    Action: test
    Thought: thinking
    Result: done
    """
    result = basic_parser.parse(text)

    assert "'action' requires 'action input'" in result["errors"][0].lower()


def test_malformed_json(basic_parser):
    text = """
    Action: test
    Action Input: {invalid json here}
    Result: done
    """
    result = basic_parser.parse(text)

    assert any(
        "JSON error in 'Action Input'" in err for err in result["errors"]
    )


def test_multiple_entries(basic_parser):
    text = """
    Action: test1
    Action Input: {"test": 1}
    
    Action: test2
    Action Input: {"test": 2}
    
    Result: done
    """
    result = basic_parser.parse(text)
    print(result)

    assert len(result["data"]["action"]) == 2
    assert len(result["data"]["action input"]) == 2
    assert result["data"]["action"] == ["test1", "test2"]


def test_similar_label_names(similar_labels_parser):
    text = """
    Action Input Validation: checking
    Action Input: {"data": 123}
    Action: process
    Actions: multiple actions here
    """
    result = similar_labels_parser.parse(text)

    assert "action input validation" in result["data"]
    assert result["data"]["action input validation"][0] == "checking"
    assert result["data"]["actions"][0] == "multiple actions here"


def test_empty_values(basic_parser):
    text = """
    Action:
    Action Input:
    Thought:
    Result:
    """
    result = basic_parser.parse(text)

    assert all(len(entries) == 0 for entries in result["data"].values())
    assert set(result["data"].keys()) == {
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
    result = basic_parser.parse(text)

    assert result["data"]["action"][0] == "test"
    assert result["data"]["action input"][0] == {"test": True}
    assert result["data"]["result"][0] == "done"


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
    result = basic_parser.parse(text)
    print(result)

    assert len(result["data"]["thought"][0].split("\n")) == 3
    assert result["data"]["action input"][0]["nested"]["data"] == "value"


def test_mixed_separators(basic_parser):
    text = """
    Action: test1
    Action Input~ {"test": 1}
    Thought - thinking
    Result: done
    """
    result = basic_parser.parse(text)

    assert len(result["errors"]) == 0
    assert result["data"]["action"][0] == "test1"
    assert result["data"]["thought"][0] == "thinking"


def test_case_insensitivity(basic_parser):
    text = """
    ACTION: test
    action INPUT: {"test": true}
    THOUGHT: thinking
    Result: done
    """
    result = basic_parser.parse(text)

    assert len(result["errors"]) == 0
    assert result["data"]["action"][0] == "test"


def test_string_label_conversion():
    parser = Parser(["Label1", "Label2"])
    text = """
    Label1: test
    Label2: value
    """
    result = parser.parse(text)

    assert len(result["errors"]) == 0
    assert result["data"]["label1"][0] == "test"
    assert result["data"]["label2"][0] == "value"


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
    result = basic_parser.parse(text)

    assert len(result["errors"]) == 0
    assert result["data"]["action input"][0] == {"test": True}


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
    result = basic_parser.parse(text)

    assert len(result["errors"]) == 0
    assert result["data"]["action input"][0] == {"test": True}
    assert "Processing the data" in result["data"]["thought"][0]
    assert "# Done" in result["data"]["result"][0]


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
    result = similar_labels_parser.parse(text)

    assert len(result["errors"]) == 0
    assert "def validate():" in result["data"]["action input validation"][0]
    assert "$ run command" in result["data"]["actions"][0]
    assert result["data"]["action"][0] == "nested_action"
