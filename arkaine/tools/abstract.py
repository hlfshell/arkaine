from abc import ABC
from typing import Dict, List, Optional

from arkaine.llms.llm import LLM
from arkaine.tools.agent import Agent
from arkaine.tools.argument import Argument
from arkaine.tools.example import Example
from arkaine.tools.result import Result
from arkaine.tools.tool import Tool


class AbstractTool(Tool, ABC):
    """
    Abstract base class for creating tools with enforced argument patterns and
    required methods. Inherits from both Tool and ABC to provide tool
    functionality with abstract method support.
    """

    # Class variable to store argument rules
    _argument_rules: Dict[str, List[str]] = {
        "required_args": [],  # List of required argument names
        "allowed_args": [],  # List of allowed argument names
    }

    def __init__(self, *args, **kwargs):
        # Verify that all abstract methods are implemented.
        self._validate_abstract_methods()
        # Call parent __init__ so that attributes like self.args are properly
        # assigned.
        super().__init__(*args, **kwargs)
        # Now that self.args is available, validate the arguments.
        self._validate_argument_rules(self.args)

    def _validate_abstract_methods(self):
        """Ensures all abstract methods are implemented"""
        for method_name in getattr(self, "__abstractmethods__", set()):
            raise NotImplementedError(
                f"Can't instantiate abstract class {self.__class__.__name__} "
                f"with abstract method {method_name}"
            )

    def _validate_argument_rules(self, args: List[Argument]):
        """
        Validates that the provided arguments match the defined rules.

        Args:
            args: List of Argument objects to validate

        Raises:
            ValueError: If arguments don't match the defined rules
        """
        rules = self._argument_rules
        provided_args = {arg.name: arg for arg in args}

        # Check required arguments
        for required_arg in rules["required_args"]:
            if required_arg.name not in provided_args:
                raise ValueError(
                    f"Required argument '{required_arg.name} - "
                    f"{required_arg.type_str}' is missing for "
                    f"{self.__class__.__name__}"
                )
            # Check that the provided argument has the expected type.
            provided = provided_args[required_arg.name]
            if required_arg.type_str.lower() != provided.type_str.lower():
                raise ValueError(
                    f"Required argument '{required_arg.name}' is of type "
                    f"{required_arg.type_str} but provided argument is of "
                    f"type {provided.type_str}"
                )

        # If allowed_args is specified, verify that any provided argument is
        # allowed.
        if rules.get("allowed_args"):
            allowed_arg_names = {arg.name for arg in rules["allowed_args"]}
            for name in provided_args.keys():
                if name not in allowed_arg_names and name not in {
                    arg.name for arg in rules["required_args"]
                }:
                    raise ValueError(
                        f"Argument '{name}' is not in the allowed arguments "
                        f"list for {self.__class__.__name__}"
                    )


class AbstractAgent(Agent, AbstractTool):
    """
    AbstractAgent is an abstract base class for LLM-based agents that require
    both:

      • The abstract interface defined in Agent (i.e., implementing
        prepare_prompt and extract_result).
      • The argument validation behavior provided by AbstractTool.

    Any subclass must implement:
        - prepare_prompt(self, context: Context, **kwargs) -> Prompt
        - extract_result(self, context: Context, output: str) -> Optional[Any]
    """

    def __init__(
        self,
        name: str,
        description: str,
        args: List[Argument],
        llm: LLM,
        examples: List[Example] = [],
        id: Optional[str] = None,
        result: Optional[Result] = None,
    ):
        # Using super() here will follow the MRO: AbstractAgent -> AbstractTool
        # -> Agent -> Tool -> ABC. AbstractTool.__init__ will perform the
        # abstract method check and validate `args` (by pulling it from kwargs)
        # and then call Agent.__init__ which sets self.llm.
        super().__init__(
            name,
            description,
            args=args,
            llm=llm,
            examples=examples,
            id=id,
            result=result,
        )
