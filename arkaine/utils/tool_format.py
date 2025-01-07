from arkaine.tools.tool import Tool


def python(
    tool: Tool, output_style: str = "standard", include_examples: bool = False
) -> str:
    """
    Generate a Python docstring for the given tool.

    Args:
        tool (Tool): The tool for which to generate the docstring.

        output_style (str): The style of output to request (e.g., "standard",
            "google", "numpy").

        include_examples (bool): Whether to include examples in the docstring.

    Returns:
        str: The generated docstring.
    """
    docstring = f'"""{tool.description}\n\n'

    # Add arguments based on the output style
    if output_style == "google":
        docstring += "Args:\n"
        for arg in tool.args:
            desc = arg.description if hasattr(arg, "description") else ""
            arg_desc = f"    {arg.name} ({arg.type}): {desc}\n"
            docstring += arg_desc
    elif output_style == "numpy":
        docstring += "Parameters\n----------\n"
        for arg in tool.args:
            desc = arg.description if hasattr(arg, "description") else ""
            arg_desc = f"{arg.name} : {arg.type}\n    {desc}\n"
            docstring += arg_desc
    elif output_style == "standard":
        docstring += "Args:\n"
        for arg in tool.args:
            desc = arg.description if hasattr(arg, "description") else ""
            arg_desc = f"    {arg.name} ({arg.type}): {desc}\n"
            docstring += arg_desc
    else:
        raise ValueError(f"Invalid output style: {output_style}")

    if tool.result:
        docstring += f"\n{tool.result}\n"

    if include_examples and tool.examples:
        docstring += "\nExamples:\n"
        for example in tool.examples:
            docstring += f"    {example}\n"

    docstring += '"""'
    return docstring
