from typing import Optional
from arkaine.utils.website import Website
import os


class TavilyAuth:

    __api_key = None

    @classmethod
    def set_api_key(cls, api_key: str):
        cls.__api_key = api_key

    @classmethod
    def get_api_key(cls) -> str:
        if not cls.__api_key:
            raise ValueError("Tavily API key not set")
        return cls.__api_key


def register_tavily_plugin(api_key: Optional[str] = None):
    # Ensure that we have the necessary imports
    try:
        import tavily  # noqa: F401
    except ImportError:
        raise ImportError("Tavily plugin requires tavily package version 0.5.1")

    if api_key is None:
        api_key = os.environ.get("TAVILY_API_KEY")

    if api_key is None:
        raise ValueError(
            "Tavily API key not found - either pass it or set the "
            "TAVILY_API_KEY environment variable"
        )

    TavilyAuth.set_api_key(api_key)

    Website.add_custom_domain_loader("*", load_tavily_content)


def load_tavily_content(website: Website):
    import tavily

    client = tavily.TavilyClient(api_key=TavilyAuth.get_api_key())
    response = client.extract(urls=[website.url])

    if len(response["failed_results"]) > 0:
        Website.load(website)
        return

    if len(response["results"]) == 0:
        Website.load(website)
        return

    website.raw_content = response["results"][0]["content"]
    website.markdown = response["results"][0]["content"]
