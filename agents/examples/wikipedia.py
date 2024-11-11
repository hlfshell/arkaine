from typing import Any, Dict, List

import wikipedia

from agents.agent import ToolAgent
from agents.backends.openai import OpenAI
from agents.backends.react import ReActBackend
from agents.backends.simple import SimpleBackend
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

    def topic_query(self, argdict: Dict[str, str]) -> List[str]:
        topic = argdict["query"]
        topics = wikipedia.search(topic)
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

    def page(self, args: Dict[str, str]) -> str:
        title = args["title"]
        content = wikipedia.page(title).content

        chunks = self.__break_down_content(content)

        store = InMemoryEmbeddingStore(embedding_model="")
        for chunk in chunks:
            store.add_text(chunk)

        results = store.query(args["query"], top_n=5)

        out = "Here are the top 5 most relevant sections of the specified article:\n"

        for index, result in enumerate(results):
            out += f"{index + 1} - {result}\n"

        return out


class WikipediaSearch(ToolAgent):
    def __init__(
        self, llm: LLM, name: str = "wikipedia_search", backend: str = "react"
    ):
        if backend not in ["react", "simple", "openai"]:
            raise ValueError(
                "Invalid backend specified - must be one of 'react', 'simple', or 'openai'"
            )

        self.agent_explanation = (
            "Searches for an answer to the question by utilizing Wikipedia"
        )

        tools = [WikipediaPage(), WikipediaTopicQuery()]

        if backend == "react":
            self.backend = ReActBackend(llm, tools, self.agent_explanation)
        elif backend == "simple":
            self.backend = SimpleBackend(llm, tools, self.agent_explanation)
        elif backend == "openai":

            text = """
You are an AI agent that is tasked to perform certain tasks
with the help of additional tools. Utilizing these tools, perform
the following task:

{task}
"""
            self.backend = OpenAI(tools, PromptTemplate(text))

        super().__init__(
            name,
            self.agent_explanation,
            [
                Argument(
                    "question",
                    "Your question you want answered",
                    "string",
                    required=True,
                )
            ],
            self.backend,
        )

    def prepare_for_backend(self, **kwargs) -> Dict[str, Any]:
        question = f"Answer the following question: {kwargs['question']}\n"

        return {"task": question}
