from os.path import join
from pathlib import Path
from threading import Thread
from typing import Any, Dict, List, Optional, Tuple

from arkaine.toolbox.code_envs.python import PythonEnv
from arkaine.tools.tool import Context, Tool
from arkaine.utils.docker import BindVolume


class PythonREPL(PythonEnv):
    """
    PythonREPL represents a persistent Python REPL environment running in a
    Docker container. It extends PythonEnv to provide interactive execution
    capabilities.

    Attributes:
        name (str): A unique identifier for the REPL container.

        version (str): The version of Python to use. Default is "3.12".

        modules (Optional[Union[Dict[str, Union[str, Tuple[str, str]]],
            List[str]]]): Python modules to install in the environment.

        tools (List[Tool]): Tools available within the REPL environment.

        volumes (List[Union[BindVolume, Volume]]): Volumes to mount in
        container.

        ports (List[str]): Port mappings between container and host.

        env (Dict[str, Any]): Environment variables for the container.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        version: Optional[str] = "3.12",
        modules: Optional[Dict[str, Any]] = None,
        tools: List[Tool] = [],
        volumes: List[BindVolume] = [],
        ports: List[str] = [],
        env: Dict[str, Any] = {},
        image: Optional[str] = None,
        container_code_directory: str = "/arkaine",
        socket_file: str = "arkaine_bridge.sock",
        local_code_directory: str = None,
    ):
        super().__init__(
            name=name,
            version=version,
            image=image,
            modules=modules,
            tools=tools,
            volumes=volumes,
            ports=ports,
            env=env,
            container_code_directory=container_code_directory,
            socket_file=socket_file,
            local_code_directory=local_code_directory,
        )

        self.__install_repl()

    def __install_repl(self):
        with open(
            join(Path(__file__).parent, "extras", "python_env", "_repl.py"), "r"
        ) as f:
            self.__repl_code = f.read()

        __repl_code = self.__repl_code.replace(
            "{tool_names}", "\n".join([tool.tname for tool in self.__tools])
        ).replace("{client_import}", self.__client_import_filename)

        with open(join(self.__local_code_directory, "_repl.py"), "w") as f:
            f.write(__repl_code)

    def execute(
        self, context: Context, code: str
    ) -> Tuple[Any, Exception, str, str]:
        """
        Execute code in the REPL environment.

        Args:
            code (str): The Python code to execute.

        Returns:
            Tuple containing:
            - Any: The output of the executed code
            - Exception: Any exception that occurred during execution
            - str: stdout from the execution
            - str: stderr from the execution
        """
        if context is None:
            context = Context()

        if context.executing:
            context = context.child_context(None)

        context.executing = True

        with context:
            self._add_bridge_imports()
            self._install_modules()
            self.__install_repl()
            server = self._run_socket_server(context)

            # Create the repl client
            with self._container:
                

    def stop(self):
        """Stop the REPL environment and clean up resources."""
        if self.__initialized:
            self._PythonEnv__halt = True
            super().stop()
            self.__initialized = False

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()
