from arkaine.tools.tool import Tool


def python(
    tool: Tool,
    output_style: str = "standard",
    include_examples: bool = False,
    include_return: bool = True,
) -> str:
    """
    Generate a Python docstring for the given tool.

    Args:
        tool (Tool): The tool for which to generate the docstring.

        output_style (str): The style of output to request (e.g., "standard",
            "google", "numpy").

        include_examples (bool): Whether to include examples in the docstring.

        include_return (bool): Whether to include the return type in the
            docstring (if a Result is specified for the tool).

    Returns:
        str: The generated docstring.
    """
    # Build function signature with tool name and args
    func_sig = f"\ndef {tool.name}("
    if tool.args:
        func_sig += ", ".join(arg.name for arg in tool.args)
    func_sig += ")\n"

    docstring = func_sig + f'"""\n{tool.description}\n\n'

    # Add arguments based on the output style
    if tool.args:
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

    if tool.result and include_return:
        docstring += f"\n\nReturns: {tool.result}\n"

    if include_examples and tool.examples:
        docstring += "\nExamples:\n"
        for example in tool.examples:
            docstring += f"    {example}\n"

    docstring += '"""'
    return docstring
