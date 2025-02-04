import re
from typing import List

from arkaine.llms.llm import LLM, Prompt
from arkaine.tools.agent import Agent
from arkaine.tools.tool import Argument, Context
from arkaine.utils.templater import PromptTemplate


class Webqueryer(Agent):
    def __init__(self, llm: LLM):
        description = (
            "You are an AI agent that accepts a topic or query from a user and "
            "generates multiple search queries that could return relevant "
            "information."
        )

        super().__init__(
            name="webqueryer",
            description=description,
            args=[
                Argument(
                    "topic",
                    "The topic/question to generate search queries for",
                    "str",
                    required=True,
                ),
                Argument(
                    "num_queries",
                    "The number of search queries to generate (default: 3)",
                    "int",
                    required=False,
                    default="3",
                ),
            ],
            llm=llm,
        )

        self.__template = PromptTemplate(
            "You are an AI agent that specializes in generating effective "
            "search queries. Given a topic or question, generate "
            "{num_queries} different search queries that would help find "
            "relevant information. Each query should focus on a different "
            "aspect or approach to finding information about the topic.\n\n"
            "Format your response as a simple list with one query per line, "
            "like:\n"
            "query 1\n"
            "query 2\n"
            "query 3\n\n"
            "Topic: {topic}"
        )

    def prepare_prompt(
        self, context: Context, topic: str, num_queries: int = 3
    ) -> Prompt:
        return self.__template.render(
            {"topic": topic, "num_queries": num_queries}
        )

    def extract_result(self, context: Context, answer: str) -> List[str]:
        """
        Extract search queries from the LLM response, handling various formats.

        Handles formats like:
        - Numbered lists (1.,

        Args:
            answer (str): Raw LLM output text

        Returns:
            List[str]: List of clean search queries
        """
        # Split into lines and clean initial whitespace
        lines = [line.strip() for line in answer.split("\n")]

        # Filter out empty lines and common headers
        lines = [
            line
            for line in lines
            if line
            and not any(
                header in line.lower()
                for header in ["topic:", "queries:", "here are", "suggested"]
            )
        ]

        queries = []
        for line in lines:
            # Remove common list prefixes
            # Handle numbered lists (1., 1), 1-, etc)
            line = re.sub(r"^\d+[\.\)\-]\s*", "", line)

            # Handle bullet points and other decorators
            line = re.sub(r"^[-•*→⇒≫»·]\s*", "", line)

            # Remove "Query:" or "Search:" prefixes
            line = re.sub(
                r"^(?:query|search|suggestion)[\s:]+",
                "",
                line,
                flags=re.IGNORECASE,
            )

            # Remove quotes if they wrap the entire string
            line = re.sub(r'^["\'](.*)["\']$', r"\1", line)

            # Remove any remaining leading/trailing whitespace or punctuation
            line = line.strip("\"'.,; \t")

            if line:  # Only add non-empty queries
                queries.append(line)

        # Remove duplicates while preserving order
        seen = set()
        queries = [q for q in queries if not (q in seen or seen.add(q))]

        return queries
