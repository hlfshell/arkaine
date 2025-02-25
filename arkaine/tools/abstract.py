from abc import ABC
from typing import Dict, List, Optional, Union

from arkaine.llms.llm import LLM
from arkaine.tools.agent import Agent
from arkaine.tools.argument import Argument
from arkaine.tools.example import Example
from arkaine.tools.result import Result
from arkaine.tools.tool import Tool


class AbstractTool(Tool, ABC):
    """
    Abstract base class for creating tools with enforced argument and result
    patterns and required methods. Inherits from both Tool and ABC to provide
    tool functionality with abstract method support.

    Example:
        ---
        ExampleTool(AbstractTool):
            _rules = {
                "args": {
                    "required": [Argument(name="arg1", type="str")],
                    "allowed": [Argument(name="arg2", type="int")],
                },
                "result": {
                    "required": ["str"],
                },
            }
        ---

    This example would force that any tool inheriting AbstractTool to have
    an argument called "arg1" of type "str" and an optional argument called
    "arg2" of type "int". It would also force that the result be a string.

    Note that abstract tool inherits from ABC.abc, and thus @abstractmethod
    decorators are supported and also checked.
    """

    # Class variable to store argument rules
    _rules: Dict[str, Dict[str, List[Union[str, Argument]]]] = {
        "args": {
            "required": [],
            "allowed": [],
        },
        "result": {
            "required": None,
        },
    }

    def __init__(self, *args, **kwargs):
        # Verify that all abstract methods are implemented.
        self._validate_abstract_methods()
        # Call parent __init__ so that attributes like self.args are properly
        # assigned.
        super().__init__(*args, **kwargs)
        # Now that self.args is available, validate the arguments.
        self._validate_argument_rules(self.args)
        # Validate the result if required.
        self._validate_result()

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
        self._ensure_rule_keys(self._rules)
        provided_args = {arg.name: arg for arg in args}

        # Check required arguments
        for required_arg in self._rules["args"]["required"]:
            if isinstance(required_arg, Argument):
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
            else:
                # Argument is a string, so just check the name
                if required_arg not in provided_args:
                    raise ValueError(
                        f"Required argument '{required_arg}' is missing for "
                        f"{self.__class__.__name__}"
                    )

        # If allowed_args is specified, verify that any provided argument is
        # allowed.
        if self._rules.get("allowed_args"):
            allowed_arg_names = {}
            for arg in self._rules["args"]["allowed"]:
                if isinstance(arg, Argument):
                    allowed_arg_names[arg.name] = arg.type_str
                else:
                    allowed_arg_names[arg] = None

            for name in provided_args.keys():
                if name not in allowed_arg_names and name not in {
                    arg.name for arg in self._rules["args"]["required"]
                }:
                    raise ValueError(
                        f"Argument '{name}' is not in the allowed arguments "
                        f"list for {self.__class__.__name__}"
                    )

                if allowed_arg_names[name] is not None:
                    if (
                        provided_args[name].type_str.lower()
                        != allowed_arg_names[name]
                    ):
                        raise ValueError(
                            f"Argument '{name}' is of type "
                            f"{provided_args[name].type_str} but must be of "
                            f"type {allowed_arg_names[name]}"
                        )

    def _validate_result(self):
        """
        Validates that, if the tool requires a result, the tool has a set
        Result and the types match one of the allowed/required types.
        """
        self._ensure_rule_keys(self._rules)
        if self._rules["result"]["required"]:
            if self.result is None:
                raise ValueError(
                    f"{self.__class__.__name__} requires a result but none "
                    "was provided."
                )
            if self.result.type_str not in self._rules["result"]["required"]:
                raise ValueError(
                    f"{self.__class__.__name__} result type "
                    f"{self.result.type_str} does not match one of the "
                    "required types: "
                    f"{self._rules['result']['required']}"
                )

    def _ensure_rule_keys(
        self, rules: Dict[str, List[str]]
    ) -> Dict[str, List[str]]:
        """
        Ensures all required rule keys exist in the rules dictionary.
        If a key is missing, it will be added with an empty list.

        Args:
            rules: Dictionary of rules to validate

        Returns:
            Dictionary with all required keys present
        """
        required_keys = ["args", "result"]
        required_args_keys = ["required", "allowed"]
        required_result_keys = ["required"]

        for key in required_keys:
            if key not in rules:
                rules[key] = {}

        for key in required_args_keys:
            if key not in rules["args"]:
                rules["args"][key] = []

        for key in required_result_keys:
            if key not in rules["result"]:
                rules["result"][key] = []

        self._rules = rules


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

    ...as well as the rules defined by the _rules attribute.
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
