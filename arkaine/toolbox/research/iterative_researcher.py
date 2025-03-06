from datetime import datetime
from time import time
from typing import Dict, List, Optional

from arkaine.flow import DoWhile, ParallelList
from arkaine.llms.llm import LLM, Prompt
from arkaine.toolbox.research.finding import Finding
from arkaine.toolbox.research.researcher import Researcher
from arkaine.toolbox.research.web_research import WebResearcher
from arkaine.tools.abstract import AbstractAgent
from arkaine.tools.argument import Argument
from arkaine.tools.result import Result
from arkaine.tools.tool import Context
from arkaine.utils.parser import Label, Parser
from arkaine.utils.templater import PromptLoader


class TopicGenerator(AbstractAgent):
    """
    Abstract base class for agents that generate follow-up topics based on
    existing research findings.

    Any subclass must implement:
        - prepare_prompt(self, context: Context, **kwargs) -> Prompt
        - extract_result(self, context: Context, output: str) -> List[str]
    """

    _rules = {
        "args": {
            "required": [
                Argument(
                    name="topics",
                    description="Topics that have already been researched",
                    type="list[str]",
                    required=True,
                ),
                Argument(
                    name="findings",
                    description=(
                        "Findings that have already been researched, "
                        "from which we can generate follow up topics."
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


class DefaultTopicGenerator(TopicGenerator):
    def __init__(self, llm: LLM):
        super().__init__(
            name="GenerateTopics",
            description="Generate a list of topics to research.",
            args=[
                Argument(
                    name="topics",
                    description="Topics that have already been researched",
                    type="list[str]",
                    required=True,
                ),
                Argument(
                    name="findings",
                    description=(
                        "Findings that have already been researched, "
                        "from which we can generate follow up topics."
                    ),
                    type="list[Finding]",
                    required=True,
                ),
            ],
            result=Result(
                type="list[str]",
                description="List of generated topics",
            ),
            llm=llm,
        )

        self.__parser = Parser(
            [
                Label(
                    "reason",
                    required=True,
                    data_type="str",
                    is_block_start=True,
                ),
                Label("topic", required=True, data_type="str"),
            ]
        )

    def prepare_prompt(
        self,
        context: Context,
        topics: List[str],
        findings: List[Finding],
    ) -> Prompt:
        base = PromptLoader.load_prompt("researcher")
        topics_prompt = PromptLoader.load_prompt("generate_topics")

        prompt = base.render(
            {
                "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

        prompt.extend(
            topics_prompt.render(
                {
                    "topic": topics[0],
                    "generated_topics": topics[1:],
                    "findings": findings,
                }
            )
        )

        return prompt

    def extract_result(self, context: Context, output: str) -> List[str]:
        if output.strip().lower() == "NONE":
            return []

        parsed: List[Dict]
        parsed, _ = self.__parser.parse_blocks(output)

        output = []

        # Place into output a dict of { "reason": reason, "topic": topic }
        for block in parsed:
            if len(block["topic"]) == 0:
                continue

            if len(block["reason"]) == 0:
                continue

            output.append(
                {
                    "reason": block["reason"].strip(),
                    "topic": block["topic"].strip(),
                }
            )

        context["topics"] = output

        return [output["topic"] for output in output]


class IterativeResearcher(DoWhile):
    """
    A "deep" iterative researcher that:
      • Takes an initial list of topics.
      • For each topic, runs a researcher (e.g., WebResearcher) to get
        findings.
      • Proposes follow-up topics based on existing findings to research
        further.
      • Repeats until:
         (1) no more topics remain,
         (2) maximum depth is reached, or
         (3) maximum allotted time is exceeded.
      • Returns all collected findings.

    Args:
        name (str): Deep researcher tool name.
        llm (LLM): Large Language Model for generating follow-up topics,
            etc.
        max_depth (int): Maximum number of iterations/depth. Default is 3.
        max_time_seconds (int): Maximum total time in seconds to run the loop.
            Default is depth * 120 seconds (2 minutes per depth).
        researcher (Optional[Researcher]): The researcher tool
            to run on each topic. Defaults to a standard WebResearcher if
            not provided.
        topic_generator (Optional[DefaultTopicGenerator]): Agent that
            suggests additional research topics based on current findings.
        id (Optional[str]): Optional custom ID for the tool.
    """

    def __init__(
        self,
        llm: LLM,
        name: str = "iterative_researcher",
        max_depth: int = 3,
        max_time_seconds: int = 600,
        researcher: Optional[Researcher] = None,
        topic_generator: Optional[DefaultTopicGenerator] = None,
        id: Optional[str] = None,
    ):
        # If the user didn't pass their own "GenerateTopics" agent, default
        # to it
        if topic_generator is None:
            topic_generator = DefaultTopicGenerator(llm)

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
            description="A set of researchers to study each topic passed",
            result_formatter=self._format_findings,
        )

        self._generate_topics = topic_generator

        self.max_depth = max_depth
        self.max_time_seconds = max_time_seconds

        args = [
            Argument(
                name="topics",
                description=(
                    "A list of topics to start the research with, where "
                    "each topic is a thoroughly prescribed topic to "
                    "research. Ensure that each topic is a single, highly "
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
                "researcher to gather findings from each topic in "
                "a loop, then uses a GenerateTopics agent to "
                "propose follow-up topics, until no more topics "
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
        self, context: Context, topics: List[str]
    ) -> List[Finding]:
        """
        This function is called once per iteration of the DoWhile loop:
          1) Takes all current topics from context["topics"].
          2) Runs the researcher(s) to gather new findings for all topics
            in parallel.
          3) Appends those findings to context["all_findings"].
          4) Uses generate_topics to propose follow-up topics based on
            all known findings.
          5) Appends any newly generated topics to context["topics"],
            unless depth is about to exceed.
        """
        # Since _execute_research is toolified and thus its own context,
        # we grab the parent context to reference the iterative researcher's
        # context.
        ctx = context.parent
        # Initialize start time on first execution
        ctx.init("researcher_start_time", time())

        # Initialize findings list in context if not present
        ctx.init("findings", [])
        ctx.init("all_topics", [])

        # No topics are asked, we're done
        if len(topics) == 0:
            return ctx["findings"]

        # Track all topics we've researched
        ctx.concat("all_topics", topics)

        findings = self.__researcher(context, topics=topics)

        # Add new findings to our collection
        ctx.concat("findings", findings)

        return ctx["findings"]

    def _should_stop(self, context: Context, output):
        """
        _should_stop is checked after each iteration. We want to stop if:
          1) No more topics remain.
          2) We have reached max_depth.
          3) We have exceeded max_time_seconds.
        If any of these are true, return True => stop. Otherwise, continue.
        """
        # First, we determine if our depth is about to exceed the max
        if context["iteration"] >= self.max_depth:
            return True

        # If we've exceeded total time
        elapsed = time() - context["researcher_start_time"]
        if elapsed >= self.max_time_seconds:
            return True

        # If there are no more topics to process
        next_topics = self._generate_topics(
            context,
            context.get("all_topics", []),
            context.get("findings", []),
        )

        if len(next_topics) == 0:
            return True

        # Store the next topics for prepare_args to use
        context["next_topics"] = next_topics

        # Otherwise, continue
        return False

    def _prepare_args(self, context: Context, args):
        if context["iteration"] == 1:
            if isinstance(args["topics"], str):
                args["topics"] = [args["topics"]]
            return args
        else:
            return {"topics": context.get("next_topics", [])}
