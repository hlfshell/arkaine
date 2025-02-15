from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

from arkaine.tools.toolify import toolify
from arkaine.tools.events import ToolReturn
from arkaine.tools.tool import Argument, Context, Tool


class ParallelList(Tool):
    """A wrapper that executes a tool in parallel across a list of inputs.

    This tool takes a list of inputs and runs the wrapped tool for each item
    concurrently. Each input can be optionally formatted before being passed to
    the tool, and the final results can be aggregated using a custom formatter.

    ParallelList can be prepped in a number of ways.

    Args:
        tool (Tool): The base tool to wrap and execute for each input
        args (Optional[Union[List[Argument], Dict[str, str], str]]): The arguments
            for the input of the parallel_list tool. There are three ways to
            provide this:

            - A list of Argument objects, which will be used as the arguments
              for the tool. This allows you to set the arguments as you wish,
              and is intended to be used in conjunction with the args_transform
              argument.
            - A dictionary, which will be used to rename the arguments of the
              tool. The keys are the new names, and the values are the string of
              the existing names. The goal is to allow name mapping to make sense, like
              foo -> foos

            In both of these cases, the arguments being passed on call are expected to be
            called in the manner of:

            parallel_list(a=[1,2,3], b = [a,b,c])

            ...where a and b are arguments of the tool. That is, the index of the
            passed iterable to each argument resides in the same index. Be wary
            of optional arguments in this case.

            If instead you wish to utilize parallel_list in the following manner:

            parallel_list([{"a": 1, "b": 2}, {"a": 3, "b": 4}])

            ...wherein you are passing a list of dictionaries, each expected to be
            a unique set of arguments, you can utilize the following options:

            - Argument: A singular argument object, which we assume is the input list
                as described above.
            - A string, which will be used as the name of the input argument.


        args_transform (Optional[Callable[[Any], Tuple[Optional[List[Any]],
            Optional[Dict[str, Any]]]]): Optional function to format the
            arguments passed into parallel list into whatever format your tool
            would expect. This allows you to use different names/argument types
            for the input of the wrapped tool. This is only available if args
            is provided as a List[Argument].
        result_formatter (Optional[Callable[[List[Any]], Any]]): Optional
            function to format the combined results. If not provided, returns
            the list of results. Note that the list of results is provided in
            the same order as the input. If the error strategy is to ignore
            errors, the list of results will still be the same size as the
            input, but with an Exception object in the place of the result for
            each item that failed. If the completion strategy is for "n" or
            "any", the list of results will contain None for each input that
            was not completed but didn't fail.
        max_workers (Optional[int]): Maximum number of concurrent executions.
        completion_strategy (str): How to handle completion:
            - "all": Wait for all items (default)
            - "any": Return after first successful completion
            - "n": Return after N successful completions
            - "majority": Return after majority of items complete
        completion_count (Optional[int]): Required when completion_strategy="n";
            # of successful completions to wait for.
        error_strategy (str): How to handle errors:
            - "ignore": Continue execution (default)
            - "fail": Stop all execution on first error
            Defaults to "fail"
        name (Optional[str]): Custom name for the wrapper. Defaults to
            "{tool.name}::parallel_list"
        description (Optional[str]): Custom description. Defaults to describing
            the parallel execution behavior and then the wrapped tool's
            description.
    """

    def __init__(
        self,
        tool: Union[Tool, Callable[[Context, Any], Any]],
        args: Optional[
            Union[Dict[str, str], List[Argument], Argument, str]
        ] = None,
        args_transform: Optional[
            Callable[
                [Any], Tuple[Optional[List[Any]], Optional[Dict[str, Any]]]
            ]
        ] = None,
        result_formatter: Optional[Callable[[List[Any]], Any]] = None,
        max_workers: Optional[int] = None,
        completion_strategy: str = "all",
        completion_count: Optional[int] = None,
        error_strategy: str = "fail",
        name: Optional[str] = None,
        description: Optional[str] = None,
    ):
        if isinstance(tool, Tool):
            self.tool = tool
        else:
            self.tool = toolify(tool)

        if completion_strategy not in ["all", "any", "n", "majority"]:
            raise ValueError(
                "completion_strategy must be one of: all, any, n, majority"
            )

        if completion_strategy == "n" and not completion_count:
            raise ValueError(
                "completion_count required when completion_strategy is 'n'"
            )

        if error_strategy not in ["ignore", "fail"]:
            raise ValueError("error_strategy must be one of: ignore, fail")

        self._args_transform = args_transform
        self._result_formatter = result_formatter
        self._completion_strategy = completion_strategy
        self._completion_count = completion_count
        self._error_strategy = error_strategy
        self._threadpool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=f"{name or self.tool.name}::parallel",
        )

        if not name:
            name = f"{self.tool.name}::parallel_list"

        if not description:
            description = (
                f"Executes {self.tool.name} in parallel across a list of "
                f"inputs. {self.tool.name} is:\n{self.tool.description}"
            )

        # Build our arguments. We can either:
        # A) Utilize the same arguments as the tool
        # B) Set up a whole new list of arguments, with the plan of using
        #   args_transform to format the inputs
        # C) Use the dict to "rename" arguments and convert them into a list
        #   of the arguments of the tool's original inputs.
        arguments: List[Argument] = []
        if isinstance(args, dict):
            self.__args_type = "renamed"
            # Create a copy of the tool's args that have keys, but replace the
            # name with the key of the dict, and the type to a list[x] of
            # whatever it was Every other arg is added as specified
            args_used: Set[str] = set()
            self._renamed_args = {}
            for key, value in args.items():
                self._renamed_args[key] = value

                # Get the arg of the same name. If it doesn't exist, raise
                # an error
                arg = next(
                    (arg for arg in self.tool.args if arg.name == key), None
                )
                if arg is None:
                    raise ValueError(
                        f"Argument {value} not found in {self.tool.name}"
                    )
                args_used.add(key)

                argument = Argument(
                    name=key,
                    description=arg.description,
                    type=f"list[{arg.type_str}]",
                    required=arg.required,
                    default=arg.default,
                )
                arguments.append(argument)
            # All missing args are added as is
            for arg in self.tool.args:
                if arg.name not in args_used:
                    arguments.append(arg)
        elif isinstance(args, list):
            self.__args_type = "set"
            arguments = args
            if len(args) != 1:
                raise ValueError(
                    "Only one positional argument is supported when "
                    "manually setting args in a ParallelList - the expectation "
                    "is that you are passing in a list of dicts w/ keys "
                    "being the wrapped tool's arguments."
                )
            if self._args_transform is None:
                raise ValueError(
                    "args_transform is required when manually setting args "
                    "in a ParallelList"
                )
        elif isinstance(args, str):
            self.__args_type = "set"
            arguments = [
                Argument(
                    name=args,
                    description="A list of dicts, where the keys are the "
                    "wrapped tool's arguments, and the values are the values "
                    "to pass for each item in the input list.",
                    type="list[dict]",
                    required=True,
                    default=None,
                )
            ]
        elif args is None:
            self.__args_type = "original"
            arguments = self.tool.args
        else:
            raise ValueError(f"Invalid args type: {type(args)}")

        super().__init__(
            name=name,
            description=description,
            args=arguments,
            func=self.parallelize,
            examples=self.tool.examples,
        )

    def parallelize(self, context: Context, args, kwargs) -> List[Any]:
        if self._args_transform:
            args, kwargs = self._args_transform(args, kwargs)
            if args is None:
                args = []
            if kwargs is None:
                kwargs = {}

        # We support both args passed like:
        # parallel_list([1,2,3], b = [a,b,c])
        # and
        # parallel_list([{"a": 1, "b": 2}, { "a": 3, "b": 4}])
        # But we only support the second one if and only if
        # Check to see if we are passed a single var list
        if self.__args_type == "set":
            # Determine if the passed list is in args or kwargs
            if len(args) == 1:
                input_list = args[0]
            elif len(kwargs) == 1:
                if self.args[0].name not in kwargs:
                    raise ValueError(
                        f"Expected a singular list in {self.args[0].name}, "
                        f"instead received {kwargs.keys()[0]}"
                    )
                input_list = kwargs[self.args[0].name]
            else:
                raise ValueError(
                    "Expected a singular list argument, instead received "
                    f"{len(args) + len(kwargs)} positional arguments"
                )

            if not isinstance(input_list, Iterable):
                raise ValueError(
                    f"Expected a list in {self.args[0].name}, instead received "
                    f"{type(input_list)}"
                )
        else:
            # Create a dict of arguments based on self.args
            args_dict = {}
            if len(args) > len(self.args):
                raise ValueError(
                    f"Too many positional arguments provided: {len(args)} "
                    f"(expected {len(self.args)})"
                )

            for arg in self.args:
                for i in range(len(args)):
                    name = self.args[i].name
                    if (
                        self.__args_type == "renamed"
                        and name in self._renamed_args
                    ):
                        args_dict[self._renamed_args[name]] = args[i]
                    else:
                        args_dict[name] = args[i]

                    args_dict[self.args[i].name] = arg

            for key, value in kwargs.items():
                if key not in args_dict:
                    if (
                        self.__args_type == "renamed"
                        and key in self._renamed_args
                    ):
                        args_dict[self._renamed_args[key]] = value
                    else:
                        args_dict[key] = value
                else:
                    raise ValueError(
                        f"Argument {key} provided both as a positional "
                        "argument and a keyword argument"
                    )

            # Ensure that we have the same number of entries for each argument;
            # if not, raise an error
            entry_count = len(args_dict[self.tool.args[0].name])
            for key, value in args_dict.items():
                if len(value) != entry_count:
                    raise ValueError(
                        f"All arguments must have the same number of entries. "
                        f"{key} has {len(value)} entries, but "
                        f"{self.tool.args[0].name} has {entry_count}"
                    )

            # Convert to an input_list
            input_list: List[Dict[str, Any]] = []
            for i in range(entry_count):
                input_list.append({})
                for key, value in args_dict.items():
                    input_list[i][key] = value[i]

        # Fire off the tool in parallel with the executor for each input
        futures = {
            self._threadpool.submit(self.tool, context, **kwargs)
            for kwargs in input_list
        }

        # Based on the completion strategy, handle the futures
        context["results"] = [None] * len(input)
        if self._completion_strategy == "all":
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    context["results"][idx] = future.result()
                except Exception as e:
                    if self._error_strategy == "fail":
                        raise e
                    else:
                        context["results"][idx] = e
        elif self._completion_strategy == "any":
            # Wait for any future to complete
            future = next(as_completed(futures))
            idx = futures[future]
            try:
                context["results"][idx] = future.result()
            except Exception as e:
                if self._error_strategy == "fail":
                    raise e
                else:
                    context["results"][idx] = e
            # Cancel all other futures
            for future in futures:
                future.cancel()
        elif (
            self._completion_strategy == "n"
            or self._completion_strategy == "majority"
        ):
            # Wait for N futures to complete
            remaining_futures = set(futures.keys())

            # to_complete is utilized if the context already has a
            # "to_go_count", which is set within retries. It alerts us to there
            # being some number of output already complete, and thus we need to
            # make it to the completion count including these.
            if self._completion_strategy == "n":
                to_complete = (
                    context["to_go_count"]
                    if "to_go_count" in context
                    else self._completion_count
                )
            elif self._completion_strategy == "majority":
                to_complete = (
                    context["to_go_count"]
                    if "to_go_count" in context
                    else len(remaining_futures) // 2
                )

            completed = 0
            while completed < to_complete and remaining_futures:
                future = next(as_completed(remaining_futures))
                idx = futures[future]
                try:
                    context["results"][idx] = future.result()
                except Exception as e:
                    if self._error_strategy == "fail":
                        raise e
                    else:
                        context["results"][idx] = e
                completed += 1
                remaining_futures.remove(future)

            # Cancel all other futures
            for future in remaining_futures:
                future.cancel()

        # Format the results if a formatter is provided
        if self._result_formatter:
            return self._result_formatter(context["results"])
        else:
            return context["results"].copy()

    def retry(self, context: Context) -> Any:
        """
        Retry the parallel list execution. This attempts to retry only the
        failed items from the previous execution.
        """
        # Ensure that the context passed is in fact a context for this tool
        if context.attached is None:
            raise ValueError("no tool assigned to context")
        if context.attached != self:
            raise ValueError(
                f"context is not for {self.name}, is instead for "
                f"{context.attached.name}"
            )

        # Get the original args and clear the context for re-running
        args = context.args.copy()
        input_list = args[self.args[0].name]
        original_results = context["results"]
        context.clear(executing=True)

        with context:
            # Format inputs if needed
            if self._args_transform:
                input_list = [self._args_transform(item) for item in input_list]

            # Figure out which items failed in context["result"] - we create a
            # new list of outputs that only includes the failed/incomplete
            # items.
            failed_indices = [
                idx
                for idx, result in enumerate(context["results"])
                if result is None or isinstance(result, Exception)
            ]

            # Create a new list of inputs that only includes the failed items
            input_list = [input_list[idx] for idx in failed_indices]

            # We need to tell the paralellize function through the context that
            # *this* particular context already has a set amount complete.
            # Since we are clearing the results["output"], we can't count it
            # without setting it as an optional override.
            if self._completion_strategy == "n":
                context["to_go_count"] = self._completion_count - sum(
                    1
                    for result in context["results"]
                    if result is not None and not isinstance(result, Exception)
                )
            elif self._completion_strategy == "majority":
                context["to_go_count"] = (
                    (len(input_list) // 2)
                    + 1
                    - sum(
                        1
                        for result in context["results"]
                        if result is not None
                        and not isinstance(result, Exception)
                    )
                )

            context, kwargs = self.extract_arguments((context, input_list), {})
            output = self.parallelize(context, **kwargs)

            context["results"] = original_results

            # Now that we have the results for the failed indexes,
            # we need to now set these results to their corresponding
            # indexes in the original context["results"] list.
            for new_idx, old_idx in enumerate(failed_indices):
                context["results"][old_idx] = output[new_idx]

            context.output = context["results"]
            context.broadcast(ToolReturn(context["results"]))

            return context["results"]

    def __del__(self):
        self._threadpool.shutdown(wait=False)
