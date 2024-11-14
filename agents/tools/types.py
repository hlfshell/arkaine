from typing import Any, Dict, List, Tuple

# ToolArguments are a dict of the arguments passed to a function, with the key
# being the argument name and the value being the argument value.
ToolArguments = Dict[str, Any]

# ToolResults are a type representing a set of of possible tool calls,
# arguments provided, and their results, representing a history of queries from
# an LLM to their tools. The format is a list of tuples; each tuple represents
# the name of the tool, a ToolArguments, and finally the return result of that
# tool.
ToolResults = List[Tuple[str, ToolArguments, Any]]
