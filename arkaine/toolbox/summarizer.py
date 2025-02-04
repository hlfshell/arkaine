import pathlib
from os import path
from typing import List, Optional

from arkaine.llms.llm import LLM, Prompt
from arkaine.tools.agent import IterativeAgent
from arkaine.tools.tool import Argument, Context
from arkaine.utils.templater import PromptTemplate


class Summarizer(IterativeAgent):

    def __init__(
        self,
        llm: LLM,
        chunk_size: Optional[int] = None,
        focus_query: bool = False,
    ):

        args = [
            Argument(
                "text",
                "The body of text to be summarized",
                "string",
                required=True,
            ),
            Argument(
                "length",
                "The desired length of the summary, in human readable format "
                + "(ie a 'few sentences')",
                "string",
                required=False,
                default="a few sentences",
            ),
        ]

        defaults = {"query_instruction": ""}

        self.focus_query = focus_query
        if focus_query:
            args.append(
                Argument(
                    "query",
                    "An optional query to try and focus the summary towards "
                    + "answering",
                    "string",
                    required=False,
                ),
            )
            defaults["query_instruction"] = (
                "Provided is an additional query that you should take into "
                + "account and focus on when summarizing:"
            )

        super().__init__(
            name="Summarizer",
            description="Summarizes a given body of text to a more succinct "
            + "form",
            args=args,
            llm=llm,
            initial_state={
                "chunks": [],
                "current_chunk": 0,
                "summary": "",
                "initial_summary": True,
            },
        )

        self.__templater = PromptTemplate.from_file(
            path.join(
                pathlib.Path(__file__).parent,
                "prompts",
                "summarizer.prompt",
            ),
            defaults,
        )

        self._chunk_size = chunk_size

    def __chunk_text(self, text: str) -> List[str]:
        """
        Given a chunk of text, divide it into smaller chunks
        broken down by words
        """
        # Use 50% of the context length as a default, or a user specified chunk
        # size.
        token_limit = self._chunk_size or (self.llm.context_length * 0.5)

        chunks: List[str] = []
        words = text.split(" ")
        # Rule of thumb: 0.75 words per token, so...
        words_per_chunk = int(token_limit * 0.75)
        while words:
            chunk = words[:words_per_chunk]
            chunks.append(" ".join(chunk))
            words = words[words_per_chunk:]

        return chunks

    def prepare_prompt(self, context: Context, **kwargs) -> Prompt:
        # First time through, initialize state vars for repeated use.
        if not context["chunks"]:
            text = kwargs["text"]
            context["chunks"] = self.__chunk_text(text)

        chunk = context["chunks"][context["current_chunk"]]
        vars = {
            "current_summary": context["summary"],
            "length": kwargs["length"],
            "text": chunk,
        }

        if self.focus_query:
            vars["query"] = kwargs["query"]

        return self.__templater.render(vars)

    def extract_result(self, context: Context, output: str) -> Optional[str]:
        # Update summary
        if context["initial_summary"]:
            context["summary"] = f"Your summary so far:\n{output}\n"
            context["initial_summary"] = False
        else:
            context["summary"] = output

        # Move to next chunk
        context.increment("current_chunk")

        # If we've processed all chunks, return the final summary
        if context["current_chunk"] >= len(context["chunks"]):
            return context["summary"]

        return None
