from abc import ABC, abstractmethod
from arkaine.llms.llm import LLM
from arkaine.tools.agent import Agent
from arkaine.tools.argument import Argument
from arkaine.utils.templater import PromptTemplate
from typing import List
from arkaine.tools.result import Result
from arkaine.tools.example import Example


class Generator(Agent):

    def __init__(
        self,
        name: str,
        description: str,
        args: List[Argument],
        llm: LLM,
        examples: List[Example],
        result: Result,
        id: str,
    ):
        super().__init__(
            name,
            description,
            args,
            llm,
            examples=examples,
            result=result,
            id=id,
        )

    @abstractmethod
    def generate(self, context: Context) -> str:
        pass
