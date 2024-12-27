from __future__ import annotations

import inspect
import random
import re
import string
from functools import wraps
from typing import Any, Callable, List, Optional, _GenericAlias, get_type_hints

from arkaine.tools.tool import Argument, Tool


def toolify(
    tool_name: Optional[str] = None, tool_description: Optional[str] = None
):
    """
    Decorator that converts a function into a Tool object.
    """

    def decorator(func: Callable) -> Tool:
        # Get function signature
        sig = inspect.signature(func)

        # Get type hints
        type_hints = get_type_hints(func)

        # Parse docstring
        doc_description, arg_descriptions, return_desc, doc_name = (
            _parse_docstring(func.__doc__)
        )

        # Determine name priority: explicit tool_name > docstring name > function name > random lambda name
        if func.__name__ == "<lambda>":
            name = tool_name or doc_name or f"lambda_{_generate_random_id()}"
        else:
            name = tool_name or doc_name or func.__name__

        # Use provided name/description or defaults
        description = tool_description or doc_description

        # Add return description to tool description if available
        if return_desc:
            description = (
                f"{description}\n\nReturns: {return_desc}"
                if description
                else f"Returns: {return_desc}"
            )
        elif not description:
            description = f"Tool for {func.__name__}"

        # Create Arguments list
        arguments: List[Argument] = []

        for param_name, param in sig.parameters.items():
            # Skip self/cls for methods
            if param_name in ("self", "cls", "context"):
                continue

            # Determine if argument is required
            required = param.default == inspect.Parameter.empty

            # Get default value if exists
            default = None if required else str(param.default)

            # Get type as string
            param_type = type_hints.get(param_name, "Any")
            type_str = _get_full_type_str(param_type)

            # Get description from docstring if available
            param_desc = arg_descriptions.get(
                param_name, f"Parameter {param_name}"
            )

            # Create Argument object
            arg = Argument(
                name=param_name,
                description=param_desc,
                type=type_str,
                required=required,
                default=default,
            )
            arguments.append(arg)

        # Create and return Tool
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        tool = Tool(
            name=name,
            description=description,
            args=arguments,
            func=wrapper,
        )

        return tool

    # Handle case where decorator is used without parentheses
    if callable(tool_name):
        func = tool_name
        tool_name = None
        return decorator(func)

    return decorator


def _parse_docstring(
    docstring: Optional[str],
) -> tuple[str, dict[str, str], Optional[str], Optional[str]]:
    """
    Parse a docstring to extract the name, description, argument descriptions,
    and return description.
    """
    if not docstring:
        return "", {}, None, None

    # Clean and split the docstring
    lines = [line.strip() for line in docstring.split("\n")]
    if not lines:
        return "", {}, None, None

    # Look for Name: tag
    name = None
    cleaned_lines = []
    for line in lines:
        if line.lower().startswith("name:"):
            name = line[5:].strip()
        else:
            cleaned_lines.append(line)

    # Process the rest of the docstring with cleaned lines
    lines = cleaned_lines

    description = []
    arg_descriptions: dict[str, str] = {}
    return_description = None

    # Find where the parameters section begins
    param_start_idx = len(lines)
    param_indicators = [
        ":param",
        "Args:",
        "Parameters:",
        "Arguments:",
    ]

    plain_param_pattern = re.compile(r"\s*\w+\s+(?:--|—|-)\s+.+")

    # First pass: find the first parameter section and description
    for idx, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        if (
            any(line.startswith(ind) for ind in param_indicators)
            or line in param_indicators
            or plain_param_pattern.match(line)
        ):
            param_start_idx = idx
            break
        description.append(line)

    # Track the format being used to maintain consistency
    current_format = None  # "rst", "google", or "plain"
    in_section = False
    current_param = None
    current_desc = []
    in_returns = False

    # Second pass: process parameters and returns
    for line in lines[param_start_idx:]:
        line = line.strip()
        if not line:
            continue

        # Detect format if not yet determined
        if not current_format:
            if line.startswith(":param"):
                current_format = "rst"
            elif line in ["Args:", "Parameters:", "Arguments:"]:
                current_format = "google"
                in_section = True
                continue
            elif plain_param_pattern.match(line):
                current_format = "plain"

        # Handle return descriptions
        if any(
            line.startswith(ind)
            for ind in [":return", ":returns", "Returns:", "Return:"]
        ) or line.lower().startswith(("returns --", "return --")):
            if current_param and current_desc:
                arg_descriptions[current_param] = " ".join(current_desc)
            current_param = None
            current_desc = []
            in_returns = True

            return_match = re.match(
                r"(?::returns?|Returns?:|\w+\s*--)\s*(.+)?", line
            )
            if (
                return_match
                and return_match.group(1)
                and not return_description
            ):
                return_description = return_match.group(1)
            continue

        # Handle return continuation lines
        if in_returns and not return_description:
            return_description = line
            continue
        elif (
            in_returns
            and return_description
            and not any(line.startswith(ind) for ind in param_indicators)
        ):
            return_description += f" {line}"
            continue

        # Parse according to format
        if current_format == "rst":
            rst_match = re.match(r":param\s+(\w+)\s*:\s*(.+)", line)
            if rst_match:
                if current_param:
                    arg_descriptions[current_param] = " ".join(current_desc)
                current_param = rst_match.group(1)
                current_desc = [rst_match.group(2)]
                in_returns = False
            elif current_param and not line.startswith(":"):
                current_desc.append(line)

        elif current_format == "google" and in_section:
            if line in ["Returns:", "Return:"]:
                in_section = False
                continue
            google_match = re.match(
                r"\s*(\w+)(?:\s*\([^)]+\))?\s*:\s*(.+)", line
            )
            if google_match:
                if current_param:
                    arg_descriptions[current_param] = " ".join(current_desc)
                current_param = google_match.group(1)
                current_desc = [google_match.group(2)]
                in_returns = False
            elif current_param and not any(
                line.startswith(ind) for ind in param_indicators + ["Returns:"]
            ):
                current_desc.append(line)

        elif current_format == "plain":
            plain_match = re.match(r"\s*(\w+)\s*(?:--|—|-)\s*(.+)", line)
            if plain_match:
                if current_param:
                    arg_descriptions[current_param] = " ".join(current_desc)
                current_param = plain_match.group(1)
                current_desc = [plain_match.group(2)]
                in_returns = False

    # Don't forget to add the last parameter
    if current_param and current_desc:
        arg_descriptions[current_param] = " ".join(current_desc)

    # Clean up descriptions
    description = " ".join(description).strip()
    arg_descriptions = {k: v.strip() for k, v in arg_descriptions.items()}
    if return_description:
        return_description = return_description.strip()

    return description, arg_descriptions, return_description, name


def _get_full_type_str(type_hint: Any) -> str:
    """
    Get a string representation of a type hint, including generic parameters.
    """
    if isinstance(type_hint, _GenericAlias):
        return str(type_hint).replace("typing.", "")
    return getattr(type_hint, "__name__", str(type_hint))


def _generate_random_id(n: int = 6) -> str:
    """Generate a random n-character alphanumeric string (lowercase)."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))
