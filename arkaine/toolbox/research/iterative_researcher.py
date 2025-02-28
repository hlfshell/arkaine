from datetime import datetime
from time import time
from typing import Dict, List, Optional

from arkaine.flow import DoWhile, ParallelList
from arkaine.internal.parser import Label, Parser
from arkaine.llms.llm import LLM, Prompt
from arkaine.toolbox.research.finding import Finding
from arkaine.toolbox.research.researcher import Researcher
from arkaine.toolbox.research.web_research import WebResearcher
from arkaine.tools.abstract import AbstractAgent
from arkaine.tools.argument import Argument
from arkaine.tools.result import Result
from arkaine.tools.tool import Context
from arkaine.utils.templater import PromptLoader


class QuestionGenerator(AbstractAgent):
    """
    Abstract base class for agents that generate follow-up questions based on
    existing research findings.

    Any subclass must implement:
        - prepare_prompt(self, context: Context, **kwargs) -> Prompt
        - extract_result(self, context: Context, output: str) -> List[str]
    """

    _rules = {
        "args": {
            "required": [
                Argument(
                    name="questions",
                    description="Questions that have already been researched",
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
            "allowed": [],
        },
        "result": {
            "required": ["list[str]"],
        },
    }


class DefaultQuestionGenerator(QuestionGenerator):
    def __init__(self, llm: LLM):
        super().__init__(
            name="GenerateQuestions",
            description="Generate a list of questions to research a topic.",
            args=[
                Argument(
                    name="questions",
                    description="Questions that have already been researched",
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
            llm=llm,
        )

        self.__parser = Parser(
            [
                Label("reason", required=True, data_type="str"),
                Label("question", required=True, data_type="str"),
            ]
        )

    def prepare_prompt(
        self,
        context: Context,
        questions: List[str],
        findings: List[Finding],
    ) -> Prompt:
        base = PromptLoader.load("researcher")
        questions = PromptLoader.load("generate_questions")

        prompt = base.render(
            {
                "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

        prompt.extend(
            questions.render(
                {
                    "topic": questions[0],
                    "questions": questions[1:],
                    "findings": findings,
                }
            )
        )

        return prompt

    def extract_result(self, context: Context, output: str) -> List[str]:
        if output.strip().lower() == "NONE":
            return []

        parsed: List[Dict] = self.__parser.parse_blocks(output, "reason")

        output = []

        # Place into output a dict of { "reason": reason, "question": question }
        for block in parsed:
            if block["errors"]:
                continue

            output.append(
                {
                    "reason": block["data"]["reason"],
                    "question": block["data"]["question"],
                }
            )

        context["questions"] = output

        return [output["question"] for output in output]


class IterativeResearcher(DoWhile):
    """
    A "deep" iterative researcher that:
      • Takes an initial list of questions.
      • For each question, runs a researcher (e.g., WebResearcher) to get
        findings.
      • Proposes follow-up questions based on existing findings to research
        further.
      • Repeats until:
         (1) no more questions remain,
         (2) maximum depth is reached, or
         (3) maximum allotted time is exceeded.
      • Returns all collected findings.

    Args:
        name (str): Deep researcher tool name.
        llm (LLM): Large Language Model for generating follow-up questions,
            etc.
        max_depth (int): Maximum number of iterations/depth. Default is 3.
        max_time_seconds (int): Maximum total time in seconds to run the loop.
            Default is depth * 120 seconds (2 minutes per depth).
        researcher (Optional[Researcher]): The researcher tool
            to run on each question. Defaults to a standard WebResearcher if
            not provided.
        questions_generator (Optional[GenerateQuestions]): Agent that suggests
            additional research questions based on current findings.
        id (Optional[str]): Optional custom ID for the tool.
    """

    def __init__(
        self,
        llm: LLM,
        name: str = "iterative_researcher",
        max_depth: int = 3,
        max_time_seconds: int = 600,
        researcher: Optional[Researcher] = None,
        questions_generator: Optional[DefaultQuestionGenerator] = None,
        id: Optional[str] = None,
    ):
        # If the user didn't pass their own "GenerateQuestions" agent, default
        # to it
        if questions_generator is None:
            questions_generator = DefaultQuestionGenerator(llm)

        self._llm = llm
        if researcher is None:
            # If the user didn't pass a specialized researcher, default to
            # WebResearcher
            researcher = WebResearcher(llm=llm)
        else:
            researcher = researcher

        self.__researcher = ParallelList(
            tool=researcher,
            name=f"{name}_researchers_parallel",
            description="A set of researchers to study each question passed",
            result_formatter=self._format_findings,
        )

        self._generate_questions = questions_generator

        self.max_depth = max_depth
        self.max_time_seconds = max_time_seconds
        self.start_time = None

        args = [
            Argument(
                name="questions",
                description=(
                    "A list of questions to start the research with, where "
                    "each question is a thoroughly prescribed question to "
                    "research. Ensure that each question is a single, highly "
                    "descriptive target to research and explain."
                ),
                type="list[str]",
                required=True,
            ),
        ]

        super().__init__(
            tool=self._execute_research_cycle,
            stop_condition=self._should_stop,
            args=args,
            prepare_args=self._prepare_args,
            format_output=None,
            name=name,
            description=(
                "A deep iterative researcher that uses an underlying "
                "researcher to gather findings from each question in "
                "a loop, then uses a GenerateQuestions agent to "
                "propose follow-up questions, until no more questions "
                "remain or the depth/time constraints are met."
            ),
            max_iterations=self.max_depth + 1,  # Should never be hit
            examples=[],
            id=id,
        )

    def _format_findings(
        self, context: Context, output: List[List[Finding]]
    ) -> List[Finding]:
        """
        Format the findings from the Branch tool into a list of Findings.
        """
        # Ensure that each list is actually a list, and that they contain
        # Findings and not some other element. Combine into a singular list
        # of Findings.
        findings = []
        for finding_list in output:
            if not isinstance(finding_list, list):
                continue
            elif len(finding_list) == 0:
                continue
            elif not isinstance(finding_list[0], Finding):
                continue
            findings.extend(finding_list)
        return findings

    def _execute_research_cycle(
        self, context: Context, questions: List[str]
    ) -> List[Finding]:
        """
        This function is called once per iteration of the DoWhile loop:
          1) Takes all current questions from context["questions"].
          2) Runs the researcher(s) to gather new findings for all questions
            in parallel.
          3) Appends those findings to context["all_findings"].
          4) Uses generate_questions to propose follow-up questions based on
            all known findings.
          5) Appends any newly generated questions to context["questions"],
            unless depth is about to exceed.
        """
        # Initialize start time on first execution
        if self.start_time is None:
            self.start_time = time()

        # Initialize findings list in context if not present
        context.init("findings", [])
        context.init("all_questions", [])

        # No questions are asked, we're done
        if len(questions) == 0:
            return context["findings"]

        # Track all questions we've researchered
        print("Executing research cycle")
        context.concat("all_questions", questions)

        findings = self.__researcher(context, topics=questions)

        print(f"Findings: {len(findings)}")

        # Add new findings to our collection
        context.concat("findings", findings)

        return context["findings"]

    def _should_stop(self, context: Context, output):
        """
        This condition is checked after each iteration. We want to stop if:
          1) No more questions remain.
          2) We have reached max_depth.
          3) We have exceeded max_time_seconds.
        If any of these are true, return True => stop. Otherwise, continue.
        """
        # First, we determine if our depth is about to exceed the max
        if context["iteration"] >= self.max_depth:
            return True

        # If we've exceeded total time
        elapsed = time() - self.start_time
        if elapsed >= self.max_time_seconds:
            return True

        # If there are no more questions to process
        next_questions = self._generate_questions(
            context,
            context.get("all_questions", []),
            context.get("findings", []),
        )

        if len(next_questions) == 0:
            return True

        # Store the next questions for prepare_args to use
        context["next_questions"] = next_questions

        # Otherwise, continue
        return False

    def _prepare_args(self, context: Context, args):
        """
        prepare_args is called just before each iteration in the DoWhile loop.
        We are looking to prepare the next set of questions for each iteration.

        """

        if context["iteration"] == 1:
            # First iteration, use the initial questions
            args = args
        else:
            # Use the questions generated in _should_stop
            args = {"questions": context.get("next_questions", [])}

        return {
            "topics": args["questions"],
        }
