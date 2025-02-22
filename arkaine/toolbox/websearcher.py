import pathlib
import re
from collections import OrderedDict
from os import path
from typing import Any, Dict, List, Optional

from requests.exceptions import HTTPError

from arkaine.backends.react import ReActBackend
from arkaine.flow.linear import Linear
from arkaine.flow.parallel_list import ParallelList
from arkaine.llms.llm import LLM
from arkaine.toolbox.summarizer import Summarizer
from arkaine.toolbox.webqueryer import Webqueryer
from arkaine.toolbox.websearch import Websearch, Website
from arkaine.tools.agent import Agent
from arkaine.tools.tool import Argument, Context
from arkaine.utils.templater import PromptTemplate


class WebSearcher(Linear):
    def __init__(self, llm: LLM, websearch: Optional[Websearch] = None):
        if not websearch:
            websearch = Websearch()

        super().__init__(
            name="web_searcher",
            description="Given a topic or task, perform web searches to find "
            + "relevant information",
            arguments=[
                Argument(
                    "topic",
                    "The question/topic/task to try to research",
                    "str",
                    required=True,
                ),
            ],
            examples=[],
            steps=[
                Webqueryer(llm),
                lambda queries: {"input": [{"query": q} for q in queries]},
                ParallelList(
                    websearch,
                    result_formatter=self.process_search_results,
                ),
                lambda context, sites: {
                    "sites": sites,
                    "query": context.x["init_input"]["topic"],
                },
                SearchQueryJudge(llm),
                self.process_websites,
                ParallelList(
                    Summarizer(llm, focus_query=True),
                ),
                lambda context, summaries: {
                    "query": context.x["init_input"]["topic"],
                    "text": "The following are summaries of several "
                    + "websites on the topic:"
                    + "\n\n".join(summaries),
                    "length": "a few paragraphs",
                },
                Summarizer(llm, focus_query=True),
            ],
        )

    def __strip_url(self, url: str) -> str:
        """
        Remove all extraneous URL additives, such as ?, #, and trailing
        slashes. We also will remove http://, https://, and www.
        """
        url = re.sub(r"\?.*", "", url)  # Remove query parameters
        url = re.sub(r"#.*", "", url)  # Remove anchor
        url = re.sub(r"\/+$", "", url)  # Remove trailing slashes
        url = re.sub(r"^https?:\/\/", "", url)  # Remove http:// or https://
        url = re.sub(r"^www\.", "", url)  # Remove www.
        return url

    def process_search_results(
        self, context: Context, results: List[List[Website]]
    ) -> List[Website]:
        # First we convert the list of lists into a single list
        results = [item for sublist in results for item in sublist]

        # Find all the sites that are likely to be duplicates and remove them
        unique_results = OrderedDict()

        for result in results:
            stripped_url = self.__strip_url(result.url)
            if stripped_url not in unique_results:
                unique_results[stripped_url] = result

        return list(unique_results.values())

    def process_websites(self, context, sites):
        output = []
        for site in sites:
            try:
                output.append(
                    {
                        "text": site.get_markdown(),
                        "query": context.x["init_input"]["topic"],
                        "length": "a short summary",
                    }
                )
            except HTTPError:
                # Ignore HTTP errors as that is typically
                # the site selected is down or cranky that we're
                # trying to scrape it.
                pass

        return {"input": output}


class SearchQueryJudge(Agent):

    def __init__(self, llm: LLM):
        super().__init__(
            name="search_query_judge",
            description="Given a query/topic/task, and a series of websites "
            + "and their descriptions, determine which sites of those "
            + "presented are likely to contain useful information.",
            args=[
                Argument(
                    "query",
                    "The query/topic/task to try to research",
                    "str",
                    required=True,
                ),
                Argument(
                    "sites",
                    "A list of websites and their descriptions",
                    "list[Website]",
                    required=True,
                ),
            ],
            llm=llm,
            examples=[],
        )

        self.__template = PromptTemplate.from_file(
            path.join(
                pathlib.Path(__file__).parent,
                "prompts",
                "search_query_judge.prompt",
            ),
        )

    def prepare_prompt(
        self, context: Context, query: str, sites: List[Website]
    ) -> List[Dict[str, str]]:
        websites_str = "\n".join(
            [f"{site.url}\n\t{site.snippet}" for site in sites]
        )

        return self.__template.render(
            {
                "query": query,
                "sites": websites_str,
            }
        )

    def extract_result(self, context: Context, output: str) -> List[Website]:
        """
        Process the output. We expect it to be several lines,
        which follow the form of
        SITE: url
        REASON: reason

        ...let's convert that to a List of Websites, with
        resiliency for extra lines, and extra text or symbols
        (ie bullet points, 1. 2., etc)
        """
        if output.strip() == "NONE":
            return []

        websites = []
        current_site = None
        current_reason = None

        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Remove any leading bullet points or numbers
            line = re.sub(r"^[\d\.\-\*\s]+", "", line)

            if line.upper().startswith("SITE:"):
                # If we have a complete site/reason pair, add it
                if current_site and current_reason:
                    websites.append(
                        Website(current_site, snippet=current_reason)
                    )

                # Start new site
                current_site = line[5:].strip()
                current_reason = None
            elif line.upper().startswith("REASON:"):
                current_reason = line[7:].strip()
                # If we have both site and reason, create Website
                if current_site and current_reason:
                    websites.append(
                        Website(current_site, snippet=current_reason)
                    )

                    current_site = None
                    current_reason = None

        # Handle any remaining pair
        if current_site and current_reason:
            websites.append(Website(current_site, snippet=current_reason))

        for website in websites:
            try:
                website.get_title()
            except HTTPError:
                # We are ignoring HTTP errors as that is typically
                # the site selected is down or cranky that we're
                # trying to scrape it.
                pass

        if len(websites) == 0:
            raise ValueError("No websites found")

        return websites
