import os
import pathlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable, Dict, List, Optional
from uuid import uuid4

from arkaine.flow import DoWhile, Linear
from arkaine.flow.parallel_list import ParallelList
from arkaine.internal.parser import Label, Parser
from arkaine.llms.llm import LLM, Prompt
from arkaine.toolbox.webqueryer import Webqueryer
from arkaine.toolbox.websearch import Websearch
from arkaine.tools.agent import Agent
from arkaine.tools.argument import Argument
from arkaine.tools.context import Context
from arkaine.tools.result import Result
from arkaine.tools.tool import Tool
from arkaine.utils.resource import Resource
from arkaine.utils.templater import PromptTemplate, PromptLoader
from arkaine.utils.website import Website
from arkaine.toolbox.research.researcher import Researcher
from arkaine.toolbox.research.finding import Finding


class DeepWebResearcher(DoWhile):
    def __init__(
        self,
        llm: LLM,
        name: str = "researcher",
        depth: Optional[int] = 2,
        queries_per_question: int = 3,
        max_learnings: int = 3,
        proficiency_level: Optional[str] = None,
        id: str = None,
    ):
        super().__init__(
            tool=WebResearcher(
                llm,
                name,
                depth,
                queries_per_question,
                max_learnings,
                proficiency_level,
                id,
            ),
            depth=depth,
            queries_per_question=queries_per_question,
            max_learnings=max_learnings,
            proficiency_level=proficiency_level,
            id=id,
        )


