import os
from typing import List, Optional, Union
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from arkaine.tools.tool import Argument, Tool
from arkaine.utils.website import Website

DUCK_DUCK_GO = "duckduckgo"
BING = "bing"
GOOGLE = "google"
FIRECRAWL = "firecrawl"
EXA = "exa"
TAVILY = "tavily"


def load_firecrawl():
    try:
        from firecrawl import FirecrawlApp
    except ImportError:
        raise ImportError(
            "FireCrawl is not installed - please install with "
            "pip install firecrawl==1.13.2"
        )

    return FirecrawlApp


def load_exa():
    try:
        from exa_py import Exa
    except ImportError:
        raise ImportError(
            "Exa is not installed - please install with "
            "pip install exa_py==1.8.9"
        )

    return Exa


def load_tavily():
    try:
        from tavily import TavilyClient
    except ImportError:
        raise ImportError(
            "Tavily is not installed - please install with "
            "pip install tavily==0.5.1"
        )

    return TavilyClient


class Websearch(Tool):
    def __init__(
        self,
        provider: str = DUCK_DUCK_GO,
        api_key: Optional[str] = None,
        limit: Optional[Union[int, bool]] = False,
        offset: Optional[bool] = False,
        domains: Optional[Union[List[str], bool]] = False,
    ):
        self.provider = provider.lower()
        self.__api_key = api_key

        self.forced_limit = 0
        self.allow_limit = False
        if limit and isinstance(limit, int):
            self.forced_limit = limit
        elif limit:
            self.allow_limit = True

        self.forced_domains = []
        self.allow_domains = False
        if domains and isinstance(domains, list):
            self.forced_domains = domains
        elif domains:
            self.allow_domains = True

        self.__allow_offset = offset

        # Validate API key requirements
        if self.provider == BING:
            if not api_key:
                self.__api_key = os.environ.get("BING_SUBSCRIPTION_KEY")
                if not self.__api_key:
                    raise ValueError("Bing search requires an API key")
        elif self.provider == GOOGLE:
            if not api_key:
                self.__api_key = os.environ.get("GOOGLE_SEARCH_API_KEY")
                if not self.__api_key:
                    raise ValueError("Google search requires an API key")
        elif self.provider == FIRECRAWL:
            # See if firecrawl is installed
            load_firecrawl()
            if not api_key:
                self.__api_key = os.environ.get("FIRECRAWL_API_KEY")
                if not self.__api_key:
                    raise ValueError("FireCrawl search requires an API key")
        elif self.provider == EXA:
            load_exa()
            if not api_key:
                self.__api_key = os.environ.get("EXA_API_KEY")
                if not self.__api_key:
                    raise ValueError("Exa search requires an API key")
        elif self.provider == TAVILY:
            load_tavily()

            if not api_key:
                self.__api_key = os.environ.get("TAVILY_API_KEY")
                if not self.__api_key:
                    raise ValueError("Tavily search requires an API key")

        args = [
            Argument(
                "query",
                "The query to search for",
                "string",
                required=True,
            ),
        ]

        if self.allow_domains:
            args.append(
                Argument(
                    "domains",
                    "A list of domains to restrict the search to",
                    "list[str]",
                    required=False,
                )
            )

        if self.allow_limit:
            args.append(
                Argument(
                    "limit",
                    "The number of results to return",
                    "int",
                    required=False,
                    default=10,
                )
            )

        if self.__allow_offset:
            args.append(
                Argument(
                    "offset",
                    "The offset to start the search from - optional",
                    "int",
                    required=False,
                    default=0,
                )
            )

        super().__init__(
            name="websearch",
            description=(
                "Searches the web for a given query using multiple providers"
            ),
            args=args,
            func=self.search,
        )

    def _build_query_string(self, query: str, domains: List[str]) -> str:
        if not domains:
            return query

        if self.provider == DUCK_DUCK_GO:
            return query + " " + " OR ".join(f"site:{d}" for d in domains)
        else:  # Bing and Google use the same site: syntax
            return query + " " + " OR site:".join(f"site:{d}" for d in domains)

    def _search_duckduckgo(
        self, query: str, domains: List[str], limit: int, offset: int
    ) -> List[Website]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            + " AppleWebKit/537.36 (KHTML, like Gecko)"
            + " Chrome/91.0.4472.124 Safari/537.36"
        }

        # DuckDuckGo's HTML search endpoint
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(self._build_query_string(query, domains))}"

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        results = []

        for result in soup.select(".result")[0:limit]:
            title_elem = result.select_one(".result__title a")
            snippet_elem = result.select_one(".result__snippet")

            if title_elem:
                results.append(
                    Website(
                        url=title_elem["href"],
                        title=title_elem.get_text(),
                        snippet=snippet_elem.get_text() if snippet_elem else "",
                    )
                )

        return results

    def _search_bing(
        self, query: str, domains: List[str], limit: int, offset: int
    ) -> List[Website]:
        search_url = "https://api.bing.microsoft.com/v7.0/search"
        headers = {"Ocp-Apim-Subscription-Key": self.__api_key}
        params = {
            "q": self._build_query_string(query, domains),
            "textDecorations": False,
            "textFormat": "RAW",
            "count": limit,
            "offset": offset,
        }

        response = requests.get(search_url, headers=headers, params=params)
        response.raise_for_status()
        search_results = response.json()

        results = []
        if (
            "webPages" in search_results
            and "value" in search_results["webPages"]
        ):
            for result in search_results["webPages"]["value"]:
                results.append(
                    Website(
                        url=result["url"],
                        title=result["name"],
                        snippet=result["snippet"],
                    )
                )

        return results

    def _search_google(
        self, query: str, domains: List[str], limit: int, offset: int
    ) -> List[Website]:
        search_url = "https://customsearch.googleapis.com/customsearch/v1"
        params = {
            "key": self.__api_key,
            "cx": os.environ.get(
                "GOOGLE_SEARCH_ENGINE_ID"
            ),  # Custom Search Engine ID
            "q": self._build_query_string(query, domains),
            "num": min(limit, 10),  # Google API maximum is 10 per request
            "start": offset + 1,  # Google's offset is 1-based
        }

        response = requests.get(search_url, params=params)
        response.raise_for_status()
        search_results = response.json()

        results = []
        if "items" in search_results:
            for result in search_results["items"]:
                results.append(
                    Website(
                        url=result["link"],
                        title=result["title"],
                        snippet=result.get("snippet", ""),
                    )
                )

        return results

    def _search_firecrawl(
        self, query: str, domains: List[str], limit: int, offset: int
    ) -> List[Website]:
        FirecrawlApp = load_firecrawl()
        firecrawl = FirecrawlApp(api_key=self.__api_key)

        # Firecrawl limit must be between 1 and 10
        limit = min(max(limit, 1), 10)

        response = firecrawl.search(
            query=query,
            params={
                "scrapeOptions": {
                    "formats": ["markdown", "html"],
                },
                "limit": limit,
            },
        )

        results = []
        for entry in response["data"]:
            results.append(
                Website(
                    url=entry["url"],
                    title=entry["title"],
                    snippet=entry["description"],
                    markdown=entry["markdown"],
                    html=entry["html"],
                )
            )

        return results

    def _search_exa(
        self, query: str, domains: List[str], limit: int, offset: int
    ) -> List[Website]:
        Exa = load_exa()
        exa = Exa(api_key=self.__api_key)

        response = exa.search_and_contents(
            query,
            num_results=limit,
            type="keyword",
            text={
                "max_characters": 250,
            },
        )

        results = []
        for entry in response.results:
            results.append(
                Website(
                    url=entry.url,
                    title=entry.title,
                    snippet=entry.text,
                )
            )

        return results

    def _search_tavily(
        self, query: str, domains: List[str], limit: int, offset: int
    ):
        client = load_tavily(api_key=self.__api_key)

        response = client.search(
            query=query,
            topic="general",
            max_results=limit,
            include_domains=domains,
        )

        results = []
        for result in response["results"]:
            results.append(
                Website(
                    url=result["url"],
                    title=result["title"],
                    snippet=result["content"],
                )
            )

        return results

    def search(
        self,
        query: str,
        domains: List[str] = [],
        limit: int = 10,
        offset: int = 0,
    ) -> List[Website]:
        # Handle string domains input
        if self.forced_domains:
            domains = self.forced_domains
        elif self.allow_domains and isinstance(domains, str):
            if domains.startswith("[") and domains.endswith("]"):
                domains = domains[1:-1].split(", ")
            else:
                domains = [domains]

        if self.forced_limit:
            limit = self.forced_limit
        elif self.allow_limit and isinstance(limit, int):
            limit = limit

        if self.__allow_offset:
            offset = offset
        else:
            offset = 0

        # Map providers to their search methods
        search_methods = {
            DUCK_DUCK_GO: self._search_duckduckgo,
            BING: self._search_bing,
            GOOGLE: self._search_google,
            FIRECRAWL: self._search_firecrawl,
            EXA: self._search_exa,
            TAVILY: self._search_tavily,
        }

        return search_methods[self.provider](query, domains, limit, offset)
