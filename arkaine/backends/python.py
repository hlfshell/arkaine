import pathlib
import re
import traceback
from os import path
from typing import Any, Callable, Dict, List, Optional

from arkaine.backends.base import BaseBackend
from arkaine.events import AgentBackendStep, AgentLLMResponse, AgentPrompt
from arkaine.llms.llm import LLM, Prompt
from arkaine.toolbox.code_envs.python import PythonEnv
from arkaine.tools.tool import Context, Tool
from arkaine.tools.types import ToolCalls, ToolResults
from arkaine.utils.templater import PromptTemplate
from arkaine.utils.tool_format import python as python_func


class PythonBackendResponse:
    def __init__(
        self,
        plan: str,
        code: Dict[str, str],
        libraries: List[str],
        answer: str,
    ):
        self.plan = plan
        self.code = code
        self.libraries = libraries
        self.answer = answer

    def __str__(self):
        return (
            f"PLAN: {self.plan}\n"
            f"CODE: {self.code}\n"
            f"LIBRARIES: {self.libraries}\n"
            f"ANSWER: {self.answer}"
        )

    def __repr__(self):
        return self.__str__()


class PythonJudgeResponse:

    def __init__(self, status: str, answer: str, reason: str, changes: str):
        self.status = status
        self.answer = answer
        self.reason = reason
        self.changes = changes

    def __str__(self):
        return (
            f"STATUS: {self.status}\n"
            f"ANSWER: {self.answer}\n"
            f"REASON: {self.reason}\n"
            f"CHANGES: {self.changes}"
        )

    def __repr__(self):
        return self.__str__()


class PythonOutput:

    def __init__(self, output: Any, exception: Optional[Exception]):
        self.output = output
        self.exception = exception

    def __str__(self):
        return f"OUTPUT: {self.output}\nEXCEPTION: {self.exception}"

    def __repr__(self):
        return self.__str__()


