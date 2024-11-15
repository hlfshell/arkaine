from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple


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
    ):
        self.template = template
        self.template_delimiters = template_delimiters
        self.variables = self.__get_all_variables()

    @classmethod
    def from_file(self, path: str) -> PromptTemplate:
        """Load a template from a given filepath."""
        if path.endswith(".json"):
            with open(path, "r") as f:
                template = json.load(f)
                # For JSON files, we want the content of the template
                if isinstance(template, dict):
                    template = next(iter(template.values()))
        else:
            with open(path, "r") as f:
                template = f.read()
        return PromptTemplate(template)

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
        for var, value in variables.items():
            pattern = delimiter_pattern.replace("(.*?)", re.escape(var))
            text = re.sub(pattern, str(value), text)

        return [{"role": role, "content": text}]
