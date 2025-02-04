from typing import Any, List, Optional, Tuple

import pytest

from arkaine.backends.backend import Backend, ToolNotFoundException
from arkaine.llms.llm import LLM, Prompt, RolePrompt
from arkaine.tools.tool import Tool
from arkaine.tools.types import ToolArguments, ToolResults


# Mock classes for testing
class MockLLM(LLM):
    def __init__(self, responses: List[str]):
        self.responses = responses
        self.current_response = 0

    @property
    def context_length(self) -> int:
        return 1000

    def completion(self, prompt: Prompt) -> str:
        response = self.responses[self.current_response]
        self.current_response += 1
        return response


class MockTool(Tool):
    def __init__(self, name: str):
        self.name = name

    def __call__(self, **kwargs: Any) -> Any:
        return f"Result from {self.name}"


class MockBackend(Backend):
    def parse_for_tool_calls(
        self, text: str, stop_at_first_tool: bool = False
    ) -> List[Tuple[str, ToolArguments]]:
        # Simple parser that looks for "use_tool:" format
        if "use_tool:" not in text:
            return []

        tool_name = "mock_tool"
        args = {"arg": "test"}
        return [(tool_name, args)]

    def parse_for_result(self, text: str) -> Optional[Any]:
        if "final_result:" in text:
            return text.split("final_result:")[1].strip()
        return None

    def tool_results_to_prompts(
        self, prompt: Prompt, results: ToolResults
    ) -> List[Prompt]:
        # Create a new prompt with the tool results added
        new_message: RolePrompt = {
            "role": "assistant",
            "content": "Tool results added",
        }
        return [prompt + [new_message]]

    def prepare_prompt(self, **kwargs) -> Prompt:
        return [{"role": "user", "content": "Test prompt"}]


def test_backend_initialization():
    llm = MockLLM([""])
    tools = [MockTool("mock_tool")]
    backend = MockBackend(llm, tools)

    assert isinstance(backend.llm, LLM)
    assert len(backend.tools) == 1
    assert "mock_tool" in backend.tools


def test_tool_not_found_exception():
    llm = MockLLM(["use_tool:"])
    tools = []  # Empty tools list
    backend = MockBackend(llm, tools)

    with pytest.raises(ToolNotFoundException):
        backend.invoke(None, {})


def test_max_steps_exceeded():
    llm = MockLLM(["use_tool:"] * 5)  # Always returns tool call
    tools = [MockTool("mock_tool")]
    backend = MockBackend(llm, tools)

    with pytest.raises(Exception, match="too many steps"):
        backend.invoke(None, {}, max_steps=2)


def test_successful_result():
    llm = MockLLM(["final_result: Success"])
    tools = [MockTool("mock_tool")]
    backend = MockBackend(llm, tools)

    result = backend.invoke(None, {})
    assert result == "Success"


def test_tool_execution_flow():
    # Test that tools are called and results are processed
    responses = [
        "use_tool:",  # First call triggers tool
        "final_result: Done",  # Second call returns result
    ]
    llm = MockLLM(responses)
    tools = [MockTool("mock_tool")]
    backend = MockBackend(llm, tools)

    result = backend.invoke(None, {})
    assert result == "Done"


def test_stop_at_first_tool():
    llm = MockLLM(["use_tool: first\nuse_tool: second"])
    tools = [MockTool("mock_tool")]
    backend = MockBackend(llm, tools)

    tool_calls = backend.parse_for_tool_calls(
        "use_tool: test", stop_at_first_tool=True
    )
    assert len(tool_calls) == 1


def test_call_tools():
    llm = MockLLM([""])
    tool = MockTool("mock_tool")
    backend = MockBackend(llm, [tool])

    calls = [("mock_tool", {"arg": "test"})]
    results = backend.call_tools(calls)

    assert len(results) == 1
    assert results[0][0] == "mock_tool"
    assert results[0][2] == "Result from mock_tool"
