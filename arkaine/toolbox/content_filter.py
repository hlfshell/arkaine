from typing import Any, Dict, List, Optional, Tuple

from arkaine.internal.store.embeddings import InMemoryEmbeddingStore
from arkaine.tools.tool import Argument, Context, Tool
from arkaine.tools.wrapper import Wrapper
from arkaine.utils.documents import cosine_distance
from arkaine.utils.embeddings.model import OllamaEmbeddingModel


class ContentFilter(Tool):
    """
    A tool that filters a body of text based on semantic similarity to a query.
    Can optionally cluster results and return only the highest scoring cluster.

    Args:
        name (str): Name for this filter instance. Defaults to "ContentFilter"

        description (str): Description for this filter instance.

        n (int): Number of top results to return. Defaults to 5.

        embedder (Optional[InMemoryEmbeddingStore]): Custom embedding store to
            use. If None, a fresh InMemoryEmbeddingStore is created for
            each call. If a class is provided, it will be instantiated with
            embedder_arguments for each call. If an object instance is
            provided, it will be reused for all calls (embedder_arguments
            ignored).

        embedder_arguments (Optional[Dict[str, Any]]): Arguments to initialize
            the embedder class. Required when embedder is a class. Ignored when
            embedder is None or an instance. Example: {"model":
            "text-embedding-3-small"}

        cluster_threshold (Optional[float]): If set, will cluster results and
        return
            only the highest scoring cluster. Values between 0-1, with higher
            values creating tighter clusters. Recommended range: 0.7-0.9
    """

    def __init__(
        self,
        name: str = "ContentFilter",
        description: Optional[str] = None,
        n: int = 5,
        embedding_store: Optional[InMemoryEmbeddingStore] = None,
        embedding_store_args: Optional[Dict[str, Any]] = None,
        cluster_threshold: Optional[float] = None,
    ):
        self.n = n
        self.cluster_threshold = cluster_threshold

        # Validate embedder and embedder_arguments combination
        if embedding_store is None:
            self.embedding_store = InMemoryEmbeddingStore
            self.embedding_store_args = {
                "embedding_model": OllamaEmbeddingModel()
            }
        elif isinstance(embedding_store, type):
            if embedding_store_args is None:
                raise ValueError(
                    "embedder_arguments required when embedder is a class"
                )
            self.embedding_store = embedding_store
            self.embedding_store_args = embedding_store_args
        else:
            if embedding_store_args:
                raise ValueError(
                    "embedder_arguments should be None when embedder is an"
                    + " instance"
                )
            self.embedding_store = embedding_store
            self.embedding_store_args = None

        args = [
            Argument(
                "content",
                "The text content to filter",
                "string",
                required=True,
            ),
            Argument(
                "query",
                "Query to filter results against",
                "string",
                required=True,
            ),
        ]

        if description is None:
            description = (
                f"Filters text content to the {n} most relevant results "
                "based on semantic similarity to a query."
            )
            if cluster_threshold:
                description += (
                    f" Results are clustered with threshold {cluster_threshold} "
                    "and only the highest scoring cluster is returned."
                )

        super().__init__(name, description, args, self.filter_content)

    def _process_content(self, content: Any) -> List[str]:
        """Convert various input types to list of strings for embedding."""
        if isinstance(content, str):
            # Split on newlines and filter out empty strings and whitespace-only strings
            lines = [line.strip() for line in content.split("\n")]
            return [line for line in lines if line]
        elif isinstance(content, dict):
            return [str(v) for v in content.values()]
        elif isinstance(content, (list, tuple)):
            return [str(x) for x in content]
        else:
            return [str(content)]

    def _cluster_results(
        self, results: List[Any], scores: List[float]
    ) -> List[Any]:
        """
        Cluster results based on similarity scores and return highest cluster.
        Uses a simple threshold-based clustering approach.
        """
        if not results:
            return []

        # Start with highest scoring result
        clusters = [[0]]  # List of clusters, each containing result indices

        # Group remaining results into clusters
        for i in range(1, len(results)):
            score_diff = abs(scores[0] - scores[i])

            if score_diff <= self.cluster_threshold:
                clusters[0].append(i)
            else:
                # Start new cluster
                clusters.append([i])

        # Return items from highest scoring cluster
        return [results[i] for i in clusters[0]]

    def filter_content(self, content: str, query: str) -> List[str]:
        """Filter content based on similarity to query."""
        items = self._process_content(content)

        if self.embedding_store_args is not None:
            embedder = self.embedding_store(**self.embedding_store_args)
        else:
            embedder = self.embedding_store

        embedder.add_text(items)

        # Get top N results
        filtered = embedder.query(query, top_n=self.n)

        if self.cluster_threshold:
            # Get similarity scores for clustering
            query_embedding = embedder.get_embedding(query)
            scores = [
                cosine_distance(query_embedding, embedder.get_embedding(item))
                for item in filtered
            ]
            filtered = self._cluster_results(filtered, scores)

        return filtered


class ContentFilterWrapper(Wrapper):
    """
    A wrapper that filters another tool's output using semantic similarity.

    Args:
        tool (Tool): The tool to wrap
        name (Optional[str]): Name for the wrapper. Defaults to
            "{tool.name}::cf"
        n (int): Number of top results to return
        embedder (Optional[InMemoryEmbeddingStore]): Custom embedding store to
            use
        embedder_arguments (Optional[Dict[str, Any]]): Arguments to initialize
            the embedder class. Required when embedder is a class. Ignored when
            embedder is None or an instance. Example: {"model":
            "text-embedding-3-small"}
        cluster_threshold (Optional[float]): Clustering threshold (0-1)
        argument_name (str): Name of the argument that contains the query.
            Defaults to "query". This is to be used when the wrapped tool
            takes multiple arguments and the query is passed in as one of them.
    """

    def __init__(
        self,
        tool: Tool,
        name: Optional[str] = None,
        n: int = 5,
        embedder: Optional[InMemoryEmbeddingStore] = None,
        embedder_arguments: Optional[Dict[str, Any]] = None,
        cluster_threshold: Optional[float] = None,
        argument_name: str = "query",
    ):
        if name is None:
            name = f"{tool.name}::cf"

        self.argument_name = argument_name

        description = (
            f"Filters the output of {tool.name} to the {n} most relevant "
            + " results based on semantic similarity to a query."
        )
        if cluster_threshold:
            description += (
                f" Results are clustered with threshold {cluster_threshold} "
                "and only the highest scoring cluster is returned."
            )

        self.content_filter = ContentFilter(
            n=n,
            embedding_store=embedder,
            embedding_store_args=embedder_arguments,
            cluster_threshold=cluster_threshold,
        )

        super().__init__(
            name,
            description,
            tool,
            [
                Argument(
                    self.argument_name,
                    "Query to filter results against",
                    "string",
                    required=True,
                )
            ],
        )

    def preprocess(self, ctx: Context, **kwargs) -> Tuple[Dict[str, Any], str]:
        """Remove query from kwargs before passing to wrapped tool."""
        filtered_kwargs = kwargs.copy()
        query = filtered_kwargs.pop(self.argument_name)
        return filtered_kwargs, query

    def postprocess(self, ctx: Context, passed: Any, result: Any) -> Any:
        """Filter the tool's output using the content filter."""
        return self.content_filter(content=result, query=passed)
