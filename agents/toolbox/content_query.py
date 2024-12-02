from os import path
import pathlib
from typing import List, Optional, Dict, Any

from agents.agent import Agent
from agents.llms.llm import LLM, Prompt
from agents.utils.templater import PromptTemplate
from agents.tools.tool import Argument, Context


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


class ContentQuery(Agent):
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
        # Normalize whitespace: convert all whitespace sequences to single spaces
        # and handle various newline formats
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

    def prepare_prompt(
        self, query: str, notes: str, text: str, final: bool
    ) -> Prompt:
        """Prepare the prompt for the language model.

        Args:
            query (str): The question to be answered
            notes (str): Previously collected notes
            text (str): Current text chunk to analyze
            final (bool): Whether this is the final chunk

        Returns:
            Prompt: Formatted prompt for the language model

        Note:
            If final is True, includes additional instructions to make a
            final decision based on all gathered information.
        """
        notes_text = "\n".join(notes)
        vars = {
            "current_notes": notes_text,
            "query": query,
            "text": text,
        }
        if final:
            vars["remember"] = (
                "This is the final text segment. You must make a "
                "decision based on all the information you've gathered. "
                "Do not request more information or indicate that you're "
                "waiting for more text. Provide either a complete answer "
                "from all available information or {answer_delimiter} NONE."
            )
            vars["remember"] = vars["remember"].replace(
                "{answer_delimiter}", self.answer_delimiter
            )

        return self.__templater.render(vars)

    def __notes(self, context: Context, text: str) -> Optional[List[str]]:
        """Extract notes from model response and update context.

        Args:
            context (Context): The execution context
            text (str): Model response text to process

        Returns:
            Optional[List[str]]: List of extracted notes or None if no notes found

        Note:
            Notes are expected to be prefixed with '-' and appear after
            notes_delimiter. Updates context['notes'] with found notes.
        """
        notes_parts = text.split(self.notes_delimiter)

        if len(notes_parts) > 1:
            # Take the last notes section if multiple exist
            notes = notes_parts[-1].strip()
            # Remove any answer delimiter and content that follows
            if self.answer_delimiter in notes:
                notes = notes.split(self.answer_delimiter)[0].strip()

            # Our model is told to preface the notes with -
            # so we need to remove those and create an array of notes
            notes = [
                n.strip("-").strip() for n in notes.splitlines() if n.strip()
            ]

            # Record notes to ctx
            if "notes" not in context:
                context["notes"] = []
            context["notes"].extend(notes)

            return notes
        else:
            return None

    def __answer(self, text: str) -> Optional[str]:
        """Extract answer from model response.

        Args:
            text (str): Model response text to process

        Returns:
            Optional[str]: Extracted answer or None if no valid answer found

        Note:
            Answers must appear after answer_delimiter. Handles edge cases like
            'NONE' responses and formatting issues.
        """
        answer_parts = text.split(self.answer_delimiter)
        if len(answer_parts) > 1:
            answer = answer_parts[-1].strip()

            # Sometimes a smaller model will output weird formatting. If the
            # first line of the answer is just "none" or empty, ignore it.
            # Remove all symbols in case of formatting issues with first line.
            # Similarly, we safely abort if the whole answer starts with all
            # caps NONE as well.
            if answer.strip().startswith("NONE"):
                return None

            cleaned_answer = "".join(
                c
                for c in answer.splitlines()[0].lower()
                if c.isalnum() or c.isspace()
            ).strip()

            if cleaned_answer in ["none", ""]:
                return None

            # Remove any notes delimiter and content that follows
            if self.notes_delimiter in answer:
                answer = answer.split(self.notes_delimiter)[0].strip()

            return answer
        else:
            return None

    def __call__(
        self, context: Optional[Context] = None, **kwargs
    ) -> ContentResponse:
        """Process document to answer query.

        Args:
            context (Optional[Context]): Execution context
            **kwargs: Must include 'text' and 'query' arguments

        Returns:
            ContentResponse: Contains answer and collected notes. If
                return_string is True, returns just the answer string.

        Note:
            Processes document in chunks, collecting notes and searching for
            answers. Can process entire document if read_full_doc is True.
            Uses default_answer if no answer found and default_answer is set.
        """
        with self._init_context_(context, **kwargs) as ctx:
            kwargs = self.fulfill_defaults(kwargs)
            self.check_arguments(kwargs)

            text = kwargs["text"]
            query = kwargs["query"]

            chunks = self.__chunk_text(text)

            # Process each chunk while maintaining relevant notes
            notes = []
            final_answer: Optional[str] = None

            for index, chunk in enumerate(chunks):
                prompt = self.prepare_prompt(
                    query, notes, chunk, index == len(chunks) - 1
                )

                response = self.llm.completion(prompt)

                # Extract notes and answer independently, regardless of order
                current_notes = self.__notes(ctx, response)
                if current_notes:
                    notes.extend(current_notes)

                # Check for answer separately
                answer = self.__answer(response)

                # If we found an answer and don't need to read full doc, we can stop
                if answer and not self.read_full_doc:
                    final_answer = answer
                    break
                elif answer:
                    final_answer = answer

            # If no answer was found and default_answer is set, use it
            if final_answer is None and self.default_answer is not None:
                final_answer = self.default_answer

            if self.return_string:
                return final_answer
            else:
                return ContentResponse(
                    answer=final_answer,
                    notes=notes,
                )