class PythonBackend(BaseBackend):

    def __init__(
        self,
        llm: LLM,
        tools: List[Tool],
        agent_explanation: str,
        initial_state: Dict[str, Any] = {},
        process_answer: Optional[Callable[[Any], Any]] = None,
    ):
        super().__init__(
            llm,
            tools,
            initial_state=initial_state,
            process_answer=process_answer,
        )

        self.agent_explanation = agent_explanation
        self.__base_template = PromptTemplate.from_file(
            path.join(
                pathlib.Path(__file__).parent,
                "prompts",
                "python.prompt",
            )
        )
        self.__followup_template = PromptTemplate.from_file(
            path.join(
                pathlib.Path(__file__).parent,
                "prompts",
                "python_followup.prompt",
            )
        )

    def prepare_prompt(self, context: Context, **kwargs) -> Prompt:
        if self.tools:
            tools_block = (
                "You have the following functions always available in your "
                "python environment:\n"
            )
            tools_block += "\n".join(
                [python_func(tool) for tool in self.tools.values()]
            )
        else:
            tools_block = ""

        prompt = self.__base_template.render(
            {
                "tools_block": tools_block,
                "task": kwargs["task"],
            }
        )

        if "responses" in context:
            last_code = context["code"][-1]
            last_output = context["outputs"][-1]

            coding_block = ""

            # Given that last_code is a dict[str, [Dict[str, (recursive)]]] we
            # need to convert it to a string block. All directories are
            # expressed as subdirectories in the filename, ie if we are
            # multiple dict keys in, they are combined with
            # dir1/dir2/filename.py etc
            blocks = []
            code_dict_queue = [(last_code, "")]
            while code_dict_queue:
                code_dict, prefix = code_dict_queue.pop()
                for filename, content in code_dict.items():
                    path = f"{prefix}/{filename}" if prefix else filename
                    if isinstance(content, dict):
                        code_dict_queue.append((content, path))
                    else:
                        blocks.append(f"```python:{path}\n{content}\n```")

            coding_block = "\n\n".join(blocks)

            # For the output block, we either have a successful run w/
            # the output, or an exception object. Note the output might
            # be any type, so we need to see if it is not a string and
            # if so stringify it.
            output_block = ""
            if last_output.exception:
                tb_str = "".join(
                    traceback.format_tb(last_output.exception.__traceback__)
                )
                output_block = (
                    f"Exception thrown:\n"
                    f"{last_output.exception.__class__.__name__}: "
                    f"{str(last_output.exception)}\n{tb_str}"
                )
            else:
                output = last_output.output
                if not isinstance(output, str):
                    output = str(output)
                output_block = output

            print(
                {
                    "last_code": coding_block,
                    "last_output": output_block,
                    "task": kwargs["task"],
                }
            )
            prompt += self.__followup_template.render(
                {
                    "last_code": coding_block,
                    "last_output": output_block,
                    "task": kwargs["task"],
                }
            )

        return prompt

    def parse_response(
        self, context: Context, text: str
    ) -> PythonBackendResponse:
        sections = {
            "PLAN": "",
            "CODE": "",
            "LIBRARIES_NEEDED": "",
            "ANSWER": "",
        }

        # Here we are aiming to match the section headers, but taking note
        # that some LLMs like to add additional formatting even when told
        # not to - commonly *'s and #'s, some spacing, etc.
        section_pattern = re.compile(
            r"^\s*(?:[*#]+\s*)?(?P<section>PLAN|CODE|LIBRARIES_NEEDED|ANSWER)(?:\s*[*#]+)?:\s*(?:##)?",
            re.MULTILINE,
        )
        matches = list(section_pattern.finditer(text))

        # Extract content for each section
        for i, match in enumerate(matches):
            section_name = match.group("section")
            start_pos = match.end()
            end_pos = (
                matches[i + 1].start() if i + 1 < len(matches) else len(text)
            )
            section_content = text[start_pos:end_pos].strip()

            if section_name == "CODE":
                # We are extracting multiple code blocks and isolating the
                # filenames if included.
                code_blocks = re.findall(
                    r"```python:(.*?)\n(.*?)```", section_content, re.DOTALL
                )
                code_files = {
                    filename.strip(): code.strip()
                    for filename, code in code_blocks
                }
                sections["CODE"] = code_files
            else:
                sections[section_name] = section_content.strip()

        # Isolate the libraries, and deal with LLMs that write out
        # None or N/A which is common on smaller models.
        libraries = [
            lib
            for lib in sections["LIBRARIES_NEEDED"].split()
            if lib.lower() not in ["none", "n/a"]
        ]

        # For each code_file key with a / in its filename, it's
        # specifying subdirectories. We need to recursively create
        # the directories and files.
        code = {}

        for filename, content in sections["CODE"].items():
            # Split the filename into directories and the actual filename
            path_parts = filename.split("/")
            directories = path_parts[:-1]
            actual_filename = path_parts[-1]

            # Start with the code_files dict and traverse/create the directory
            # structure
            current_dict = code
            for directory in directories:
                if directory not in current_dict:
                    current_dict[directory] = {}
                current_dict = current_dict[directory]

            # Only set the file content if it doesn't already exist
            if actual_filename not in current_dict:
                current_dict[actual_filename] = content

        # Some models struggle with remembering to include a main() function or
        # an if __name__ == "__main__" clause. We will attempt to rectify this
        # by adding a main() function block if it is missing as a last ditch
        # effort to save the current code.
        if "main.py" in code:
            # Ensure that main.py has either a main() function or an
            # if __name__ == "__main__" clause
            if "main()" not in code["main.py"] and (
                "__name__" not in code["main.py"]
            ):
                # Attempt to rectify it by wrapping the whole file in
                # an def main() function block
                new_code = "def main():\n"
                for line in code["main.py"].splitlines():
                    new_code += f"\t{line}\n"
                code["main.py"] = new_code

        return PythonBackendResponse(
            plan=sections["PLAN"],
            code=code,
            libraries=libraries,
            answer=sections["ANSWER"],
        )

    def parse_for_result(self, context: Context, text: str) -> Optional[Any]:
        return None

    def parse_for_tool_calls(
        self, context: Context, text: str, stop_at_first_tool: bool = False
    ) -> ToolCalls:
        """
        We don't need this as our code will call the tools for us. We want
        to trigger the call_tools function though, so...
        """
        return []

    def tool_results_to_prompts(
        self, context: Context, prompt: Prompt, results: ToolResults
    ) -> List[Prompt]:
        """
        We don't need this either.
        """
        return []

    def invoke(
        self,
        context: Context,
        args: Dict[str, Any],
        max_steps: Optional[int] = None,
        stop_at_first_tool: bool = False,
    ) -> str:
        self._initialize_state(context)

        steps = 0

        with PythonEnv(tools=self.tools.values()) as env:
            while True:
                steps += 1
                context.broadcast(AgentBackendStep(steps))

                if max_steps and steps > max_steps:
                    raise Exception("too many steps")

                # Build prompt
                prompt = self.prepare_prompt(context, **args)
                context.broadcast(AgentPrompt(prompt))

                for p in prompt:
                    role = p["role"]
                    content = p["content"]
                    print("-" * 100)
                    print(f"{role}:")
                    for line in content.split("\n"):
                        print(line)
                print("-" * 100)
                raw_response = self.query_model(prompt)
                print("RAW RESPONSE", raw_response)

                response = self.parse_response(context, raw_response)

                if "responses" not in context:
                    context["responses"] = []

                context["responses"].append(response)

                context.broadcast(AgentLLMResponse(response))

                print("RESPONSE", response)

                if response.answer and len(context["responses"]) > 1:
                    return response.answer

                if "code" not in context:
                    context["code"] = []
                context["code"].append(response.code)

                output, exception = env.execute(
                    response.code,
                    context=context,
                )
                print("OUTPUT", output)
                print("EXCEPTION", exception)

                if "outputs" not in context:
                    context["outputs"] = []

                context["outputs"].append(
                    PythonOutput(output=output, exception=exception)
                )
