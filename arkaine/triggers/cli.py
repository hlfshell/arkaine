import json
import sys
from typing import List, Optional, Union

import click

from arkaine.tools.tool import Argument, Context, Tool


class CLI(click.Group):
    """
    A Click-based CLI application for arkaine tools.

    This class extends click.Group to create a CLI that exposes arkaine Tools
    as commands, preserving all tool metadata like descriptions, arguments,
    and examples.
    """

    def __init__(
        self,
        tools: Union[Tool, List[Tool]],
        name: Optional[str] = None,
        help_text: Optional[str] = None,
    ):
        """
        Initialize the CLI.

        Args:
            tools: Tool or list of tools to create CLI commands for
            name: Name for the CLI group (defaults to first tool's name)
            help_text: Help text for the CLI group
        """
        self.tools = [tools] if isinstance(tools, Tool) else tools
        name = name or self.tools[0].name
        help_text = help_text or "CLI generated from arkAIne tools"

        super().__init__(name=name, help=help_text)

        self._type_map = {
            "str": click.STRING,
            "int": click.INT,
            "float": click.FLOAT,
            "bool": click.BOOL,
        }

        self._add_tool_commands()

    def _convert_type(self, type_str: str) -> click.ParamType:
        """Convert arkaine type strings to click types."""
        # Handle Optional types
        if type_str.startswith("Optional["):
            inner_type = type_str[9:-1]
            return self._convert_type(inner_type)

        # Handle List types
        if type_str.startswith("List["):
            return click.STRING

        return self._type_map.get(type_str.lower(), click.STRING)

    def _create_option(self, arg: Argument) -> List[click.Option]:
        """Convert an arkaine Argument to click Options."""
        options = []

        # Standard value option
        param_decls = [f"--{arg.name}"]
        kwargs = {
            "help": f"{arg.description}. Can be a value or @filename to read from file",
            "required": False,  # We'll handle required validation ourselves
            "type": self._convert_type(arg.type),
        }

        if arg.default is not None:
            kwargs["default"] = arg.default
            kwargs["show_default"] = True
        options.append(click.Option(param_decls, **kwargs))

        # File input option
        file_kwargs = {
            "help": f"Read {arg.name} from file",
            "type": click.Path(exists=True, dir_okay=False),
            "required": False,
        }
        options.append(click.Option([f"--{arg.name}-file"], **file_kwargs))

        return options

    def _create_command(self, tool: Tool) -> click.Command:
        """Create a click Command from an arkaine Tool."""
        params = []

        # Add input/output options
        params.extend(
            [
                click.Option(
                    ["--json-input"],
                    help="JSON string or @filename containing all arguments",
                    type=str,
                    required=False,
                ),
                click.Option(
                    ["--output-file"],
                    help="Write output to file instead of stdout",
                    type=click.Path(dir_okay=False, writable=True),
                    required=False,
                ),
                click.Option(
                    ["--output-append"],
                    help="Append to output file instead of overwriting",
                    is_flag=True,
                    default=False,
                ),
            ]
        )

        # Add tool-specific options
        for arg in tool.args:
            params.extend(self._create_option(arg))

        @click.pass_context
        def command_func(ctx: click.Context, **kwargs):
            """Execute the tool with provided arguments."""
            # Check if we should show help
            has_required_args = any(arg.required for arg in tool.args)
            args_provided = any(
                kwargs.get(arg.name) is not None
                or kwargs.get(f"{arg.name}_file") is not None
                for arg in tool.args
            )

            if (
                has_required_args
                and not args_provided
                and not sys.stdin.isatty()
            ):
                # Don't show help if we have piped input
                pass
            elif has_required_args and not args_provided:
                ctx.obj = {"show_help": True}
                click.echo(ctx.get_help())
                ctx.exit()

            # Handle piped input
            if not sys.stdin.isatty():
                piped_input = sys.stdin.read().strip()
                try:
                    # Try parsing as JSON first
                    args_dict = json.loads(piped_input)
                except json.JSONDecodeError:
                    # If not JSON, use as raw input for first required arg
                    for arg in tool.args:
                        if arg.required and kwargs.get(arg.name) is None:
                            kwargs[arg.name] = piped_input
                            break

            # Handle JSON input
            json_input = kwargs.pop("json_input", None)
            if json_input:
                if json_input.startswith("@"):
                    with open(json_input[1:]) as f:
                        args_dict = json.load(f)
                else:
                    args_dict = json.loads(json_input)
                kwargs.update(args_dict)

            # Handle file inputs for individual arguments
            args_dict = {}
            for arg in tool.args:
                value = kwargs.get(arg.name)
                file_value = kwargs.get(f"{arg.name}_file")

                if file_value:
                    with open(file_value) as f:
                        args_dict[arg.name] = f.read().strip()
                elif value and isinstance(value, str) and value.startswith("@"):
                    with open(value[1:]) as f:
                        args_dict[arg.name] = f.read().strip()
                elif value is not None:
                    args_dict[arg.name] = value
                elif arg.required:
                    raise click.UsageError(
                        f"Required argument '{arg.name}' not provided"
                    )

            # Execute tool
            context = Context(tool)
            result = tool(context=context, **args_dict)

            # Handle output
            output_file = kwargs.get("output_file")
            if output_file:
                mode = "a" if kwargs.get("output_append") else "w"
                with open(output_file, mode) as f:
                    print(result, file=f)
            else:
                click.echo(result)

        help_text = self._generate_help_text(tool)

        return click.Command(
            name=tool.name,
            help=help_text,
            callback=command_func,
            params=params,
        )

    def _generate_help_text(self, tool: Tool) -> str:
        """Generate formatted help text including examples."""
        help_text = (
            f"{tool.description}\n\n"
            "Input Methods:\n"
            "  - Standard arguments (--arg value)\n"
            "  - File input for any argument (--arg @filename or --arg-file filename)\n"
            '  - JSON input (--json-input \'{"arg": "value"}\' or --json-input @file.json)\n'
            "  - Pipe input (echo 'value' | command, or echo '{\"arg\":\"value\"}' | command)\n"
            "\nOutput Methods:\n"
            "  - Standard output (default)\n"
            "  - File output (--output-file filename)\n"
            "  - Append mode (--output-append --output-file filename)"
        )

        if tool.examples:
            help_text += "\n\nExamples:\n"
            for example in tool.examples:
                help_text += f"\n  {example.name}:\n"
                if example.description:
                    help_text += f"    {example.description}\n"
                args_str = " ".join(
                    f"--{k} {v}" for k, v in example.args.items()
                )
                help_text += f"    $ {tool.name} {args_str}\n"
                if example.output:
                    help_text += f"    Output: {example.output}\n"

        return help_text

    def _add_tool_commands(self) -> None:
        """Add all tool commands to the CLI."""
        if len(self.tools) == 1:
            tool_command = self._create_command(self.tools[0])
            self.add_command(tool_command)
            return

        # For multiple tools, create subcommands and set no_args_is_help
        for tool in self.tools:
            command = self._create_command(tool)
            command.no_args_is_help = True  # Show help when no args provided
            self.add_command(command)

        # Also show help for the main group when no command is specified
        self.no_args_is_help = True
