from datetime import datetime
from typing import Dict, List, Optional, Union

from arkaine.flow.linear import Linear
from arkaine.flow.parallel_list import ParallelList
from arkaine.llms.llm import LLM, Prompt
from arkaine.toolbox.research.finding import Finding
from arkaine.tools.abstract import AbstractAgent
from arkaine.tools.argument import Argument
from arkaine.tools.context import Context
from arkaine.tools.events import Event
from arkaine.tools.result import Result
from arkaine.utils.parser import Label, Parser
from arkaine.utils.resource import Resource
from arkaine.utils.templater import PromptLoader


class QueryGenerator(AbstractAgent):

    _rules = {
        "args": {
            "required": [
                Argument(
                    name="topic",
                    description="The topic to research",
                    type="str",
                    required=True,
                )
            ],
        },
        "result": {
            "required": ["list[str]"],
        },
    }


class ResourceJudge(AbstractAgent):

    _rules = {
        "args": {
            "required": [
                Argument(
                    name="topic",
                    description="The topic to research",
                    type="str",
                    required=True,
                ),
                "resources",
            ],
        },
    }


class DefaultResourceJudge(ResourceJudge):
    """
    DefaultResourceJudge is a tool that is utilized to judge a list of resources
    based on a given query/topic/task. It is fed a query/topic/task and a list
    of resources and their descriptions, and it determines which of those
    resources are likely to contain useful information.

    Args:
        llm (LLM): The LLM to use
    """

    def __init__(self, llm: LLM):
        super().__init__(
            name="resource_query_judge",
            description="Given a query/topic/task, and a series "
            + "of resources and their descriptions, determine which of "
            + "those resources are likely to contain useful information.",
            args=[
                Argument(
                    "topic",
                    "The query/topic/task to try to research",
                    "str",
                    required=True,
                ),
                Argument(
                    "resources",
                    "A list of resources to judge",
                    "list[Resource]",
                    required=True,
                ),
            ],
            llm=llm,
            examples=[],
            result=Result(
                description="A list of filtered resources that are likely "
                + "to contain useful information",
                type="list[Resource]",
            ),
        )

        self.__parser = Parser(
            [
                Label(name="resource", required=True, is_block_start=True),
                Label(name="reason", required=True),
                Label(name="recommend", required=True),
            ]
        )

    def prepare_prompt(
        self, context: Context, topic: str, resources: List[Resource]
    ) -> List[Dict[str, str]]:
        context["resources"] = {resource.id: resource for resource in resources}
        resources_str = "\n\n".join([str(resource) for resource in resources])

        prompt = PromptLoader.load_prompt("researcher").render(
            {
                "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

        query_judge_prompt = PromptLoader.load_prompt("resource_judge").render(
            {
                "topic": topic,
                "resources": resources_str,
            }
        )

        prompt.extend(query_judge_prompt)

        return prompt

    def extract_result(self, context: Context, output: str) -> List[Resource]:
        labels, _ = self.__parser.parse_blocks(output)
        resources = []

        context["parsed_resource_judgements"] = labels

        for label in labels:
            id = label["resource"]

            recommend = label["recommend"]

            # Find the resource from the original context.
            # If the resource is not found, it is a hallucinated resource
            # and thus we shouldn't recommend it.
            if id not in context["resources"]:
                if "hallucinated_resources" not in context:
                    context["hallucinated_resources"] = {}
                context["hallucinated_resources"][id] = label
                continue
            else:
                resource = context["resources"][id]

            if recommend.strip().lower() == "yes":
                resources.append(resource)

        return resources


class ResourceSearch(AbstractAgent):

    _rules = {
        "args": {
            "required": [
                Argument(
                    name="topic",
                    description="The topic to research",
                    type="str",
                    required=True,
                )
            ],
        },
        "result": {
            "required": ["list[Resource]"],
        },
    }


class FindingsGenerator(AbstractAgent):
    _rules = {
        "args": {
            "required": [
                Argument(
                    name="topic",
                    description="The topic to research",
                    type="str",
                    required=True,
                ),
                Argument(
                    name="resource",
                    description="The content to generate findings from",
                    type="Resource",
                    required=True,
                ),
            ],
        },
        "result": {
            "required": ["list[Finding]"],
        },
    }


class GenerateFinding(FindingsGenerator):
    """
    GenerateFinding is a tool that is utilized to generate findings from a given
    corpus of content. It is fed a singular resource and the topic to
    focus/research on.

    Args:
        llm (LLM): The LLM to use for the generate finding tool; only used if
            max_learnings is not provided
        name (str): The name of the generate finding tool; defaults to
            "generate_findings"
        description (str): The description of the generate finding tool;
            defaults to "Generate findings from a given content and query"
        max_learnings (int): The maximum number of learnings to generate;
            defaults to 5
        id (str): The id of the generate finding tool; defaults to None

    Returns:
        list[Finding]: A list of findings, which gives a source and important
            information found within.
    """

    def __init__(
        self,
        llm: LLM,
        max_learnings: int = 5,
        name: Optional[str] = None,
        description: Optional[str] = None,
        id: Optional[str] = None,
    ):
        if description is None:
            description = "Generate findings from a given content and query"

        super().__init__(
            name="generate_findings",
            description=description,
            args=[
                Argument(
                    "topic",
                    "The topic to research",
                    "str",
                ),
                Argument(
                    "resource",
                    "The content to generate findings from",
                    "Resource",
                ),
            ],
            llm=llm,
            result=Result(
                description="A list of findings, which gives a source and "
                + "important information found within.",
                type="list[Finding]",
            ),
            id=id,
        )

        self.__max_learnings = max_learnings
        self.__parser = Parser(
            [
                Label(name="summary", required=True, is_block_start=True),
                Label(name="finding", required=True),
            ]
        )

    def prepare_prompt(
        self, context: Context, topic: str, resource: Resource
    ) -> Prompt:
        try:
            # TODO incorporate pagination, not needing to load
            # resource into memory?
            content = (
                f"{resource.name}\n\t-{resource.source}\n"
                f"\n{resource.content[0:25_000]}\n\n"
            )
        except Exception as e:
            raise e

        prompt = PromptLoader.load_prompt("researcher").render(
            {
                "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

        prompt.extend(
            PromptLoader.load_prompt("generate_findings").render(
                {
                    "content": content,
                    "query": topic,
                    "max_learnings": self.__max_learnings,
                }
            )
        )

        return prompt

    def extract_result(self, context: Context, output: str) -> List[Finding]:
        labels, _ = self.__parser.parse_blocks(output)

        resource: Resource = context.args["resource"]

        findings: List[Finding] = []
        for label in labels:
            try:
                summary = label["summary"]
                content = label["finding"]
                findings.append(Finding(resource, summary, content))
            except Exception:  # NOQA
                continue

        # Attempt to broadcast the findings via the researcher, which should be
        # the parent's parent (generatefindings->parallellist->researcher)
        try:
            context.parent.parent.broadcast(
                FindingsGeneratedEvent(self, findings)
            )
        except Exception:
            pass

        return findings


class Researcher(Linear):
    """
    Researcher is a tool that is utilized to answer a single question.
    To do so, it follows the process of:

    1. Generate a set of queries to search for
    2. Perform the search across a set of Resources
    3. Judge the relevance of the Resources before consuming them
    4. Generate Findings from each Resources

    To call the researcher, you simply provide a topic to research. Note that
    the topic should be specific, detailed, and accurately describe the
    information desired. It may be wise to utilize an other agent to expand the
    topic into a more specific question. In short, do *not* treat it like a web
    search query
    IE:

    Bad: "stock trading strategies"
    Good: "Compare common long-term stock trading strategies for average middle
        class investors, while discussing the potential risks and upsides of
        each strategy."

    Args:
        name (str): The name of the researcher; defaults to "researcher"
        description (str): The description of the researcher
        llm: The LLM to use for the researcher; only used if query_generator,
            search_resources, or judge_resources are not provided
        query_generator: The query generator to use for the researcher;
            defaults to QueryGenerator(llm)
        search_resources: The resource search to use for the researcher;
            this must be provided, as it determines where the researcher
            will search for information
        judge_resources: The resource judge to use for the researcher;
            defaults to DefaultResourceJudge(llm)
        generating_findings: The findings generator to use for the researcher;
            defaults to GenerateFinding(llm)
        max_learnings (int): The maximum number of learnings to generate
            per resource; defaults to 5
        max_workers (int): The maximum number of workers to use for the
            researcher; defaults to 10
        id (str): The id of the researcher; defaults to None
    """

    def __init__(
        self,
        name: str = "researcher",
        description: Optional[str] = None,
        llm: Optional[LLM] = None,
        query_generator: Optional[QueryGenerator] = None,
        search_resources: Optional[ResourceSearch] = None,
        judge_resources: Optional[ResourceJudge] = None,
        generating_findings: Optional[FindingsGenerator] = None,
        max_learnings: int = 5,
        max_workers: int = 10,
        id: Optional[str] = None,
    ):
        self._query_generator = query_generator

        if judge_resources is None:
            if llm is None:
                raise ValueError(
                    "llm is required if judge_resources is not provided"
                )
            judge_resources = DefaultResourceJudge(llm)

        if search_resources is None:
            raise ValueError("search_resources is required")

        self._resource_search = ParallelList(
            search_resources,
            max_workers=max_workers,
            result_formatter=self._batch_resources,
        )

        if generating_findings is None:
            if llm is None:
                raise ValueError(
                    "llm is required if generating_findings is not provided"
                )
            generating_findings = GenerateFinding(llm, max_learnings)

        self._finding_generation = ParallelList(
            generating_findings,
            max_workers=max_workers,
            error_strategy="ignore",
            result_formatter=self._combine_findings,
        )
        self._resource_judge = ParallelList(
            judge_resources,
            max_workers=max_workers,
            error_strategy="ignore",
            result_formatter=self._combine_resources,
        )

        self._max_learnings = max_learnings

        args = [
            Argument(
                name="topic",
                description=(
                    "The question to research; ensure you are "
                    "specific, detailed, and concise in asking "
                    "your question/topic. Ask for specifically "
                    "what you want researched to avoid general "
                    "responses."
                ),
                type="str",
                required=True,
            ),
        ]

        if description is None:
            description = (
                "A researcher that can search for information across a "
                "set of resources and generate findings from the content "
                "of those resources."
            )

        super().__init__(
            name,
            description=description,
            arguments=args,
            examples=[],
            steps=[
                self._query_generator,
                self._resource_search,
                self._resource_judge,
                self._finding_generation,
            ],
            id=id,
            result=Result(
                description=(
                    "A list of findings, which gives a source and "
                    "important information found within."
                ),
                type="list[Finding]",
            ),
        )

    def _batch_resources(
        self, context: Context, resource_lists: List[List[Resource]]
    ) -> List[List[Resource]]:
        topic = context.parent.args["topic"]
        queries = [i["query"] for i in context.args["input"]]
        [
            context.parent.broadcast(
                ResearchQueryEvent(context.parent.attached, query)
            )
            for query in queries
        ]

        unique_resources = list(
            {
                r.source: r
                for resource_list in resource_lists
                for r in resource_list
            }.values()
        )

        [
            context.parent.broadcast(
                ResourceFoundEvent(context.parent.attached, resource)
            )
            for resource in unique_resources
        ]

        resource_groups = [
            unique_resources[i : i + 10]
            for i in range(0, len(unique_resources), 10)
        ]

        return {"topic": topic, "resources": resource_groups}

    def _combine_resources(
        self, context: Context, resource_lists: List[List[Resource]]
    ) -> List[Resource]:
        return {
            "topic": context.parent.args["topic"],
            "resources": [
                r for resource_list in resource_lists for r in resource_list
            ],
        }

    def _combine_findings(
        self, context: Context, findings: List[List[Finding]]
    ) -> List[Finding]:
        # Since the parallel list can return exceptions, and we ignore them
        # for individual finding generations (as the source may prevent
        # scraping, or have an issue, etc).
        findings = [
            finding
            for sublist in findings
            if isinstance(sublist, list)
            for finding in sublist
            if isinstance(finding, Finding)
        ]

        return findings


class ResearchQueryEvent(Event):
    """
    ResearchQueryEvent is an event that is utilized to notify when a research
    query is searched for.
    """

    def __init__(self, researcher: Union[str, Researcher], query: str):
        if isinstance(researcher, Researcher):
            researcher = researcher.id
        super().__init__(
            ResearchQueryEvent,
            {
                "researcher": researcher,
                "query": query,
            },
        )

    @classmethod
    def type(self) -> str:
        return "research_query"


class ResourceFoundEvent(Event):
    """
    ResourceFoundEvent is an event that is utilized to notify when a resource
    is found.
    """

    def __init__(self, researcher: Union[str, Researcher], resource: Resource):
        if isinstance(researcher, Researcher):
            researcher = researcher.id
        super().__init__(
            ResourceFoundEvent,
            {
                "researcher": researcher,
                "resource": resource,
            },
        )

    @classmethod
    def type(self) -> str:
        return "resource_found"


class FindingsGeneratedEvent(Event):
    """
    FindingsGeneratedEvent is an event that is utilized to notify when a finding
    is generated.
    """

    def __init__(
        self, researcher: Union[str, Researcher], findings: List[Finding]
    ):
        if isinstance(researcher, Researcher):
            researcher = researcher.id
        super().__init__(
            FindingsGeneratedEvent,
            {
                "researcher": researcher,
                "findings": findings,
            },
        )

    @classmethod
    def type(self) -> str:
        return "findings_generated"
