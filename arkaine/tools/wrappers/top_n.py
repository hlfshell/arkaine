from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from arkaine.internal.store.embeddings import (
    EmbeddingStore,
    InMemoryEmbeddingStore,
)
from arkaine.tools.tool import Argument, Context, Tool
from arkaine.tools.wrapper import Wrapper
from arkaine.utils.documents import chunk_text_by_sentences
from arkaine.utils.embeddings.model import OllamaEmbeddingModel


class TopN(Wrapper):
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
        n (int): Number of closest results to return
        embedder (Optional[InMemoryEmbeddingStore]): Custom embedding store to
            use. If None, a fresh InMemoryEmbeddingStore is created for each
            call. If a class is provided, it will be instantiated with
            embedder_kwargs for each call. If an object instance is provided,
            it will be reused for all calls (embedder_kwargs ignored).
        embedder_kwargs (Optional[Dict[str, Any]]): Arguments to initialize the
            embedder class. Required when embedder is a class. Ignored when
            embedder is None or an instance. Example: {"model":
            "text-embedding-3-small"}
        sentences_per (int, optional): Number of sentences per chunk. Defaults
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
        n: int,
        embedder: Optional[EmbeddingStore] = None,
        embedder_kwargs: Optional[Dict[str, Any]] = None,
        sentences_per: int = 3,
        tool_formatter: Optional[Callable[[str], Union[str, List[str]]]] = None,
        output_formatter: Optional[Callable[[str], str]] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        query_attribute: str = "query",
        query_description: Optional[str] = None,
    ):
        # Validate embedder and embedder_kwargs combination
        if embedder is None:
            self._embedder = InMemoryEmbeddingStore
            self._embedder_kwargs = {"embedding_model": OllamaEmbeddingModel()}
        elif isinstance(embedder, type):
            if embedder_kwargs is None:
                raise ValueError(
                    "embedder_kwargs required when embedder is a class"
                )
            self._embedder = embedder
            self._embedder_kwargs = embedder_kwargs
        else:
            if embedder_kwargs:
                raise ValueError(
                    "embedder_kwargs should be None when embedder is an "
                    + "instance"
                )
            self._embedder = embedder
            self._embedder_kwargs = None

        self._n = n
        self._sentences_per = sentences_per
        self._tool_formatter = tool_formatter
        self._output_formatter = output_formatter
        self._query_attribute = query_attribute

        if not name:
            name = f"{tool.name}::top_{n}"

        if not description:
            description = tool.description

        if not query_description:
            query_description = "The query to search for in the content"

        args = [
            Argument(
                name=query_attribute,
                description=query_description,
                type="str",
                required=True,
            )
        ]

        super().__init__(
            name=name, description=description, tool=tool, args=args
        )

    def preprocess(self, ctx: Context, **kwargs) -> Tuple[Dict[str, Any], Any]:
        """Extract query and prepare arguments for the wrapped tool."""
        if self._query_attribute not in kwargs:
            raise ValueError(
                f"The {self._query_attribute} argument is required for this "
                + "tool"
            )

        # Extract query and pass it through to postprocess
        query = kwargs.pop(self._query_attribute)

        # Return processed args and the query as pass-through data
        return kwargs, query

    def postprocess(
        self, ctx: Context, passed: Optional[Any] = None, results: Any = None
    ) -> str:
        """Process the tool results using semantic search."""
        query = passed

        if self._tool_formatter:
            results = self._tool_formatter(results)

        if isinstance(results, str):
            results = [results]
        elif isinstance(results, dict):
            results = list(results.values())

        chunks = [
            chunk_text_by_sentences(item, self._sentences_per)
            for item in results
        ]

        # Initialize embedder based on configuration
        if self._embedder_kwargs is not None:
            embedder = self._embedder(**self._embedder_kwargs)
        else:
            embedder = self._embedder

        for chunk in chunks:
            embedder.add_text(chunk)

        search_results = embedder.query(query, top_n=self._n)

        if self._output_formatter:
            return self._output_formatter(search_results)

        out = (
            f"Here are the top {self._n} most relevant sections "
            + "to the query:\n"
        )

        for index, result in enumerate(search_results):
            out += f"{index + 1} - {result}\n"

        return out
