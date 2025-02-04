from google.ai.generativelanguage import FunctionDeclaration

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


def openai(
    tool: Tool, include_examples: bool = False, include_return: bool = True
) -> str:
    """
    Generates a structured representation of a tool for OpenAI integration.

    This function takes a Tool object and constructs a dictionary that
    describes the tool's properties, including its name, description,
    parameters, and required arguments.

    Args:
        tool (Tool): The tool object containing metadata about the tool.

        include_examples (bool): Whether to include example usages in the
            output.

        include_return (bool): Whether to include return type information in
            the output.

    Returns:
        dict: A dictionary representation of the tool, suitable for OpenAI
            function calls.
    """
    properties = {}
    required_args = []

    description = tool.description
    if include_return and tool.result:
        description += f"\n\nReturns: {tool.result}"
    if include_examples and tool.examples:
        description += "\n\nExamples:\n"
        for example in tool.examples:
            description += f"    {example}\n"

    for arg in tool.args:
        arg_type = arg.type_str
        if arg_type == "str":
            arg_type = "string"

        properties[arg.name] = {
            "type": arg_type,
            "description": arg.description,
        }
        if arg.required:
            required_args.append(arg.name)

    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required_args,
            },
        },
    }


def gemini(tool: Tool) -> FunctionDeclaration:
    """Convert a tool into a Gemini FunctionDeclaration.

    Args:
        tool: tool obj to convert

    Returns:
        FunctionDeclaration object compatible with Gemini's function calling
    """
    # Create the parameters schema
    parameters = {"type_": "OBJECT", "properties": {}, "required": []}

    # Convert each argument into the Gemini format
    for arg in tool.args:
        type_map = {
            "str": "STRING",
            "string": "STRING",
            "number": "NUMBER",
            "float": "NUMBER",
            "integer": "NUMBER",
            "int": "NUMBER",
            "boolean": "BOOLEAN",
            "array": "ARRAY",
            "object": "OBJECT",
            "dict": "OBJECT",
            "list": "ARRAY",
            "tuple": "ARRAY",
            "set": "ARRAY",
            "tuple": "ARRAY",
            "datetime": "STRING",
            "date": "STRING",
            "time": "STRING",
            "timedelta": "STRING",
        }

        # Get the Gemini type, defaulting to STRING if unknown
        gemini_type = type_map.get(arg.type_str.lower(), "STRING")

        description = arg.description
        if arg.default:
            description += f"\nDefault: {arg.default}"

        # Add the property
        parameters["properties"][arg.name] = {
            "type_": gemini_type,
            "description": (arg.description),
        }

        # Add to required list if necessary
        if arg.required:
            parameters["required"].append(arg.name)

    return FunctionDeclaration(
        name=tool.name, description=tool.description, parameters=parameters
    )
