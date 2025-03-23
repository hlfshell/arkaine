from typing import Optional
from arkaine.tools.tool import Tool
from arkaine.tools.result import Result
from arkaine.tools.context import Context
from arkaine.tools.argument import Argument


class ThinkTool(Tool):
    """
    ThinkTool is loosely based on an [Anthropic study of a simple no-op think
    tool](https://www.anthropic.com/engineering/claude-think-tool). This tool is
    the no-op(ish) version of the think tool, which just has the agent append a
    thought to its log. We save the thought to the context (`.x["thoughts"]`)
    for safe-keeping and further reference, but the tool does nothing else.
    Since most Backends maintain a log of what it is actively doing, the act of
    writing the thought to the input argument is actively getting the model to
    think.
    """

    def __init__(
        self,
        name: str = "think_tool",
        id: Optional[str] = None,
    ):
        super().__init__(
            name=name,
            description=(
                "Use the tool to think about something. It will not obtain "
                "new information and not return anything, but allows you to "
                "expand on your current thought process."
            ),
            arguments=[
                Argument(
                    name="thought",
                    description="A thought to think about",
                    required=True,
                )
            ],
            func=self.think,
            examples=[],
            Result=Result(
                type=str,
                description="A blank string",
            ),
            id=id,
        )

    def think(self, context: Context, thought: str) -> str:
        """
        Think about something.
        """
        context.x.init("thoughts", [])
        context.x.append("thoughts", thought)
        return ""
