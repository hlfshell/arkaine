import os
from pathlib import Path
from typing import Dict, List, Optional, Union

from arkaine.llms.llm import LLM, Prompt
from arkaine.tools.agent import Agent
from arkaine.tools.argument import Argument
from arkaine.tools.context import Context
from arkaine.tools.example import Example
from arkaine.tools.result import Result
from arkaine.utils.parser import Label as ParserLabel
from arkaine.utils.parser import Parser
from arkaine.utils.templater import PromptTemplate


class Label:
    def __init__(self, name: str, explanation: str):
        self.name = name
        self.explanation = explanation


class LabelExample:
    """
    Represents an example for a specific label.
    """

    def __init__(self, sample: str, label: Union[str, Label], reason: str):
        if isinstance(label, Label):
            label = label.name
        self.sample = sample
        self.label = label
        self.reason = reason

    def to_json(self) -> Dict[str, str]:
        return {
            "sample": self.sample,
            "label": self.label,
            "reason": self.reason,
        }

    def __str__(self):
        out = f"Sample:\n{self.sample}\n"
        out += f"Reason: {self.reason}"
        out += f"Label: {self.label}\n"
        return out


class Labeler(Agent):
    """
    An agent that assigns labels to input text based on predefined labels and
    examples.
    """

    def __init__(
        self,
        llm: LLM,
        labels: List[Label],
        examples: List[LabelExample],
        name: str = "labeler",
        allow_none: bool = True,
        id: Optional[str] = None,
    ):
        args = [
            Argument(
                name="input",
                description="The text to be labeled.",
                type="str",
                required=True,
            )
        ]

        # Convert LabelExamples to format compatible with the Example class
        formatted_examples = [
            Example(
                name="label_example",
                args={"input": ex.sample},
                output={"label": ex.label, "reason": ex.reason},
                description=f"Example of label '{ex.label}': {ex.reason}",
            )
            for ex in examples
        ]

        description = (
            f"Assigns one of the following labels to the input text: "
            f"{', '.join(str(label) for label in labels)}"
        )
        for example in formatted_examples:
            description += f"\n\n{example.description}"

        result = Result(
            type="dict",
            description=(
                "The assigned label for the input text and the model's "
                "reasoning for the label, following the format:\n",
                "{'label': <label>, 'reason': <reason>}",
            ),
        )

        super().__init__(
            name=name,
            description=description,
            args=args,
            llm=llm,
            examples=formatted_examples,
            result=result,
            id=id,
        )

        self.__labels = labels
        self.__label_examples = examples
        self.__allow_none = allow_none

        self.__prompt = PromptTemplate.from_file(
            os.path.join(
                Path(__file__).parent,
                "prompts",
                "label.prompt",
            )
        )

        self.__parser = Parser([ParserLabel("Reason"), ParserLabel("Label")])

    def prepare_prompt(self, context: Context, input: str) -> Prompt:
        """
        Prepares the prompt for the LLM to assign a label based on examples.
        """
        examples = "### **Examples:**\n"
        for index, example in enumerate(self.__label_examples):
            examples += f"#### **Example {index + 1}**\n"
            examples += f"**Input:**\n{example.sample}\n"
            examples += "**Output:**\n```plaintext\n"
            examples += f"Reason: {example.reason}\n"
            examples += f"Label: {example.label}\n"
            examples += "```\n"

        labels = "\n".join(
            [
                f"\t- **{label.name}** - {label.explanation}"
                for label in self.__labels
            ]
        )

        prompt = self.__prompt.render(
            {
                "input": input,
                "examples": examples,
                "labels": labels,
                "none_label": (
                    (
                        '- If the text does not match any label, state "None" '
                        "as the label"
                        if self.__allow_none
                        else ""
                    ),
                ),
            }
        )

        return prompt

    def extract_result(self, context: Context, response: str) -> Dict[str, str]:
        """
        Processes the LLM response to extract the label.
        """
        output, errors = self.__parser.parse(response)

        if errors:
            raise ValueError(f"Errors: {errors}")

        if self.__allow_none:
            if len(output["label"]) == 0:
                return {"label": "None", "reason": ""}
        else:
            raise ValueError("No label assigned")

        return {
            "label": output["label"],
            "reason": output["reason"],
        }
