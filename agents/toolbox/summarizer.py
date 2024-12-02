import pathlib
from os import path
from typing import List, Optional

from agents.agent import Agent
from agents.llms.llm import LLM, Prompt
from agents.utils.templater import PromptTemplate
from agents.tools.tool import Argument, Context


class Summarizer(Agent):

    def __init__(self, llm: LLM, word_limit: Optional[int] = None):
        super().__init__(
            name="Summarizer",
            description="Summarizes a given body of text to a more succinct form",
            args=[
                Argument(
                    "text",
                    "The body of text to be summarized",
                    "string",
                    required=True,
                ),
                Argument(
                    "length",
                    "The desired length of the summary, in human readable format (ie a 'few sentences')",
                    "string",
                    required=False,
                    default="a few sentences",
                ),
            ],
            llm=llm,
        )

        if word_limit is None:
            word_limit = int(self.llm.context_length / 10)
        self.token_limit = word_limit

        self.__templater = PromptTemplate.from_file(
            path.join(
                pathlib.Path(__file__).parent,
                "prompts",
                "summarizer.prompt",
            )
        )

    def __chunk_text(self, text: str) -> List[str]:
        """
        Given a chunk of text, divide it into smaller chunks
        broken down by words
        """
        chunks: List[str] = []
        words = text.split(" ")
        while words:
            chunk = words[: self.token_limit]
            chunks.append(" ".join(chunk))
            words = words[self.token_limit :]

        return chunks

    def prepare_prompt(self, **kwargs) -> Prompt:
        pass

    def __call__(self, context: Optional[Context] = None, **kwargs) -> str:
        with self._init_context_(context, **kwargs) as ctx:
            kwargs = self.fulfill_defaults(kwargs)
            self.check_arguments(kwargs)

            text = kwargs["text"]
            length = kwargs["length"]

            chunks = self.__chunk_text(text)

            # Summarize each chunk
            summary = ""
            initial_summary = True
            for chunk in chunks:
                prompt = self.__templater.render(
                    {
                        "current_summary": summary,
                        "length": length,
                        "text": chunk,
                    }
                )

                summary = self.llm.completion(prompt)

                if initial_summary:
                    summary = f"Your summary so far:\n{summary}\n"
                    initial_summary = False

            return summary
