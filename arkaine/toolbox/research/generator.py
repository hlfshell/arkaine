from datetime import datetime
from typing import List

from arkaine.llms.llm import LLM, Prompt
from arkaine.toolbox.research.finding import Finding
from arkaine.tools.abstract import AbstractAgent
from arkaine.tools.argument import Argument
from arkaine.tools.context import Context
from arkaine.utils.templater import PromptLoader


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
                    "list[str]",
                ),
            ],
            llm=llm,
        )

    def prepare_prompt(
        self, context: Context, topic: str, findings: List[Finding]
    ) -> Prompt:
        report_template = PromptLoader.load_prompt("generate_report")
        base_prompt = PromptLoader.load_prompt("researcher")
        prompt = base_prompt.render(
            {
                "now": datetime.now().strftime("%Y-%m-%d"),
                "proficiency_level": "a highly experienced domain expert",
            }
        )
        prompt.extend(
            report_template.render(
                {
                    "topic": topic,
                    "findings": findings,
                    "proficiency": "a highly experienced domain expert",
                }
            )
        )
        return prompt

    def extract_result(self, context: Context, output: str) -> str:
        return output


class LessonGenerator(Generator):
    def __init__(self, llm: LLM):
        super().__init__(
            name="lesson_generator",
            description="Generate a lesson from a list of findings",
            args=[
                Argument(
                    "topic",
                    "The topic the research focused on",
                    "str",
                ),
                Argument(
                    "findings",
                    "Findings from which we generate the lesson from",
                    "list[str]",
                ),
            ],
            llm=llm,
        )
