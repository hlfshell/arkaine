import pytest
from typing import List, Optional
from unittest.mock import MagicMock

from arkaine.tools.abstract import AbstractTool, AbstractAgent
from arkaine.tools.argument import Argument
from arkaine.tools.result import Result
from arkaine.tools.context import Context
from arkaine.tools.example import Example
from arkaine.llms.llm import LLM


# Test classes for AbstractTool
class ValidTool(AbstractTool):
    _rules = {
        "args": {
            "required": [
                Argument(
                    name="required_arg",
                    type="str",
                    description="A required string argument",
                )
            ],
            "allowed": [
                Argument(
                    name="optional_arg",
                    type="int",
                    description="An optional integer argument",
                )
            ],
        },
        "result": {
            "required": ["str"],
        },
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        return "result"


class MissingRequiredArgTool(AbstractTool):
    _rules = {
        "args": {
            "required": [
                Argument(
                    name="required_arg",
                    type="str",
                    description="A required string argument",
                )
            ],
            "allowed": [],
        },
        "result": {
            "required": None,
        },
    }


class WrongResultTypeTool(AbstractTool):
    _rules = {
        "args": {
            "required": [],
            "allowed": [],
        },
        "result": {
            "required": ["int"],
        },
    }


# Test class for AbstractAgent
class ValidAgent(AbstractAgent):
    _rules = {
        "args": {
            "required": [
                Argument(
                    name="query", type="str", description="The query string"
                )
            ],
            "allowed": [],
        },
        "result": {
            "required": ["str"],
        },
    }

    def prepare_prompt(self, context: Context, **kwargs):
        return "test prompt"

    def extract_result(self, context: Context, output: str) -> Optional[str]:
        return output


# Tests for AbstractTool
def test_valid_abstract_tool_initialization():
    """Test that a valid AbstractTool subclass can be initialized properly."""
    args = [
        Argument(
            name="required_arg",
            type="str",
            description="A required string argument",
            default="test",
        ),
        Argument(
            name="optional_arg",
            type="int",
            description="An optional integer argument",
            default=42,
        ),
    ]
    result = Result(type="str", description="A string result")

    tool = ValidTool(
        name="ValidTool",
        description="A valid tool for testing",
        args=args,
        func=lambda: "result",
        result=result,
    )

    assert tool.name == "ValidTool"
    assert tool.description == "A valid tool for testing"
    assert len(tool.args) == 2
    assert tool.result.type_str == "str"


def test_missing_required_argument():
    """Test that initialization fails when a required argument is missing."""
    args = []  # Missing required_arg

    with pytest.raises(ValueError) as excinfo:
        MissingRequiredArgTool(
            name="MissingRequiredArgTool",
            description="A tool missing required arguments",
            args=args,
            func=lambda: None,
        )

    assert "Required argument 'required_arg" in str(excinfo.value)


def test_wrong_argument_type():
    """Test that initialization fails when an argument has the wrong type."""
    args = [
        Argument(
            name="required_arg",
            type="int",
            description="A required argument",
            default=42,
        ),  # Should be str
    ]

    with pytest.raises(ValueError) as excinfo:
        ValidTool(
            name="ValidTool",
            description="A valid tool for testing",
            args=args,
            func=lambda: "result",
        )

    assert (
        "Required argument 'required_arg' is of type str but provided argument is of type int"
        in str(excinfo.value)
    )


def test_missing_result():
    """Test that initialization fails when a required result is missing."""
    args = [
        Argument(
            name="required_arg",
            type="str",
            description="A required string argument",
            default="test",
        ),
    ]

    with pytest.raises(ValueError) as excinfo:
        ValidTool(
            name="ValidTool",
            description="A valid tool for testing",
            args=args,
            func=lambda: "result",
            # Missing result
        )

    assert "requires a result but none was provided" in str(excinfo.value)


def test_wrong_result_type():
    """Test that initialization fails when the result has the wrong type."""
    args = []
    result = Result(type="str", description="A string result")

    with pytest.raises(ValueError) as excinfo:
        WrongResultTypeTool(
            name="WrongResultTypeTool",
            description="A tool with wrong result type",
            args=args,
            func=lambda: 42,
            result=result,
        )

    assert "result type str does not match one of the required types" in str(
        excinfo.value
    )


def test_ensure_rule_keys():
    """Test that _ensure_rule_keys adds missing keys with empty values."""
    tool = ValidTool(
        name="ValidTool",
        description="A valid tool for testing",
        args=[
            Argument(
                name="required_arg",
                type="str",
                description="A required string argument",
                default="test",
            )
        ],
        func=lambda: "result",
        result=Result(type="str", description="A string result"),
    )

    incomplete_rules = {}
    tool._ensure_rule_keys(incomplete_rules)

    assert "args" in incomplete_rules
    assert "result" in incomplete_rules
    assert "required" in incomplete_rules["args"]
    assert "allowed" in incomplete_rules["args"]
    assert "required" in incomplete_rules["result"]


# Tests for AbstractAgent
def test_valid_abstract_agent_initialization():
    """Test that a valid AbstractAgent subclass can be initialized properly."""
    args = [
        Argument(
            name="query",
            type="str",
            description="The query string",
            default="test query",
        )
    ]
    result = Result(type="str", description="A string result")
    mock_llm = MagicMock(spec=LLM)
    examples = [
        Example(
            name="test_example",
            args={"query": "test"},
            output="test output",
            description="A test example",
        )
    ]

    agent = ValidAgent(
        name="ValidAgent",
        description="A valid agent for testing",
        args=args,
        llm=mock_llm,
        examples=examples,
        result=result,
    )

    assert agent.name == "ValidAgent"
    assert agent.description == "A valid agent for testing"
    assert len(agent.args) == 1
    assert agent.args[0].name == "query"
    assert agent.llm == mock_llm
    assert len(agent.examples) == 1
    assert agent.result.type_str == "str"


def test_abstract_agent_missing_methods():
    """Test that AbstractAgent requires implementation of abstract methods."""

    class IncompleteAgent(AbstractAgent):
        _rules = {
            "args": {
                "required": [
                    Argument(
                        name="query", type="str", description="The query string"
                    )
                ],
                "allowed": [],
            },
            "result": {
                "required": ["str"],
            },
        }

        # Missing prepare_prompt and extract_result methods

    args = [
        Argument(
            name="query",
            type="str",
            description="The query string",
            default="test query",
        )
    ]
    mock_llm = MagicMock(spec=LLM)

    with pytest.raises(TypeError) as excinfo:
        IncompleteAgent(
            name="IncompleteAgent",
            description="An incomplete agent",
            args=args,
            llm=mock_llm,
        )

    # Check that it complains about one of the missing abstract methods
    assert "abstract method" in str(excinfo.value)
