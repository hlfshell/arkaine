from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from agents.agent_old import Prompt


class PromptTemplate:
    """
    PromptTemplate is a class designed to handle easy templating within
    prompts. It can successfully deal with the Prompt type (str or a List of
    dicts) and handle save/load appropriately.
    """

    def __init__(
        self, template: str, template_delimiters: Tuple[str, str] = ("{", "}")
    ):
        self.template = template
        self.template_delimiters = template_delimiters
        self.variables = self.__get_all_variables()

    @classmethod
    def from_file(self, path: str) -> PromptTemplate:
        with open(path) as f:
            return PromptTemplate(f.read())

    def __isolate_templated_variables(self, input: str) -> List[str]:
        """
        Given a string, identify all templated variables and return them as a
        list of strings. These are marked as any continuous variable within
        templating delimiters. This is an internal function for initialization
        purposes.
        """
        variables = []
        start = 0
        current = start
        while current < len(input):
            if input[current] == self.template_delimiters[0]:
                start = current
                while (
                    current < len(input)
                    and input[current] != self.template_delimiters[1]
                ):
                    current += 1
                variables.append(input[start + 1 : current])
            current += 1

        return variables

    def __get_all_variables(self) -> Dict[str, Optional[Any]]:
        """
        Run through the template, be it a string or a list of dicts. Identify
        all templating variables and return that as a dictionary. This is an
        internal function for initialization purposes.
        """
        if isinstance(self.template, str):
            return {
                var: None
                for var in self.__isolate_templated_variables(self.template)
            }
        else:
            variables: Dict[str, Optional[Any]] = {}
            for role, content in self.template:
                for var in self.__isolate_templated_variables(content):
                    variables[var] = None

            return variables

    def __setitem__(self, name: str, value: Any) -> None:
        """
        Set a variable in the template. Will raise an error if the variable is
        not found in the template.
        """
        if name not in self.variables:
            raise ValueError(f"Variable {name} not found in template.")
        self.variables[name] = value

    def __getitem__(self, name: str) -> Any:
        """
        Get a variable in the template. Will raise an error if the variable is
        not found in the template.
        """
        if name not in self.variables:
            raise ValueError(f"Variable {name} not found in template.")
        return self.variables[name]

    def render(self, variables: Optional[Dict[str, any]] = None) -> Prompt:
        """
        Render the template with the given prompt with the current variables in
        memory. If the variables argument is set, this is used instead.
        """
        if variables is None:
            variables = self.variables

        if isinstance(self.template, str):
            return self.template.format(**variables)
        else:
            return [
                {
                    "role": role,
                    "content": content.format(**variables),
                }
                for role, content in self.template
            ]

    @staticmethod
    def Load(path: str):
        """
        load a template from a given filepath. If JSON, load it as a list of
        dicts and convert to a pythonic object. If not, load it as a string.
        """
        if path.endswith(".json"):
            with open(path, "r") as f:
                template = json.load(f)
            return PromptTemplate(template)
        else:
            with open(path, "r") as f:
                template = f.read()
            return PromptTemplate(template)