class ResourceQueryJudge(Agent):

    def __init__(self, llm: LLM):
        super().__init__(
            name="resource_query_judge",
            description="Given a query/topic/task, and a series of websites "
            + "and their descriptions, determine which of those sites "
            + "presented are likely to contain useful information.",
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
        )

        self.__template = PromptTemplate.from_file(
            os.path.join(
                pathlib.Path(__file__).parent,
                "prompts",
                "resource_judge.prompt",
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

        prompt = get_base_prompt()

        query_judge_prompt = self.__template.render(
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
                print("HALLUCINATED RESOURCE", id)
                if "hallucinated_resources" not in context:
                    context["hallucinated_resources"] = {}
                context["hallucinated_resources"][id] = label
                continue
            else:
                resource = context["resources"][id]

            if recommend.strip().lower() == "yes":
                resources.append(resource)

        return resources


class ReportGenerator(Agent):
    def __init__(self, llm: LLM):
        super().__init__(
            name="report_generator",
            description="Generate a detailed report from a list of findings",
            args=[
                Argument(
                    "topic",
                    "The topic to research",
                    "str",
                ),
                Argument(
                    "findings",
                    "Findings from which we generate the report from",
                    "list[str]",
                ),
            ],
            llm=llm,
        )

    def prepare_prompt(
        self, context: Context, topic: str, findings: List[Finding]
    ) -> Prompt:
        report_template = PromptLoader.load_prompt("generate_report")
        base_prompt = PromptLoader.load_prompt("researcher")
        prompt = base_prompt.render(
            {
                "now": datetime.now().strftime("%Y-%m-%d"),
                "proficiency_level": "a highly experienced domain expert",
            }
        )
        prompt.extend(
            report_template.render(
                {
                    "topic": topic,
                    "findings": findings,
                    "proficiency": "a highly experienced domain expert",
                }
            )
        )
        return prompt

    def extract_result(self, context: Context, output: str) -> str:
        return output


class WebResearcher(Researcher):

    def __init__(
        self,
        llm: LLM,
        name: str = "web_researcher",
        websearch: Optional[Websearch] = None,
        max_learnings: int = 5,
        max_workers: int = 10,
        id: str = None,
    ):
        if websearch is None:
            websearch = Websearch(provider="bing", limit=20)
        self.__websearch = websearch

        super().__init__(
            llm,
            name,
            query_generator=Webqueryer(llm),
            search_resources=self._serp,
            max_learnings=max_learnings,
            max_workers=max_workers,
            id=id,
        )

    def _serp(self, context: Context, query: str) -> List[Resource]:
        # import pickle

        # If searches.pkl exists, load it
        # if os.path.exists("searches.pkl"):
        #     with open("searches.pkl", "rb") as f:
        #         searches = pickle.load(f)
        #         return searches

        websites = self.__websearch(context, query)

        resources: List[Resource] = []
        for website in websites:
            resources.append(
                Resource(
                    website.url,
                    website.title,
                    "website",
                    website.snippet,
                    website.get_markdown,
                )
            )

        # with open("searches.pkl", "wb") as f:
        #     pickle.dump(resources, f)

        return resources


class WebResearcher2(Tool):
    def __init__(
        self,
        llm: LLM,
        name: str = "researcher",
        depth: Optional[int] = 2,
        queries_per_question: int = 3,
        max_learnings: int = 3,
        proficiency_level: Optional[str] = None,
        id: str = None,
    ):
        self._llm = llm
        self._query_generator = Webqueryer(llm)
        self._parallel_websearch = ParallelList(Websearch())
        # self._parallel_websearch = self.__p_search
        # self.__fc = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))

        self._max_depth = depth
        self._max_learnings = max_learnings
        self._queries_per_question = queries_per_question

        self.__research_template = PromptTemplate.from_file(
            os.path.join(
                pathlib.Path(__file__).parent,
                "prompts",
                "researcher.prompt",
            )
        )
        self.__questions_template = PromptTemplate.from_file(
            os.path.join(
                pathlib.Path(__file__).parent,
                "prompts",
                "generate_questions.prompt",
            )
        )
        self.__findings_template = PromptTemplate.from_file(
            os.path.join(
                pathlib.Path(__file__).parent,
                "prompts",
                "generate_findings.prompt",
            )
        )
        self.__report_template = PromptTemplate.from_file(
            os.path.join(
                pathlib.Path(__file__).parent,
                "prompts",
                "generate_report.prompt",
            )
        )
        self.__threadpool = ThreadPoolExecutor(max_workers=10)

        args = [
            Argument(
                name="topic",
                description="The topic to research",
                type="str",
                required=True,
            )
        ]

        if proficiency_level:
            self.__default_proficiency_level = proficiency_level
        else:
            args.append(
                Argument(
                    name="proficiency",
                    description="The proficiency level of the user",
                    type="str",
                    required=True,
                    default="a highly experienced expert analyst",
                )
            )

        if self._max_depth is None:
            args.append(
                Argument(
                    name="max_depth",
                    description=(
                        "The maximum depth / iterations of research to "
                        "perform"
                    ),
                    type="int",
                    required=False,
                    default=4,
                )
            )

        super().__init__(
            name,
            description=(
                "Research agent is a tool that, given a topic, will repeatedly "
                "search across the web (and other tools) to build a "
                "comprehensive research report."
            ),
            args=args,
            func=self._research,
            id=id,
        )

    def _get_base_prompt(self, context: Context) -> Prompt:
        return self.__research_template.render(
            {
                "now": datetime.now().strftime("%Y-%m-%d"),
                "proficiency_level": context["proficiency_level"],
            }
        )

    def _generate_queries(self, context: Context, topic: str) -> List[str]:
        """
        Given the topic, generate a number of queries to search for
        that will return relevant information.
        """
        return self._query_generator(
            context, topic, num_queries=self._queries_per_question
        )

    def _serp(self, context: Context, topic) -> List[Website]:
        """
        Given the topic, generate a number of queries to search for
        that will return relevant information. then, for each of those
        queries, search the web return the website results.
        """
        with self._init_context_(context, topic):
            queries: List[str] = self._generate_queries(context, topic)
            print("queries", queries)
            query_inputs = [{"query": query} for query in queries]
            results: List[List[Website]] = self._parallel_websearch(
                context, query_inputs
            )
            results = [item for sublist in results for item in sublist]
            print(f"found {len(results)} results")

            # Use a set to track seen URLs for O(1) lookup efficiency
            seen_urls = set()
            websites: List[Website] = []
            already_visited_sites = context["sites"]
            for site in already_visited_sites:
                seen_urls.add(site.url)

            for result in results:
                if result.url not in seen_urls:
                    seen_urls.add(result.url)
                    websites.append(result)

            print(f"found {len(websites)} websites")
            return websites

    def _generate_findings(
        self, context: Context, question: str, sites: List[Website]
    ) -> str:
        print("GEN FINDINGS")
        print("NUM SITES", len(sites))

        def fetch_site_content(site: Website) -> Optional[str]:
            try:
                print("Trying to get ", site.url)
                markdown = site.get_markdown()
                markdown = markdown[0:25_000]
                return f"URL: {site.url}\nTitle: {site.title}\n\n{markdown}---"
            except Exception as e:
                print(f"Error getting markdown from {site.url}: {e}")
                return None

        # Use ThreadPoolExecutor to fetch content in parallel
        content_futures = [
            self.__threadpool.submit(fetch_site_content, site) for site in sites
        ]

        # Collect results and filter out None values from failed fetches
        content_parts = [
            future.result()
            for future in content_futures
            if future.result() is not None
        ]

        # Join all content parts into final content string
        content = "".join(content_parts)

        print("Post sites")
        prompt = self.__findings_template.render(
            {
                "content": content,
                "query": question,
                "max_learnings": self._max_learnings,
            }
        )
        return self._llm(context, prompt)

    def _generate_next_questions(
        self, context: Context, topic: str, questions: List[str], findings: str
    ) -> List[str]:
        questions_text = (
            "You have already searched these followup questions:\n- "
        )
        questions_text += "\n- ".join(questions)

        prompt = self._get_base_prompt(context)
        prompt.extend(
            self.__questions_template.render(
                {
                    "topic": topic,
                    "findings": findings,
                    "questions": questions_text,
                }
            )
        )
        print("PROMPT", prompt)

        output = self._llm(context, prompt)
        print("*" * 100)
        print("RAW OUTPUT")
        print(output)
        print("*" * 100)

        # Parse the output for our questions
        questions = []
        lines = output.strip().split("\n")
        for line in lines:
            # Look for lines starting with a number followed by period or
            # parenthesis
            if any(
                line.strip().startswith(f"{i}." or f"{i})")
                for i in range(1, 10)
            ):
                # Extract the question part after the number
                question = line.split(".", 1)[-1].split(")", 1)[-1].strip()
                if question:  # Only add non-empty questions
                    questions.append(question)

        for question in questions:
            context["questions"].append(question)

        return questions

    def _generate_report(
        self, context: Context, topic: str, findings: List[str]
    ) -> str:
        prompt = self._get_base_prompt(context)
        prompt.extend(
            self.__report_template.render(
                {
                    "topic": topic,
                    "findings": findings,
                    "proficiency": context["proficiency_level"],
                }
            )
        )
        return self._llm(context, prompt)

    def _research(
        self,
        context: Context,
        topic: str,
        proficiency: Optional[str],
        depth: Optional[int] = None,
    ) -> str:
        if depth is None:
            depth = self._max_depth

        context["topic"] = topic
        context["proficiency_level"] = proficiency
        context["questions"] = []
        context["sites"] = []
        context["findings"] = []

        steps = 0
        current_questions: List[str] = [topic]
        findings: List[str] = []
        questions: List[str] = []
        while steps < depth:
            steps += 1
            # Grab all the research data]
            for question in current_questions:
                print("SERP")
                sites = self._serp(context, question)

                # Read the sites, generate findings
                print("GENERATE FINDINGS")
                current_findings = self._generate_findings(
                    context, question, sites
                )
                context.append("findings", current_findings)
                findings.append(current_findings)

            # Given the findings, if we have not reached the depth, generate
            # followup questions
            if steps < depth:
                print("GENERATE NEXT QUESTIONS")
                current_questions = self._generate_next_questions(
                    context, topic, questions, findings
                )
                current_questions = current_questions[0:3]
                print(f"generated {len(current_questions)} questions")
                for question in current_questions:
                    print(f"- {question}")
                questions.extend(current_questions)
                if len(current_questions) == 0:
                    print("NO QUESTIONS")
                    break

        # We have all the findings we need, so let's go ahead and generate a report
        print("GENERATING REPORT")
        report = self._generate_report(context, topic, findings)
        return report


class Research2(Linear):
    def __init__(
        self,
        llm: LLM,
        name: str = "researcher",
        queries_to_generate: int = 3,
        max_learnings: int = 5,
        max_workers: int = 10,
        id: str = None,
    ):
        self._llm = llm
        self._query_generator = Webqueryer(llm)
        self._parallel_websearch = ParallelList(Websearch())
        self._parallel_finding_generation = ParallelList(self._generate_finding)
        self._parallel_resource_judge = ParallelList(ResourceQueryJudge(llm))

        self._max_learnings = max_learnings
        self._queries_to_generate = queries_to_generate

        self.__research_template = PromptTemplate.from_file(
            os.path.join(
                pathlib.Path(__file__).parent,
                "prompts",
                "researcher.prompt",
            )
        )
        self.__findings_template = PromptTemplate.from_file(
            os.path.join(
                pathlib.Path(__file__).parent,
                "prompts",
                "generate_findings.prompt",
            )
        )
        self.__judge_resources_template = PromptTemplate.from_file(
            os.path.join(
                pathlib.Path(__file__).parent,
                "prompts",
                "resource_judge.prompt",
            )
        )

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

        def save(context, resources):
            import pickle

            pickle.dumps(resources)
            with open("resources.pkl", "wb") as f:
                pickle.dump(resources, f)
            raise "saved"

        super().__init__(
            name,
            description=(
                "Research agent is a tool that, given a topic, will repeatedly "
                "search across the web to build a collection of findings."
            ),
            arguments=args,
            examples=[],
            steps=[
                self._generate_queries,
                self._websearch,
                lambda context, resources: [
                    {
                        "topic": context.x["init_input"]["topic"],
                        "resources": resources[i : i + 10],
                    }
                    for i in range(0, len(resources), 10)
                ],
                # save,
                self._parallel_resource_judge,
                lambda context, resources: [
                    {
                        "topic": context.x["init_input"]["topic"],
                        "resources": resources[i : i + 10],
                    }
                    for i in range(0, len(resources), 10)
                ],
                self._parallel_finding_generation,
            ],
            id=id,
            result=Result(
                description=(
                    "A list of findings, which gives a source and "
                    "important information found within."
                ),
                type="list",
            ),
        )

    def _get_base_prompt(self, context: Context) -> Prompt:
        return self.__research_template.render(
            {
                "now": datetime.now().strftime("%Y-%m-%d"),
                "proficiency_level": context["proficiency_level"],
            }
        )

    def _generate_queries(self, context: Context, topic: str) -> List[str]:
        return self._query_generator(
            context, topic, num_queries=self._queries_to_generate
        )

    def _websearch(self, context: Context, topic) -> List[Resource]:
        with self._init_context_(context, topic):
            queries: List[str] = self._generate_queries(context, topic)
            query_inputs = [{"query": query} for query in queries]
            results: List[List[Website]] = self._parallel_websearch(
                context, query_inputs
            )
            print(f"Search found {len(results)} results")
            results = [item for sublist in results for item in sublist]

            seen_urls = set()
            websites: List[Website] = []
            for result in results:
                if result.url not in seen_urls:
                    seen_urls.add(result.url)
                    websites.append(result)

            print(f"Found {len(websites)} unique websites")

            # Convert the websites to a list of resources.
            resources = [
                Resource(
                    website.url,
                    website.title,
                    "website",
                    website.snippet,
                )
                for website in websites
            ]
            return resources

    def _fetch_site_content(self, site: Website) -> Optional[str]:
        try:
            markdown = site.get_markdown()
            markdown = markdown[0:25_000]
            return f"URL: {site.url}\nTitle: {site.title}\n\n{markdown}---"
        except Exception as e:
            print(f"Error getting markdown from {site.url}: {e}")
            return None

    def _generate_finding(
        self, context: Context, resource: Resource
    ) -> Finding:
        content = self._fetch_site_content(site)
        # Get the original topic from the execution context data
        topic = context.x["init_input"]["topic"]

        prompt = self.__findings_template.render(
            {
                "content": content,
                "query": topic,
                "max_learnings": self._max_learnings,
            }
        )
        try:
            output = self._llm(context, prompt)
            return Finding(site, output)
        except Exception as e:
            print(f"Error generating finding for {site.url}: {e}")
            raise e

    # def _generate_findings(
    #     self, context: Context, sites: List[Website]
    # ) -> List[Finding]:
    #     # Grab the original topic from the execution context data
    #     topic = context.x["init_input"]["topic"]

    #     # Use ThreadPoolExecutor to fetch content in parallel
    #     content_futures = [
    #         self.__threadpool.submit(self._fetch_site_content, site)
    #         for site in sites
    #     ]

    #     # Collect results and filter out None values from failed fetches
    #     content_parts = [
    #         future.result()
    #         for future in content_futures
    #         if future.result() is not None
    #     ]

    #     # Join all content parts into final content string
    #     content = "".join(content_parts)

    #     print("Post sites")
    #     prompt = self.__findings_template.render(
    #         {
    #             "content": content,
    #             "query": topic,
    #             "max_learnings": self._max_learnings,
    #         }
    #     )
    #     return self._llm(context, prompt)
