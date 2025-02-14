import os
import pathlib
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List
from uuid import uuid4

from arkaine.llms.llm import LLM
from arkaine.toolbox.research.web_research import Finding
from arkaine.tools.abstract import AbstractAgent
from arkaine.tools.argument import Argument
from arkaine.tools.example import Example
from arkaine.tools.result import Result
from arkaine.utils.templater import PromptLoader, PromptTemplate


class Generator(AbstractAgent):
    # Define the argument rules as class variable
    _argument_rules = {
        "required_args": [Argument("findings", "", "list[Finding]")],
        "allowed_args": [Argument("topic", "", "str")],
    }


class ReportGenerator(Generator):
    def __init__(self, llm: LLM):
        super().__init__(
            name="report_generator",
            description="Generate a detailed report from a list of findings",
            args=[
                Argument(
                    "topic",
                    "The topic to research",
                    "str",
                ),
                Argument(
                    "findings",
                    "Findings from which we generate the report from",
                    "list[Finding]",
                ),
            ],
            llm=llm,
            examples=[],
            result=Result(
                description="A detailed report generated from the findings",
                type="str",
            ),
            id=str(uuid4()),
        )

        self.__report_template = PromptLoader.load_prompt("generate_report")
        self.__base_prompt = PromptLoader.load_prompt("researcher")

    def prepare_prompt(
        self, context: str, topic: str, findings: List[Finding]
    ) -> List[str]:
        prompt = self.__base_prompt.render(
            {
                "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        prompt.extend(
            self.__report_template.render(
                {
                    "topic": topic,
                    "findings": findings,
                    "proficiency": "a highly experienced domain expert",
                }
            )
        )
        return prompt

    def extract_result(self, context: str, output: str) -> str:
        return output
