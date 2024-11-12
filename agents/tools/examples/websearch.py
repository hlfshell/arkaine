import os
import re
from typing import List, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from agents.tools.tool import Argument, Tool


class Website:
    def __init__(
        self,
        url: str,
        title: str = "",
        snippet: str = "",
        load_content: bool = False,
    ):
        self.url = url
        self.title = title
        self.snippet = snippet
        self.domain = Website.extract_domain(url)

        self.raw_content: Optional[str] = None

        if load_content:
            self.load_content()

    @classmethod
    def extract_domain(self, url: str) -> str:
        """
        Given a url extract the domain
        """
        # Use urlparse to handle the URL parsing
        parsed_url = urlparse(url)

        # Get the netloc (network location part)
        domain = parsed_url.netloc

        # Remove port number if present
        domain = domain.split(":")[0]

        # Remove 'www.' if present
        domain = re.sub(r"^www\.", "", domain)

        # Split by '.' and get the last two parts
        parts = domain.split(".")
        if len(parts) > 2:
            domain = ".".join(parts[-2:])

        return domain

    def load_content(self):
        """
        Load the content of the page, storing it in self.raw_content
        """
        response = requests.get(self.url)
        response.raise_for_status()
        self.raw_content = response.text

    def get_body(self):
        """
        Return the raw HTML body content of the page. If the page has not been
        already fetched, it will be fetched first.
        """
        if not self.raw_content:
            self.load_content()

        soup = BeautifulSoup(self.raw_content, "html.parser")
        return soup.body

    def get_body_text(self):
        """
        Return the text content of the page. If the page has not been already
        fetched, it will be fetched first.
        """
        if not self.raw_content:
            self.load_content()

        soup = BeautifulSoup(self.raw_content, "html.parser")
        return soup.body.get_text()

    def format(self, template: str) -> str:
        """
        format returns a string formatted per the provided string, replacing
        {url}, {domain}, {title}, and {snippet} with the actual values
        """
        return template.format(
            url=self.url,
            domain=self.domain,
            title=self.title,
            snippet=self.snippet,
        )

    def __str__(self):
        return f"{self.title}\n{self.url}\n\t{self.snippet}"


class Websearch(Tool):

    def __init__(self, api_key: str = None):
        self.__api_key = api_key
        if not self.__api_key:
            self.__api_key = os.environ["BING_SUBSCRIPTION_KEY"]

        super().__init__(
            name="websearch",
            description="Searches the web for a given query",
            args=[
                Argument(
                    "query",
                    "The query to search for",
                    "string",
                    required=True,
                ),
                Argument(
                    "domains",
                    "A list of domains to restrict the search to",
                    "list[str]",
                    required=False,
                ),
                Argument(
                    "limit",
                    "The number of results to return",
                    "int",
                    required=False,
                    default=10,
                ),
                Argument(
                    "offset",
                    "The offset to start the search from",
                    "int",
                    required=False,
                    default=0,
                ),
            ],
            func=self.search,
        )

    def search(
        self,
        query: str,
        domains: List[str] = [],
        limit: int = 10,
        offset: int = 0,
    ) -> List[Website]:
        # Safety check to ensure domain is a List and not a
        # string (or a string of a list)
        if isinstance(domains, str):
            # check to see if it's a stringified list (ie "[domain1, domain2]")
            if domains.startswith("[") and domains.endswith("]"):
                domains = domains[1:-1].split(", ")
            else:
                domains = [domains]

        print("domains", domains)
        query_string = query
        if domains:
            query_string += " " + " OR site:".join(f"site:{d}" for d in domains)

        search_url = "https://api.bing.microsoft.com/v7.0/search"

        headers = {"Ocp-Apim-Subscription-Key": self.__api_key}
        params = {
            "q": query_string,
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
