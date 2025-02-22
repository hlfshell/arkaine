from typing import List, Optional

from arkaine.llms.llm import LLM
from arkaine.toolbox.research.researcher import Researcher
from arkaine.toolbox.webqueryer import Webqueryer
from arkaine.toolbox.websearch import Websearch
from arkaine.tools.context import Context
from arkaine.utils.resource import Resource


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

        return resources
