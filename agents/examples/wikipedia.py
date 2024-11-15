from typing import Any, Dict, List, Optional

import wikipedia

from agents.agent import ToolAgent
from agents.backends.base import BaseBackend
from agents.backends.react import ReActBackend
from agents.documents import InMemoryEmbeddingStore, chunk_text_by_sentences
from agents.llms.llm import LLM
from agents.templater import PromptTemplate
from agents.tools.tool import Argument, Tool

TOPIC_QUERY_TOOL_NAME = "wikipedia_search_pages"
PAGE_CONTENT_TOOL_NAME = "wikipedia_get_page"


class WikipediaTopicQuery(Tool):

    def __init__(self):
        super().__init__(
            TOPIC_QUERY_TOOL_NAME,
            "Search Wikipedia for articles that match a given query topic -"
            + f" returns a list of titles of Wiki pages that possibly match. Follow this function call with a {PAGE_CONTENT_TOOL_NAME} function to get the content of the chosen title",
            [
                Argument(
                    name="query",
                    type="string",
                    description="A simple query to search associated Wikipedia pages for",
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
            f"Get the most relevant content of a Wikipedia page based on its title and a query. If you do not know the title, it is better to first perform a {TOPIC_QUERY_TOOL_NAME} to find the exact title from a given topic. Utilize the query argument to narrow your search to specific facts.",
            [
                Argument(
                    name="title",
                    type="string",
                    description="The title of the Wikipedia page - "
                    + "returns 'None' if the page does not exist",
                    required=True,
                ),
                Argument(
                    name="query",
                    type="string",
                    description="The query to search that specified Wikipedia to narrow results to related history."
                    + " page for",
                    required=True,
                ),
            ],
            self.page,
        )

    def __break_down_content(self, content: str) -> List[str]:
        # Wikipedia content is separated by content
        # headers with =, and then paragraphs. We're
        # going to isolate individual sentences from
        # each section

        # For cleanliness we're adding a fake title

        content = "= Title =\n\n" + content

        sections: List[str] = []
        current_section = []
        for line in content.split("\n"):
            if line.strip() == "":
                continue

            if line[0] == "=" and line[-1] == "=":
                if len(current_section) > 0:
                    sections.append(" ".join(current_section))
                    current_section = []
            else:
                current_section.append(line)

        # return [chunk_text_by_sentences(section, 3) for section in sections]
        chunks = []
        for section in sections:
            chunks += chunk_text_by_sentences(section, 3)

        return chunks

    def page(self, title: str, query: str) -> str:
        content = wikipedia.page(title).content

        chunks = self.__break_down_content(content)

        store = InMemoryEmbeddingStore(embedding_model="")
        for chunk in chunks:
            store.add_text(chunk)

        results = store.query(query, top_n=5)

        out = "Here are the top 5 most relevant sections of the specified article:\n"

        for index, result in enumerate(results):
            out += f"{index + 1} - {result}\n"

        return out


class WikipediaSearch(ToolAgent):
    def __init__(
        self,
        llm: LLM,
        name: str = "wikipedia_search",
        backend: Optional[BaseBackend] = None,
    ):
        description = (
            "Searches for an answer to the question by utilizing Wikipedia"
        )

        if not backend:
            backend = ReActBackend(
                llm,
                [WikipediaPage(), WikipediaTopicQuery()],
                description,
            )
        else:
            backend.add_tool(WikipediaPage())
            backend.add_tool(WikipediaTopicQuery())

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


PROMPT_TEXT = """
You are an AI agent that is tasked to perform certain tasks
with the help of additional tools. Utilizing these tools, perform
the following task:

{task}
"""
PROMPT = PromptTemplate(PROMPT_TEXT)
