import pathlib
from os import path
from typing import List, Optional

from arkaine.llms.llm import LLM
from arkaine.tools.agent import IterativeAgent
from arkaine.tools.tool import Argument, Context
from arkaine.utils.templater import PromptTemplate


class NoteTaker(IterativeAgent):
    """An agent that creates structured notes and outlines from content.

    This agent processes text content in chunks, creating a hierarchical outline
    that thoroughly covers the material. It can optionally focus on specific
    aspects or topics within the content.

    Args:
        llm (LLM): The language model to use for note taking
        focus_query (bool): Whether to focus notes around a specific query/topic
        chunk_size (int): Number of sentences per chunk when processing
        overlap (int): Number of sentences to overlap between chunks
    """

    def __init__(
        self,
        llm: LLM,
        focus_query: bool = False,
        chunk_size: Optional[int] = None,
        overlap: Optional[int] = None,
    ):
        args = [
            Argument(
                "text",
                "The text content to create notes from",
                "str",
                required=True,
            ),
            Argument(
                "length",
                "Desired detail level of notes (brief/detailed/comprehensive)",
                "str",
                required=False,
                default="detailed",
            ),
        ]

        if focus_query:
            args.append(
                Argument(
                    "query",
                    "The specific topic or aspect to focus on in the notes",
                    "str",
                    required=True,
                )
            )

        super().__init__(
            name="note_taker",
            description="Creates structured notes and outlines from text content",
            args=args,
            llm=llm,
            examples=[],
            initial_state={
                "chunks": [],
                "current_chunk": 0,
                "outline": "",
            },
        )

        self._chunk_size = chunk_size or (self.llm.context_length * 0.33)
        if overlap is None:
            # We aim for 15% of the context length as a default
            self._overlap = int(self.llm.context_length * 0.15)
        else:
            self._overlap = overlap

        self._focus_query = focus_query

        # Load appropriate prompt template based on whether we're using focus_query
        template_name = (
            "note_taker_focused.prompt" if focus_query else "note_taker.prompt"
        )
        self.__template = PromptTemplate.from_file(
            path.join(
                pathlib.Path(__file__).parent,
                "prompts",
                template_name,
            )
        )

    def __chunk_text(
        self, text: str, chunk_size: int, overlap: int
    ) -> List[str]:
        """Given a chunk of text, divide it into smaller chunks broken down by words"""
        # Use 50% of the context length as a default, or a user specified chunk
        # size.
        token_limit = chunk_size
        chunks: List[str] = []
        words = text.split(" ")
        words_per_chunk = int(token_limit * 0.75)
        while words:
            # Take the next chunk of words, with overlap from previous chunk
            chunk = words[:words_per_chunk]
            chunks.append(" ".join(chunk))

            # Move pointer forward but keep overlap words
            words = words[words_per_chunk - overlap :]
        return chunks

    def prepare_prompt(
        self,
        context: Context,
        text: str = "",
        length: str = "detailed",
        query: str = "",
    ) -> str:
        if len(context["chunks"]) == 0:
            context["chunks"] = self.__chunk_text(
                text, self._chunk_size, self._overlap
            )
            context["current_chunk"] = 0
            context["outline"] = ""
            context["length"] = length

        """Prepare the prompt for the current chunk."""
        current_chunk = context["chunks"][context["current_chunk"]]

        # Check if the prompt would be too long and truncate previous notes if needed
        # Estimate tokens using 0.75 words per token ratio
        max_tokens = int(self.llm.context_length * 0.75)
        current_chunk_words = len(current_chunk.split())
        previous_notes_words = (
            len(context["outline"].split()) if context["outline"] else 0
        )

        # Reserve ~25% for the template text and other variables
        available_words = max_tokens - int(current_chunk_words * 1.25)

        previous_notes = context["outline"]
        if previous_notes_words > available_words:
            # Keep most recent notes by splitting on newlines and taking latest sections
            note_sections = previous_notes.split("\n")
            truncated_notes = []
            word_count = 0

            # Work backwards through sections
            for section in reversed(note_sections):
                section_words = len(section.split())
                if word_count + section_words > available_words:
                    break
                truncated_notes.insert(0, section)
                word_count += section_words

            previous_notes = "\n".join(truncated_notes)
            if truncated_notes:
                previous_notes = "...\n" + previous_notes

        context["outline"] = previous_notes
        template_vars = {
            "text": current_chunk,
            "length": context["length"],
            "previous_outline": (
                context["outline"]
                if context["outline"]
                else "No previous notes yet."
            ),
        }

        if self._focus_query:
            template_vars["query"] = context["query"]

        return self.__template.render(template_vars)

    def extract_result(self, context: Context, output: str) -> Optional[str]:
        """Process the current chunk's notes and determine if we're done."""
        context["outline"] += f"\n{output}"

        # Move to next chunk
        context.increment("current_chunk")

        # If we've processed all chunks, return the final outline
        if context["current_chunk"] >= len(context["chunks"]):
            return context["outline"]

        return None
