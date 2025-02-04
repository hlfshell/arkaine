import pathlib
from os import path
from typing import Any, Dict, List, Optional, Tuple

from arkaine.llms.llm import LLM, Prompt
from arkaine.tools.agent import IterativeAgent
from arkaine.tools.tool import Argument, Context
from arkaine.utils.templater import PromptTemplate


class ContentResponse:
    """
    Structured response from the ContentQuery containing the answer,
    whether an answer was found, and any notes collected during processing.
    """

    def __init__(
        self,
        answer: str,
        notes: List[str] = None,
    ):
        self.answer = answer
        self.notes = notes

    def to_json(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "notes": self.notes if self.notes else "",
        }

    def __str__(self) -> str:
        if self.answer:
            result = f"Answer: {self.answer}\n"
        else:
            result = "No definitive answer was found in the content.\n"
        if self.notes:
            result += "\nNotes:\n"
            for note in self.notes:
                result += f"- {note}\n"
        return result


class ContentQuery(IterativeAgent):
    """An agent that processes documents chunk by chunk to answer queries.

    This agent takes a document and a query, breaks the document into
    manageable chunks, and processes each chunk to find relevant information
    and answers. It maintains context across chunks by collecting notes and can
    either stop at the first answer or process the entire document.

    The agent uses delimiters to identify notes and answers in the LLM's
    responses, allowing for structured information gathering. It can return
    either just the answer string or a full ContextResponse with both answer
    and collected notes.

    Args:
        llm (LLM): The language model to use for processing
        word_limit (Optional[int]): Maximum words per chunk. If None, uses
            llm.context_length / 10
        notes_delimiter (str): Delimiter used to identify notes sections.
            Defaults to "NOTES:"
        answer_delimiter (str): Delimiter used to identify answer sections.
            Defaults to "ANSWER FOUND:"
        words_overlap (int): Number of words to overlap between chunks.
            Defaults to 10
        return_string (bool): If True, returns just the answer string. If
            False, returns ContentResponse. Defaults to True
        read_full_doc (bool): If True, processes entire document even after
            finding an answer. Defaults to False
        default_answer (Optional[str]): Default answer to return if none
            found. Defaults to None
    """

    def __init__(
        self,
        llm: LLM,
        word_limit: Optional[int] = None,
        notes_delimiter: str = "NOTES:",
        answer_delimiter: str = "ANSWER FOUND:",
        words_overlap: int = 10,
        return_string: bool = True,
        read_full_doc: bool = False,
        default_answer: Optional[str] = None,
    ):
        super().__init__(
            name="content_query",
            description=(
                "Reads through a document to answer specific queries, "
                + "maintaining context across chunks"
            ),
            args=[
                Argument(
                    "text",
                    "The content to be read and analyzed",
                    "string",
                    required=True,
                ),
                Argument(
                    "query",
                    "The question or query to answer from the document",
                    "string",
                    required=True,
                ),
            ],
            llm=llm,
            initial_state={
                "chunks": [],
                "current_chunk": 0,
                "notes": [],
                "final_answer": None,
            },
        )

        if word_limit is None:
            if self.llm.context_length is None:
                raise ValueError(
                    "LLM context length and ContentQuery context length is "
                    "not set - we need to know approximal words per chunk to "
                    "process the content."
                )
            word_limit = int(self.llm.context_length / 10)
        self.token_limit = word_limit
        self.words_overlap = words_overlap
        self.notes_delimiter = notes_delimiter
        self.answer_delimiter = answer_delimiter
        self.return_string = return_string
        self.read_full_doc = read_full_doc
        self.default_answer = default_answer

        self.__templater = PromptTemplate.from_file(
            path.join(
                pathlib.Path(__file__).parent,
                "prompts",
                "content_query.prompt",
            ),
            defaults={
                "notes_delimiter": notes_delimiter,
                "answer_delimiter": answer_delimiter,
                "remember": (
                    "Your role is to be a meticulous and patient analyzer. "
                    "Prioritize accuracy and completeness over speed. "
                    "Your goal is to provide the most comprehensive and "
                    "accurate answer possible based solely on the document's "
                    "content."
                ),
            },
        )

    def __chunk_text(self, text: str) -> List[str]:
        """Divide text into overlapping chunks of specified word limit.

        Args:
            text (str): The input text to be chunked

        Returns:
            List[str]: List of text chunks with specified overlap

        Note:
            Chunks are created based on word boundaries and include overlap
            specified by self.words_overlap. All whitespace is normalized.
        """
        # Normalize whitespace: convert all whitespace sequences to single
        # spaces and handle various newline formats
        normalized_text = " ".join(text.split())

        # Split into words
        words = normalized_text.split(" ")
        chunks: List[str] = []
        start_idx = 0

        while start_idx < len(words):
            chunk = words[start_idx : start_idx + self.token_limit]
            chunks.append(" ".join(chunk))
            start_idx += self.token_limit - self.words_overlap

        return chunks

    def prepare_prompt(self, context: Context, **kwargs) -> Prompt:
        """Prepare the prompt for the language model.

        Args:
            context (Context): The execution context
            state (Dict[str, Any]): The current state of the agent
            **kwargs: Must include 'text' and 'query' arguments

        Returns:
            Prompt: Formatted prompt for the language model

        Note:
            If final is True, includes additional instructions to make a
            final decision based on all gathered information.
        """
        # First time through, initialize chunks
        if not context["chunks"]:
            text = kwargs["text"]
            context["chunks"] = self.__chunk_text(text)

        chunk = context["chunks"][context["current_chunk"]]
        is_final = context["current_chunk"] == len(context["chunks"]) - 1

        notes_text = "\n".join(context["notes"])
        vars = {
            "current_notes": notes_text,
            "query": kwargs["query"],
            "text": chunk,
        }

        if is_final:
            vars["remember"] = (
                "This is the final text segment. You must make a "
                "decision based on all the information you've gathered. "
                "Do not request more information or indicate that you're "
                "waiting for more text. Provide either a complete answer "
                "from all available information or {answer_delimiter} NONE."
            ).replace("{answer_delimiter}", self.answer_delimiter)

        return self.__templater.render(vars)

    def __extract(self, text: str) -> Tuple[Optional[List[str]], Optional[str]]:
        ret_notes = None
        ret_answer = None
        notes_parts = text.split(self.notes_delimiter)

        if len(notes_parts) > 1:
            notes = notes_parts[-1].strip()
            if self.answer_delimiter in notes:
                notes = notes.split(self.answer_delimiter)[0].strip()
            ret_notes = [
                n.strip("-").strip() for n in notes.splitlines() if n.strip()
            ]

        answer_parts = text.split(self.answer_delimiter)
        if len(answer_parts) > 1:
            answer = answer_parts[-1].strip()
            if answer.strip().startswith("NONE"):
                ret_answer = None
                return ret_notes, ret_answer

            cleaned_answer = "".join(
                c
                for c in answer.splitlines()[0].lower()
                if c.isalnum() or c.isspace()
            ).strip()

            if cleaned_answer in ["none", ""]:
                ret_answer = None
                return ret_notes, ret_answer

            if self.notes_delimiter in answer:
                answer = answer.split(self.notes_delimiter)[0].strip()

            ret_answer = answer

        return ret_notes, ret_answer

    def extract_result(self, context: Context, output: str) -> Optional[Any]:
        """Process document to answer query.

        Args:
            context (Context): The execution context
            state (Dict[str, Any]): The current state of the agent
            output (str): Model response text to process

        Returns:
            Optional[Any]: Contains answer and collected notes. If
                return_string is True, returns just the answer string.

        Note:
            Processes document in chunks, collecting notes and searching for
            answers. Can process entire document if read_full_doc is True.
            Uses default_answer if no answer found and default_answer is set.
        """
        # Extract notes and answer and add to state
        notes, answer = self.__extract(output)
        if notes:
            context.concat("notes", notes)
        if answer:
            context["final_answer"] = answer
            # If we don't need to read the full doc and found an answer, return
            if not self.read_full_doc:
                return self._format_response(context)

        # Move to next chunk
        context.increment("current_chunk")

        # If we've processed all chunks or found our answer, return result
        if context["current_chunk"] >= len(context["chunks"]):
            if (
                context["final_answer"] is None
                and self.default_answer is not None
            ):
                context["final_answer"] = self.default_answer
            return self._format_response(context)

        return None

    def _format_response(self, context: Context) -> Any:
        if self.return_string:
            return context["final_answer"]
        return ContentResponse(
            answer=context["final_answer"],
            notes=context["notes"],
        )
