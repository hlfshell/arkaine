from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Optional

from arkaine.tools.context import Context
from arkaine.tools.tool import Tool
from arkaine.utils.clustering import find_optimal_cluster_representative


class SelfConsistency(Tool):

    def __init__(
        self,
        tool: Tool,
        executions: int,
        embedding_generator: Callable[[str], List[float]],
        max_workers: Optional[int] = None,
        name: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        if executions < 3:
            raise ValueError(
                "Need at least 3 executions to perform self-consistency"
            )

        super().__init__(
            name=name or tool.name + ":self_consistency",
            description=tool.description,
            args=tool.args,
            func=tool.func,
            examples=tool.examples,
        )

        self.executions = executions
        self.__tool = tool
        self.__embedding_generator = embedding_generator
        self.max_workers = max_workers
        self._threadpool = ThreadPoolExecutor(
            max_workers=self.max_workers, thread_name_prefix=f"{self.name}::"
        )
        self.timeout = timeout

    def __del__(self):
        self._threadpool.shutdown(wait=False)

    def invoke(self, context: Context, **kwargs):
        contexts: List[Context] = []

        # Launch all executions
        for _ in range(self.executions):
            ctx = self.__tool.async_call(context, **kwargs)
            contexts.append(ctx)

        for idx, ctx in enumerate(contexts):
            ctx.wait(timeout=self.timeout)

        done_contexts = [ctx for ctx in contexts if ctx.status == "complete"]

        if len(done_contexts) <= 2:
            for ctx in contexts:
                if ctx.exception is not None:
                    raise ctx.exception
            raise RuntimeError("Need at least 3 successful executions")

        # Generate embeddings for successful executions
        vectors = [
            self.__embedding_generator(ctx.output) for ctx in done_contexts
        ]

        # Find the most representative output
        cluster_representative = find_optimal_cluster_representative(vectors)

        # The cluster representative is supposedly "the most correct" output
        return done_contexts[cluster_representative].output
