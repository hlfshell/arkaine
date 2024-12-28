from __future__ import annotations

from typing import Dict, Optional


class Example:
    def __init__(
        self,
        name: str,
        args: Dict[str, str],
        output: Optional[str] = None,
        description: Optional[str] = None,
        explanation: Optional[str] = None,
    ):
        self.name = name
        self.args = args
        self.output = output
        self.description = description
        self.explanation = explanation

    @classmethod
    def ExampleBlock(cls, function_name: str, example: Example) -> str:
        out = ""
        if example.description:
            out += f"{example.description}\n"
        out += f"{function_name}("

        args_str = ", ".join(
            [f"{arg}={value}" for arg, value in example.args.items()]
        )
        out += f"{args_str})"

        if example.output:
            out += f"\nReturns:\n{example.output}"

        if example.explanation:
            out += f"\nExplanation: {example.explanation}"

        return out

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "args": self.args,
            "output": self.output,
        }
