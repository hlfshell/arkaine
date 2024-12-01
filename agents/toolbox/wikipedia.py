from typing import Any, Dict, List, Optional

import wikipedia

from agents.agent import ToolAgent
from agents.backends.base import BaseBackend
from agents.backends.react import ReActBackend
from agents.documents import InMemoryEmbeddingStore, chunk_text_by_sentences
from agents.llms.llm import LLM
from agents.templater import PromptTemplate
from agents.tools.wrappers.top_n import TopN
from agents.tools.tool import Argument, Tool

TOPIC_QUERY_TOOL_NAME = "wikipedia_search_pages"
PAGE_CONTENT_TOOL_NAME = "wikipedia_get_page"


class WikipediaTopicQuery(Tool):

    def __init__(self):
        super().__init__(
            TOPIC_QUERY_TOOL_NAME,
            "Search Wikipedia for articles that match a given query topic -"
            + " returns a list of titles of Wiki pages that possibly match. "
            + f"Follow this function call with a {PAGE_CONTENT_TOOL_NAME} "
            + "function to get the content of the chosen title",
            [
                Argument(
                    name="query",
                    type="string",
                    description=(
                        "A simple query to search associated Wikipedia pages "
                        + "for"
                    ),
                    required=True,
                ),
            ],
            self.topic_query,
        )

    def topic_query(self, query: str) -> List[str]:
        topics = wikipedia.search(query)
        if len(topics) == 0:
            return "No topics match this query"

        out = "The following are titles to pages that match your query:\n"
        for topic in topics:
            out += topic + "\n"

        return out


class WikipediaPage(Tool):

    def __init__(self):
        super().__init__(
            PAGE_CONTENT_TOOL_NAME,
            (
                "Get the content of a Wikipedia page based on its title. "
                + "Content is returned as a dictionary with section titles as "
                + "keys and the content of that section as values."
            ),
            [
                Argument(
                    name="title",
                    type="string",
                    description="The title of the Wikipedia page - "
                    + "returns 'None' if the page does not exist",
                    required=True,
                )
            ],
            self.get_page,
        )

    def __break_down_content(self, content: str) -> Dict[str, str]:
        """
        Break down Wikipedia content into sections and their corresponding
        chunks.

        Wikipedia content is separated by section headers marked with '='
        characters. This method splits the content into sections and chunks
        each section's text into smaller, sentence-based segments.

        Args:
            content (str): Raw Wikipedia page content

        Returns:
            Dict[str, str]: Dictionary where keys are section titles and
                values the text from that section. Note we do not have nesting
                (subsections) - it's all one level deep.
        """
        # For cleanliness we're adding a fake title if none exists
        content = "= Title =\n\n" + content

        sections: Dict[str, str] = {}
        current_section = []
        current_title = ""

        for line in content.split("\n"):
            if line.strip() == "":
                continue

            if line[0] == "=" and line[-1] == "=":
                if len(current_section) > 0:
                    sections[current_title] = " ".join(current_section)
                    current_section = []
                current_title = line.strip(" =")
            else:
                current_section.append(line)

        # Don't forget the last section
        if len(current_section) > 0:
            sections[current_title] = " ".join(current_section)

        return sections

    def get_page(self, title: str, query: str) -> Dict[str, str]:
        content = wikipedia.page(title).content

        sections = self.__break_down_content(content)

        return sections


class WikipediaPageTopN(TopN):
    def __init__(
        self,
        name: Optional[str] = None,
        wp: Optional[WikipediaPage] = None,
        embedder: Optional[InMemoryEmbeddingStore] = None,
        n: int = 5,
    ):
        if wp is None:
            wp = WikipediaPage()

        if name is None:
            name = "wikipedia_page"

        if embedder is None:
            embedder = InMemoryEmbeddingStore()

        description = (
            "Get the content of a Wikipedia page based on its title. "
            + "Content is returned as a dictionary with section titles as "
            + "keys and the content of that section as values."
        )
        query_description = (
            "The query to search that specified Wikipedia to narrow results "
            + "to related history."
        )

        super().__init__(
            wp,
            embedder,
            n=5,
            name=name,
            description=description,
            query_description=query_description,
        )


class WikipediaSearch(ToolAgent):
    def __init__(
        self,
        llm: LLM,
        name: str = "wikipedia_search",
        backend: Optional[BaseBackend] = None,
        compress_article: bool = True,
        embedder: Optional[InMemoryEmbeddingStore] = None,
    ):
        description = (
            "Searches for an answer to the question by utilizing Wikipedia"
        )

        if not backend:
            backend = ReActBackend(
                llm,
                [WikipediaPageTopN(embedder=embedder), WikipediaTopicQuery()],
                description,
            )
        else:
            backend.add_tool(WikipediaTopicQuery())
            if compress_article:
                if embedder is None:
                    embedder = InMemoryEmbeddingStore()
                backend.add_tool(WikipediaPageTopN(embedder=embedder))
            else:
                backend.add_tool(WikipediaPage())
        super().__init__(
            name,
            description,
            [
                Argument(
                    "question",
                    "Your question you want answered",
                    "string",
                    required=True,
                )
            ],
            backend,
        )

    def prepare_for_backend(self, **kwargs) -> Dict[str, Any]:
        question = f"Answer the following question: {kwargs['question']}\n"

        return {"task": question}
