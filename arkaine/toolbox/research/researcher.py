from typing import Dict, List, Optional, Set

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

        prompt = PromptLoader.load_prompt("researcher.prompt")

        query_judge_prompt = PromptLoader.load_prompt(
            "resource_judge.prompt"
        ).render(
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
                f"{resource.title}\n\t-{resource.source}\n"
                f"\n{resource.content[0:25_000]}"
            )
        except Exception as e:
            print(f"Error getting markdown from {resource.source}: {e}")
            raise e

        prompt = PromptLoader.load_prompt("researcher")

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
        )
        self._finding_generation = ParallelList(
            GenerateFinding(llm, max_learnings),
            max_workers=max_workers,
        )
        self._resource_judge = ParallelList(
            judge_resources,
            max_workers=max_workers,
        )

        self._max_learnings = max_learnings

        args = [
            Argument(
                name="topic",
                description=(
                    "The topic to research - be as specific as possible"
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
                # We are breaking down the resources into smaller chunks
                # to avoid overloading the LLM with too much; too many entries
                # degrades performance.
                self._group_resources,
                self._resource_judge,
                # Again - batching resources
                self._group_resources,
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

    def _generate_queries(self, context: Context, topic: str) -> List[str]:
        return self._query_generator(
            context, topic, num_queries=self._generate_queries
        )

    def _group_resources(
        self, context: Context, resources: List[List[Resource]]
    ) -> List[List[Resource]]:
        seen_resources: Set[str] = set()
        for group in resources:
            for r in group:
                if r.id in seen_resources:
                    continue
                else:
                    seen_resources.add(r.id)

        return [
            seen_resources[i : i + 10]
            for i in range(0, len(seen_resources), 10)
        ]
