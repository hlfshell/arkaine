from __future__ import annotations

import inspect
import json
import pathlib
import re
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple, Union
from pathlib import Path


class PromptTemplate:
    """
    PromptTemplate is a class designed to handle easy templating within
    prompts. It can successfully deal with the Prompt type (str or a List of
    dicts) and handle save/load appropriately.
    """

    def __init__(
        self,
        template: str | Dict[str, str],
        template_delimiters: Tuple[str, str] = ("{", "}"),
        defaults: Optional[Dict[str, Any]] = None,
    ):
        self.template = template
        self.template_delimiters = template_delimiters
        self.variables = self.__get_all_variables()
        self.defaults = defaults or {}

    @classmethod
    def from_file(
        cls, path: Union[str, Path], defaults: Optional[Dict[str, Any]] = None
    ) -> PromptTemplate:
        """Load a template from a given filepath."""
        # Convert path to string if it is not already a string.
        path = str(path)
        if path.endswith(".json"):
            with open(path, "r") as f:
                template = json.load(f)
                # For JSON files, we want the content of the template
                if isinstance(template, dict):
                    template = next(iter(template.values()))
        else:
            with open(path, "r") as f:
                template = f.read()
        return cls(template, defaults=defaults)

    def __get_all_variables(self) -> Dict[str, Optional[Any]]:
        """
        Run through the template and identify all templating variables.
        """
        if isinstance(self.template, str):
            return {
                var: None
                for var in self.__isolate_templated_variables(self.template)
            }
        elif isinstance(self.template, dict):
            variables: Dict[str, Optional[Any]] = {}
            for content in self.template.values():
                if isinstance(content, str):
                    for var in self.__isolate_templated_variables(content):
                        variables[var] = None
            return variables
        else:
            raise ValueError(
                f"Template must be str or dict, not {type(self.template)}"
            )

    def __isolate_templated_variables(self, text: str) -> List[str]:
        """Find all template variables within text."""
        pattern = (
            rf"\{self.template_delimiters[0]}"
            rf"(\w+)"
            rf"\{self.template_delimiters[1]}"
        )
        return re.findall(pattern, text)

    def __setitem__(self, name: str, value: Any) -> None:
        if name not in self.variables:
            raise ValueError(f"Variable {name} not found in template.")
        self.variables[name] = value

    def __getitem__(self, name: str) -> Any:
        if name not in self.variables:
            raise ValueError(f"Variable {name} not found in template.")
        return self.variables[name]

    def render(
        self, variables: Optional[Dict[str, any]] = None, role: str = "system"
    ) -> List[Dict[str, str]]:
        """Render the template with the given variables."""
        if variables is None:
            variables = self.variables

        # Merge defaults with provided variables, prioritizing provided
        # variables
        merged_variables = self.defaults.copy()
        merged_variables.update(variables)

        template_text = (
            self.template
            if isinstance(self.template, str)
            else next(iter(self.template.values()))
        )

        delimiter_pattern = (
            re.escape(self.template_delimiters[0])
            + r"(.*?)"
            + re.escape(self.template_delimiters[1])
        )

        text = template_text
        for var, value in merged_variables.items():
            pattern = delimiter_pattern.replace("(.*?)", re.escape(var))
            sanitized_value = str(value).replace("\\", "\\\\")
            text = re.sub(pattern, sanitized_value, text)

        return [{"role": role, "content": text}]

    @classmethod
    def default(cls) -> PromptTemplate:
        """Create a default prompt template with agent_explanation and task
        variables."""
        template = "{agent_explanation}\n\n{task}"
        return cls(template)


class PromptLoader:
    """
    PromptLoader is a class designed to load prompts from a directory relative
    to the caller's file. It assumes that prompts:

    A) Are in the "prompts" directory
    B) Have the extension of ".prompt".

    PromptLoader is thread safe and will cache prompts in memory, preventing
    multiple loads, but also only loading prompts when needed.

    Note: This class is not meant to be instantiated.
    """

    _lock = Lock()
    _prompts: Dict[str, PromptTemplate] = {}

    def __new__(cls, *args, **kwargs):
        raise TypeError(
            "PromptLoader may not be instantiated. "
            "Please use its class methods directly."
        )

    @classmethod
    def load_prompt(cls, name: str) -> str:
        """
        Loads a report prompt from a file in the "prompts" directory relative
        to the caller's file and caches it.
        """
        # Get the caller's frame info
        caller_frame = inspect.stack()[1]
        caller_filepath = caller_frame.filename
        caller_directory = pathlib.Path(caller_filepath).parent

        # Construct the file path relative to the caller's file
        filepath = caller_directory / "prompts" / f"{name}.prompt"

        with cls._lock:
            if filepath not in cls._prompts:
                cls._prompts[filepath] = PromptTemplate.from_file(filepath)
            return cls._prompts[filepath]
