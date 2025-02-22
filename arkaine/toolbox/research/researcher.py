from datetime import datetime
from typing import Dict, List, Optional

from arkaine.flow.linear import Linear
from arkaine.flow.parallel_list import ParallelList
from arkaine.internal.parser import Label, Parser
from arkaine.llms.llm import LLM, Prompt
from arkaine.toolbox.research.finding import Finding
from arkaine.tools.abstract import AbstractAgent
from arkaine.tools.agent import Agent
from arkaine.tools.argument import Argument
from arkaine.tools.context import Context
from arkaine.tools.result import Result
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
                Label(name="resource", required=True),
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
        labels = self.__parser.parse_blocks(output, "resource")
        resources = []

        context["parsed_resource_judgements"] = labels

        for label in labels:
            if label["errors"]:
                continue

            id = label["data"]["resource"]
            if len(id) == 0:
                continue
            else:
                id = id[0].strip()

            recommend = label["data"]["recommend"]
            if len(recommend) == 0:
                continue
            else:
                recommend = recommend[0].strip()

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


class GenerateFinding(Agent):

    def __init__(self, llm: LLM, max_learnings: int = 5):
        super().__init__(
            name="generate_findings",
            description="Generate findings from a given content and query",
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
        )

        self.__max_learnings = max_learnings
        self.__parser = Parser(
            [
                Label(name="summary", required=True),
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
        labels = self.__parser.parse_blocks(output, "summary")

        resource: Resource = context.args["resource"]
        source = f"{resource.name} - {resource.source}"

        findings: List[Finding] = []
        for label in labels:
            if label["errors"]:
                continue

            summary = label["data"]["summary"]
            content = label["data"]["finding"]
            findings.append(Finding(source, summary, content))

        return findings


class Researcher(Linear):
    def __init__(
        self,
        llm: LLM,
        description: str,
        name: str = "researcher",
        query_generator: QueryGenerator = None,
        search_resources: ResourceSearch = None,
        judge_resources: Optional[ResourceJudge] = None,
        max_learnings: int = 5,
        max_workers: int = 10,
        id: str = None,
    ):
        self._llm = llm
        self._query_generator = query_generator

        if judge_resources is None:
            judge_resources = DefaultResourceJudge(llm)

        self._resource_search = ParallelList(
            search_resources,
            max_workers=max_workers,
            result_formatter=self._batch_resources,
        )
        self._finding_generation = ParallelList(
            GenerateFinding(llm, max_learnings),
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
                    "your question/topic."
                ),
                type="str",
                required=True,
            ),
        ]

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

        unique_resources = list(
            {
                r.source: r
                for resource_list in resource_lists
                for r in resource_list
            }.values()
        )

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
        return [
            finding
            for sublist in findings
            if isinstance(sublist, list)
            for finding in sublist
            if isinstance(finding, Finding)
        ]
