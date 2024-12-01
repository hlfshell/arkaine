from agents.tools.tool import Tool, Context, Argument
from agents.utils.documents import (
    InMemoryEmbeddingStore,
    chunk_text_by_sentences,
)
from typing import Callable, List, Optional, Union


class TopN(Tool):
    """A wrapper tool that filters another tool's output using semantic search.

    This tool takes the output from another tool, chunks it into sentences, and
    returns the most semantically relevant sections based on a user query. It
    uses embeddings to perform the semantic search.

    If the tool being wrapped returns a string, it is simply chunked into
    sentences. If, however, the tool returns a list of strings, each item is
    individually chunked, maintaining separation of sections. If the output is
    a dictionary of [str, str], the .values() are utilized.

    Args:
        tool (Tool): The base tool to wrap and filter results from the wrapped
            tool
        embedder (InMemoryEmbeddingStore): An in memory embedding store for
            semantic search
        n (int): Number of closest results to return sentences_per (int,
        optional): Number of sentences per chunk. Defaults
            to 3.
        tool_formatter (Callable[[str], Union[str, List[str]]], optional):
            Custom formatter for the tool's output. This modifies the output to
            a string or a list of strings before being chunked. If not
            provided, we utilize the raw tool output.
        output_formatter (Callable[[str], str], optional): Custom formatter for
            the output of the top N results. This modifies the output to a
            string for future consumption. By default (when None), it will
            print "Here are the top {N} most relevant sections to the query:"
            followed by the results numerically ordered.
        name (str, optional): Custom name for the tool. Defaults to
            "{tool.name}::top_{n}".
        description (str, optional): Custom description. Defaults to base
            tool's description.
        query_attribute (str, optional): Name of the query parameter. Defaults
            to "query".
        query_description (str, optional): Description of the query parameter.
            Defaults to "The query to search for in the content".
    """

    def __init__(
        self,
        tool: Tool,
        embedder: InMemoryEmbeddingStore,
        n: int,
        sentences_per: int = 3,
        tool_formatter: Optional[Callable[[str], Union[str, List[str]]]] = None,
        output_formatter: Optional[Callable[[str], str]] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        query_attribute: str = "query",
        query_description: Optional[str] = None,
    ):
        self._tool = tool
        self._n = n
        self._embedder = embedder
        self._sentences_per = sentences_per
        self._tool_formatter = tool_formatter
        self._output_formatter = output_formatter
        self._query_attribute = query_attribute

        if not name:
            name = f"{tool.name}::top_{n}"

        if not description:
            description = tool.description

        if not query_description:
            query_description = query_description
        else:
            query_description = "The query to search for in the content"

        args = tool.args
        args.append(
            Argument(
                name=query_attribute,
                description=query_description,
                type="str",
                required=True,
            )
        )

        super().__init__(
            name=name, args=args, description=description, func=self.top_n
        )

    def top_n(self, context: Context, **kwargs):
        """
        Execute the wrapped tool and filter its output using semantic search.

        Args:
            context (Context): The execution context

            **kwargs: Arguments to pass to the wrapped tool, must include
                query_attribute

        Returns:
            str: Formatted string containing the top N most relevant sections

        Raises:
            ValueError: If the required query attribute is missing from kwargs
        """
        if self._query_attribute not in kwargs:
            raise ValueError(
                f"The {self._query_attribute} argument is required for this "
                + "tool"
            )

        query = kwargs[self._query_attribute]

        out = self._tool.invoke(context, **kwargs)

        if self._tool_formatter:
            out = self._tool_formatter(out)

        if isinstance(out, str):
            out = [out]
        elif isinstance(out, dict):
            out = list(out.values())

        chunks = [
            chunk_text_by_sentences(item, self._sentences_per) for item in out
        ]

        for chunk in chunks:
            self._embedder.add_text(chunk)

        results = self._embedder.query(query, top_n=self._n)

        if self._output_formatter:
            return self._output_formatter(results)
        else:
            out = (
                f"Here are the top {self._n} most relevant sections "
                + "to the query:\n"
            )

            for index, result in enumerate(results):
                out += f"{index + 1} - {result}\n"

            return out
