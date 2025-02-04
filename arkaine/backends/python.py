import json
import pathlib
import re
import traceback
from os import path
from typing import Any, Callable, Dict, List, Optional

from arkaine.backends.backend import Backend
from arkaine.events import AgentBackendStep, AgentLLMResponse, AgentPrompt
from arkaine.llms.llm import LLM, Prompt
from arkaine.toolbox.code_envs.python import PythonEnv
from arkaine.tools.context import Context
from arkaine.tools.tool import Tool
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

    def to_json(self):
        return {
            "plan": self.plan,
            "code": self.code,
            "libraries": self.libraries,
            "answer": self.answer,
        }


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

    def to_json(self):
        return {
            "status": self.status,
            "answer": self.answer,
            "reason": self.reason,
            "changes": self.changes,
        }


class PythonOutput:

    def __init__(
        self,
        output: Any,
        exception: Optional[Exception],
        stdout: str,
        stderr: str,
    ):
        self.output = output
        self.exception = exception
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        return f"OUTPUT: {self.output}\nEXCEPTION: {self.exception}"

    def __repr__(self):
        return self.__str__()

    def to_json(self):
        if hasattr(self.output, "to_json"):
            output = self.output.to_json()
        else:
            try:
                output = json.dumps(self.output)
            except Exception:
                output = str(self.output)

        return {
            "output": output,
            "exception": str(self.exception) if self.exception else None,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


class PythonBackend(Backend):

    def __init__(
        self,
        llm: LLM,
        tools: List[Tool],
        agent_explanation: str,
        initial_state: Dict[str, Any] = {},
        process_answer: Optional[Callable[[Any], Any]] = None,
        retry_code_attempts: int = 3,
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
        self.__judge_template = PromptTemplate.from_file(
            path.join(
                pathlib.Path(__file__).parent,
                "prompts",
                "python_judge.prompt",
            )
        )

        self.__retry_code_attempts = retry_code_attempts

    def __dict_to_code_blocks(self, code_dict: Dict[str, Any]) -> str:
        blocks = []
        code_dict_queue = [(code_dict, "")]
        while code_dict_queue:
            code_dict, prefix = code_dict_queue.pop()
            for filename, content in code_dict.items():
                path = f"{prefix}/{filename}" if prefix else filename
                if isinstance(content, dict):
                    code_dict_queue.append((content, path))
                else:
                    blocks.append(f"```python:{path}\n{content}\n```")

        return "\n\n".join(blocks)

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

        followup = ""

        if "responses" in context:
            last_code = context["code"][-1]
            last_output = context["outputs"][-1]
            last_judge = context["judgements"][-1]

            # Given that last_code is a dict[str, [Dict[str, (recursive)]]] we
            # need to convert it to a string block. All directories are
            # expressed as subdirectories in the filename, ie if we are
            # multiple dict keys in, they are combined with
            # dir1/dir2/filename.py etc
            coding_block = self.__dict_to_code_blocks(last_code)

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

            followup = self.__followup_template.render(
                {
                    "code_block": coding_block,
                    "output_block": output_block,
                    "reason": last_judge.reason,
                    "suggested_changes": last_judge.changes,
                    "task": kwargs["task"],
                }
            )[0]["content"]

        prompt = self.__base_template.render(
            {
                "tools_block": tools_block,
                "task": kwargs["task"],
                "followup": followup,
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

    def __parse_judge_response(self, text: str) -> PythonJudgeResponse:
        # Extract status which is always present
        try:
            status_match = re.search(r"STATUS:\s*(.+?)(?:\n|$)", text)
            if not status_match:
                raise ValueError("STATUS field not found in response")
            status = status_match.group(1).strip()
        except Exception as e:
            raise ValueError(f"Failed to parse STATUS: {str(e)}")

        # Check for REASON/CHANGES group first
        try:
            reason_match = re.search(r"REASON:\s*(.+?)(?:\n|$)", text)
            changes_match = re.search(
                r"CHANGES:\s*(.+?)(?:\n|$)", text, re.DOTALL
            )
            if reason_match and changes_match:
                return PythonJudgeResponse(
                    status=status,
                    answer="",
                    reason=reason_match.group(1).strip(),
                    changes=changes_match.group(1).strip(),
                )
        except Exception:
            pass

        # If no REASON/CHANGES, look for ANSWER
        try:
            answer_match = re.search(r"ANSWER:\s*(.+?)(?:\n|$)", text)
            if answer_match:
                return PythonJudgeResponse(
                    status=status,
                    answer=answer_match.group(1).strip(),
                    reason="",
                    changes="",
                )
        except Exception:
            pass

        raise ValueError(
            "Response must contain either ANSWER or both REASON and CHANGES"
        )

    def __judge_response(
        self,
        context: Context,
        task: str,
        response: PythonBackendResponse,
        output: PythonOutput,
    ) -> PythonJudgeResponse:
        output_block = ""
        if output.exception:
            output_block = f"Exception thrown:\n"
            output_block += f"{output.exception.__class__.__name__}: "
            output_block += f"{str(output.exception)}\n"
            output_block += "".join(
                traceback.format_tb(output.exception.__traceback__)
            )
        else:
            if output.output is None:
                output_block = "No output"
            else:
                output_block = output.output

        prompt = self.__judge_template.render(
            {
                "code": self.__dict_to_code_blocks(response.code),
                "output": output_block,
                "task": task,
                "stdout": output.stdout,
                "stderr": output.stderr,
            }
        )

        raw_response = self.llm(context, prompt)

        response = self.__parse_judge_response(raw_response)

        return response

    def invoke(
        self,
        context: Context,
        args: Dict[str, Any],
        max_steps: Optional[int] = None,
        stop_at_first_tool: bool = False,
    ) -> str:
        task = args["task"]
        self._initialize_state(context)

        steps = 0

        with PythonEnv(tools=self.tools.values()) as env:
            while True:
                steps += 1
                if max_steps and steps > max_steps:
                    raise Exception("too many steps")

                context.broadcast(AgentBackendStep(steps))

                if max_steps and steps > max_steps:
                    raise Exception("too many steps")

                # Build prompt
                prompt = self.prepare_prompt(context, **args)
                context.broadcast(AgentPrompt(prompt))

                code = None
                code_attempts = 0
                while not code:
                    raw_response = self.query_model(context, prompt)

                    response = self.parse_response(context, raw_response)

                    if (
                        response.code
                        and "main.py" in response.code
                        and "main" in response.code["main.py"]
                    ):
                        break
                    else:
                        code_attempts += 1
                        if (
                            self.__retry_code_attempts > 0
                            and code_attempts > self.__retry_code_attempts
                        ):
                            raise Exception(
                                (
                                    "too many attempts to get executable code "
                                    "output"
                                )
                            )

                if "responses" not in context:
                    context["responses"] = []

                context["responses"].append(response)

                context.broadcast(AgentLLMResponse(response))

                if "code" not in context:
                    context["code"] = []
                context["code"].append(response.code)

                output, exception, stdout, stderr = env.execute(
                    response.code,
                    context=context,
                )

                results = PythonOutput(
                    output=output,
                    exception=exception,
                    stdout=stdout,
                    stderr=stderr,
                )

                if "outputs" not in context:
                    context["outputs"] = []

                context["outputs"].append(results)

                judgement = self.__judge_response(
                    context, task, response, results
                )

                if "judgements" not in context:
                    context["judgements"] = []
                context["judgements"].append(judgement)

                if "complete" in judgement.status.lower():
                    return judgement.answer
