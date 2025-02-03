from arkaine.tools.agent import Prompt
from arkaine.tools.types import ToolResults


def simple_tool_results_to_prompts(
    prompt: Prompt, results: ToolResults, role: str = "system"
):
    """
    Given the set of tool results, simply
    generate a string that says:

    ---
    tool_name(arg1="value1", arg2="value2") returned:
    <result>

    ...with appproiate formatting.
    """
    for name, args, result in results:
        out = f"---\n{name}("
        first_tool = True
        for arg, value in args.items():
            if first_tool:
                first_tool = False
            else:
                out += ", "
            out += f"{arg}="
            if isinstance(value, str):
                out += f'"{value}"'
            else:
                out += f"{value}"
        out += f") returned:\n{result}\n"
        prompt.append(
            {
                "role": role,
                "content": out,
            }
        )

    return prompt
