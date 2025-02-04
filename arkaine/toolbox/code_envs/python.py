from __future__ import annotations

import os
import pickle
import re
import shutil
import socket
import struct
import tempfile
import time
import traceback
from os.path import join
from pathlib import Path
from threading import Thread
from typing import IO, Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

from arkaine.tools.context import Context
from arkaine.tools.tool import Tool
from arkaine.utils.docker import BindVolume, Container, Volume


class PythonEnv(Container):
    """
    PythonEnv represents a Docker container specifically configured to run
    Python environments. It encapsulates the properties and behaviors
    associated with a Python execution environment within a Docker container.

    Attributes:
        name (str): A unique identifier for the Python environment container.

        version (str): The version of Python to use in the environment. Default
            is "3.12".

        modules (Optional[Union[Dict[str, Union[str, Tuple[str, str]]],
        List[str]]]):
            A list or dictionary of Python modules to install in the
            environment. See documentation below for more details.

        image (Optional[str]): The Docker image to use for the Python
            environment.

        tools (List[Tool]): A list of tools that can be used within the Python
            environment.

        volumes (List[Union[BindVolume, Volume]]): A list of volumes to mount
            in the container.

        ports (List[str]): A list of port mappings between the container and
            the host.

        entrypoint (str): The command to run when the container starts.

        command (Optional[str]): The command to execute in the container.

        env (Dict[str, Any]): Environment variables to set in the container.

        container_code_directory (str): The directory inside the container
            where code will be executed. Default is "/arkaine".

        socket_file (str): The name of the socket file for communication.
            Default is "arkaine_bridge.sock".

        local_code_directory (Optional[str]): The local directory on the host
            to mount in the container.

        id (Optional[str]): The ID of the Python environment. If not provided,
            a new UUID will be generated.

    Methods:
        execute(code: (see below) -> Tuple[Any, Exception]:
            Code can be a string, file-like object, dictionary, or path. Each
            have their own meaning.
             - string : the code to execute
             - file-like / IO object : the code to execute
             - dict : a dict of files to write to the container.
                The keys are the filenames, and the values are the file
                contents. If a value of a key is another dict, it will be
                treated as a directory, and so on recursively until all files
                are written.
             - path : a path to a directory or file. If it's a file, it will
                be copied to the container. If it's a directory, all the files
                in the directory will be copied to the container.

            Executes the provided code in the Python environment, managing the
            execution context and handling exceptions.

    On module installation:
        When utilizing the modules argument, you can specify it in two ways.
        The overall functionality of this feature is to install the modules
        specified at initial running of the container. Do note, however, that
        it is more ideal to utilize an image with the correct modules already
        installed.

        If passed a list, it will be treated as a list of modules to install
        using pip.

        If passed a dict, the key is the package manager to use, and the value
        is a list of modules to install. The following package managers are
        supported, but not necessarily in the image used:
            - pip
            - conda
            - poetry
            - uv
            - mamba
    """

    def __init__(
        self,
        name: Optional[str] = None,
        version: str = "3.12",
        modules: Optional[
            Union[Dict[str, Union[str, Tuple[str, str]]], List[str]]
        ] = None,
        image: Optional[str] = None,
        tools: List[Tool] = [],
        volumes: List[Union[BindVolume, Volume]] = [],
        ports: List[str] = [],
        entrypoint: str = None,
        command: Optional[str] = None,
        env: Dict[str, Any] = {},
        container_code_directory: str = "/arkaine",
        socket_file: str = "arkaine_bridge.sock",
        local_code_directory: str = None,
        id: Optional[str] = None,
    ):
        if id is None:
            self.__id = str(uuid4())
        else:
            self.__id = id

        self.__type = "python_env"

        if name is None:
            name = f"arkaine-python-{self.__id}"
        if image is None:
            image = f"python:{version}"

        self.__tools = {tool.tname: tool for tool in tools}

        if local_code_directory is None:
            self.__local_directory = tempfile.mkdtemp()
        else:
            self.__local_directory = local_code_directory

        self.__container_directory = container_code_directory
        self.__socket_file = socket_file
        self.__tmp_bind = BindVolume(
            self.__local_directory, self.__container_directory
        )
        self.__socket_path = join(self.__local_directory, self.__socket_file)

        volumes.append(self.__tmp_bind)

        super().__init__(
            name,
            image,
            args={},
            env=env,
            volumes=volumes,
            ports=ports,
            entrypoint=entrypoint,
            command=command,
        )

        self.__name = f"arkaine-python-{self.__id}::{name}::{image}"

        self.__modules = modules

        self.__client_import_filename = "arkaine_bridge.py"

        self.__halt = False

        self.__load_bridge_functions(tools)

    @property
    def id(self):
        return self.__id

    @property
    def type(self):
        return self.__type

    @property
    def name(self):
        return self.__name

    def __install_modules(self):
        """
        Installs the specified Python modules in the environment using the
        appropriate package manager.

        This method constructs installation commands based on the provided
        modules and executes them in the container. It supports multiple
        package managers such as pip, conda, poetry, uv, and mamba. If any
        installation fails, a PythonModuleInstallationException is raised.
        """
        commands: List[str] = []

        def versioned_str(installer: str, input: Tuple[str, str]) -> str:
            if installer in ["pip", "poetry"]:
                return f"{input[0]}=={input[1]}"  # pip and poetry use '=='
            elif installer in ["conda", "uv", "mamba"]:
                return f"{input[0]}={input[1]}"  # conda, uv, and mamba use '='
            else:
                raise ValueError(f"Installer '{installer}' is not supported.")

        acceptable_installers = ["pip", "conda", "poetry", "uv", "mamba"]

        if isinstance(self.__modules, List):
            commands = [
                "pip install "
                + " ".join(
                    (
                        versioned_str("pip", module)
                        if isinstance(module, Tuple)
                        else module
                    )
                    for module in self.__modules
                )
            ]
        elif isinstance(self.__modules, Dict):
            commands = []
            non_pip_installers_used: List[str] = []
            for installer, installer_modules in self.__modules.items():
                if installer not in acceptable_installers:
                    raise ValueError(
                        f"Installer '{installer}' is not supported."
                    )
                if installer == "pip":
                    commands.append(
                        "pip install "
                        + " ".join(
                            (
                                versioned_str(installer, module)
                                if isinstance(module, Tuple)
                                else module
                            )
                            for module in installer_modules
                        )
                    )
                elif installer == "conda":
                    commands.append(
                        "conda install -y "
                        + " ".join(
                            (
                                versioned_str(installer, module)
                                if isinstance(module, Tuple)
                                else module
                            )
                            for module in installer_modules
                        )
                    )
                    non_pip_installers_used.append(installer)
                elif installer == "poetry":
                    commands.append(
                        "poetry add "
                        + " ".join(
                            (
                                versioned_str(installer, module)
                                if isinstance(module, Tuple)
                                else module
                            )
                            for module in installer_modules
                        )
                    )
                    non_pip_installers_used.append(installer)

                elif installer in ["uv", "mamba"]:
                    commands.append(
                        f"{installer} install -y "
                        + " ".join(
                            (
                                versioned_str(installer, module)
                                if isinstance(module, Tuple)
                                else module
                            )
                            for module in installer_modules
                        )
                    )
                    non_pip_installers_used.append(installer)

        for command in commands:
            try:
                self.bash(command)
            except Exception as e:
                raise PythonModuleInstallationException(e)

    def __handle_client(self, client: socket, context: Context) -> Any:
        """
        Handles communication with a client connected to the Python
        environment's socket.

        This method receives data from the client, processes requests, and
        sends back responses. It supports handling various function calls,
        including ping requests, results, and exceptions.

        Args:
            client (socket): The socket connection to the client.

            context (Context): The context associated with the current
                execution.
        """
        try:
            # Get size first
            size = struct.unpack("!Q", client.recv(8))[0]
            chunks = []
            bytes_received = 0
            while bytes_received < size:
                chunk = client.recv(min(size - bytes_received, 4096))
                if not chunk:
                    return
                chunks.append(chunk)
                bytes_received += len(chunk)

            data = pickle.loads(b"".join(chunks))

            # Handle ping requests
            if data["function"] == "_ping":
                response = pickle.dumps("pong")
                client.sendall(struct.pack("!Q", len(response)))
                client.sendall(response)
                return

            if data["function"] == "_result":
                context.output = data["args"][0]
                response = pickle.dumps(None)
                client.sendall(struct.pack("!Q", len(response)))
                client.sendall(response)
                return

            if data["function"] == "_exception":
                exception, traceback = data["args"]

                context.exception = PythonExecutionException(
                    exception, traceback
                )
                response = pickle.dumps(None)
                client.sendall(struct.pack("!Q", len(response)))
                client.sendall(response)
                return

            try:
                tool = self.__tools[data["function"]]
                result = tool(context, *data["args"], **data["kwargs"])
            except Exception as e:
                result = e

            response = pickle.dumps(result)
            client.sendall(struct.pack("!Q", len(response)))
            client.sendall(response)
        finally:
            client.close()

    def __run_socket_server(self, context: Context):
        """
        Starts a socket server to listen for incoming client connections and
        handle requests.

        This method creates a Unix socket server that listens for client
        connections. It spawns a new thread to handle each client connection,
        allowing multiple clients to be served concurrently.

        Args:
            context (Context): The context associated with the current
                execution.
        """
        if os.path.exists(self.__socket_path):
            os.unlink(self.__socket_path)

        self.__halt = False

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(self.__socket_path)
        server.listen(5)

        # Start a separate thread for ping handling
        def ping_until_response():
            bridge_ready = False
            while not bridge_ready:
                try:
                    ping_socket = socket.socket(
                        socket.AF_UNIX, socket.SOCK_STREAM
                    )
                    ping_socket.connect(self.__socket_path)

                    # Send ping request
                    ping_data = pickle.dumps(
                        {"function": "_ping", "args": (), "kwargs": {}}
                    )
                    ping_socket.sendall(struct.pack("!Q", len(ping_data)))
                    ping_socket.sendall(ping_data)

                    # Get response
                    size = struct.unpack("!Q", ping_socket.recv(8))[0]
                    response = pickle.loads(ping_socket.recv(size))

                    if response == "pong":
                        bridge_ready = True

                finally:
                    ping_socket.close()

                if not bridge_ready:
                    time.sleep(0.1)  # Wait briefly before next attempt

        ping_thread = Thread(target=ping_until_response, daemon=True)
        ping_thread.start()

        """
        How this works™:

        Basically it opens the socket and checks for a connection. Once made
        (via a message being sent), we create a thread to handle the client
        message coming in. This allows possibly multiple incoming messages to
        be processed in parallel. Then we start listening yet again. Of course,
        we also have a __halt check; if we call stop or go to delete the
        process we stop this and die off.
        """
        client, _ = server.accept()
        while True:
            try:
                if self.__halt:
                    break
                Thread(
                    target=self.__handle_client,
                    args=(client, context),
                    daemon=True,
                ).start()
                client, _ = server.accept()
            except:  # noqa: E722
                break

    def __load_bridge_functions(self, tools: List[Tool]):
        """
        Loads bridge functions from external files and prepares them for use in
        the Python environment.

        This method reads bridge function definitions from specified files,
        replaces placeholders with actual values, and appends tool-specific
        function calls to the bridge code.

        Args:
            tools (List[Tool]): A list of tools whose functions will be
                included in the bridge.
        """
        bridge_functions_path = join(
            Path(__file__).parent,
            "extras",
            "python_env",
            "_bridge_functions.py",
        )

        tool_call_path = join(
            Path(__file__).parent,
            "extras",
            "python_env",
            "_tool_call.py",
        )

        with open(bridge_functions_path, "r") as f:
            bridge_code = f.read()

        # Replace {code_directory} and {socket_file} with the actual values
        bridge_code = bridge_code.replace(
            "{code_directory}", self.__container_directory
        ).replace("{socket_file}", self.__socket_file)

        with open(
            f"{self.__local_directory}/{self.__client_import_filename}", "w"
        ) as f:
            # We need to append each tool to the bridge functions.
            with open(tool_call_path, "r") as template:
                tool_call_template = template.read()

            for tool in tools:
                bridge_code += "\n\n" + tool_call_template.replace(
                    "{tool_name}", tool.tname
                )

            f.write(bridge_code)

    def __add_bridge_imports(self):
        """
        Appends import statements for bridge functions to Python files in the
        local code directory.

        This method scans the local code directory for Python files and adds
        import statements for the bridge functions, ensuring that they are
        available for execution.
        """
        ignore_files = [
            "setup.py",
            self.__client_import_filename,
            "_execute.py",
        ]

        # For each code file in the tmp filesystem that's .py, save
        # the bridge function itself, append an import line to the
        # file.
        for file in Path(self.__local_directory).rglob("*.py"):
            if file.is_file() and not any(
                part.startswith(".") for part in file.parts
            ):
                if file.name not in ignore_files:
                    with open(file, "r") as f:
                        content = f.read()
                        # Find first non-__ import or first non-import line
                        lines = content.splitlines()
                        insert_idx = 0
                        for i, line in enumerate(lines):
                            if line.strip().startswith(
                                "import"
                            ) or line.strip().startswith("from"):
                                if not line.strip().split()[1].startswith("__"):
                                    insert_idx = i
                                    break
                            elif line.strip() and not line.startswith("#"):
                                insert_idx = i
                                break

                        lines.insert(
                            insert_idx,
                            "from arkaine_bridge import *",
                        )

                        new_content = "\n".join(lines)

                    with open(file, "w") as f:
                        f.write(new_content)

    def __dict_to_files(
        self, code: Dict[str, Union[str, Dict]], parent_dir: str
    ):
        """
        Recursively writes a dictionary of code files to the local code
        directory.

        This method creates directories as needed and writes the contents of
        the provided dictionary to the specified location in the local code
        directory.

        Args:
            code (Dict[str, Union[str, Dict]]): A dictionary where keys are
                filenames and values are file contents.

            parent_dir (str): The parent directory in which to write the files.
        """
        for filename, content in code.items():
            if isinstance(content, Dict):
                # If it's a dict, we make it a directory, and then recurse
                # so that we can go as deep as we need.
                os.makedirs(
                    f"{self.__local_directory}/{parent_dir}", exist_ok=True
                )
                self.__dict_to_files(content, f"{parent_dir}/{filename}")
            else:
                # ...otherwise it's a file; write it
                with open(f"{self.__local_directory}/{filename}", "w") as f:
                    f.write(content)

    def __copy_code_to_tmp(
        self,
        code: Union[str, IO, Dict[str, str], Path],
        target_file: str = "main.py",
    ):
        """
        Copies code from various sources to the temporary local code directory
        for execution.

        This method handles different types of input (string, file-like object,
        dictionary, or path) and writes the code to the specified target file
        in the local code directory.

        Args:
            code (Union[str, IO, Dict[str, str], Path]): The code to copy,
                which can be a string, file-like object, dictionary, or path.

            target_file (str): The name of the target file to write the code
                to.
        """
        if isinstance(code, IO):
            with open(f"{self.__local_directory}/{target_file}", "w") as f:
                f.write(code.read())
        elif isinstance(code, str):
            with open(f"{self.__local_directory}/{target_file}", "w") as f:
                f.write(code)
        elif isinstance(code, Dict):
            if target_file not in code:
                raise ValueError(
                    f"Target file {target_file} not found in code files; "
                    "unsure what to execute"
                )
            self.__dict_to_files(code, self.__local_directory)
        elif isinstance(code, Path):
            # IF it's a single file Path, copy it to the tmp_folder
            if code.is_file():
                with open(f"{self.__local_directory}/{target_file}", "w") as f:
                    f.write(code.read_text())
            # If it's a dir, copy all the files to the tmp_folder
            elif code.is_dir():
                target_file_included = False
                for file in code.iterdir():
                    if file.name == target_file:
                        target_file_included = True
                    with open(
                        f"{self.__local_directory}/{file.name}", "w"
                    ) as f:
                        f.write(file.read_text())
                if not target_file_included:
                    raise ValueError(
                        f"Target file {target_file} not found in directory"
                    )
            else:
                raise ValueError(f"Invalid code type: {type(code)}")

        # Add our subprocess execution wrapper
        exec_path = join(
            Path(__file__).parent,
            "extras",
            "python_env",
            "_execute.py",
        )

        with open(exec_path, "r") as f:
            exec_template = f.read()

        exec_template = (
            exec_template.replace("{target_file}", target_file)
            .replace(
                "{client_import}",
                self.__client_import_filename.removesuffix(".py"),
            )
            .replace(
                "{main_function}",
                "main",
            )
        )

        with open(f"{self.__local_directory}/__arkaine_exec.py", "w") as f:
            f.write(exec_template)

        # Now we confirm main function, or set it to run
        # as __main__
        with open(f"{self.__local_directory}/{target_file}", "r") as f:
            body = f.read()
        if "def main()" in body:
            pass

        # Check for any form of __name__ == '__main__' - multiple spaces, "
        # versus ', etc. Then check to see if __name__, ==, and __main__ are in
        # the same line:
        elif re.search(r"__name__\s*==\s*['\"]__main__['\"]", body):
            body = re.sub(
                r"__name__\s*==\s*['\"]__main__['\"]\s*:", "def main():", body
            )
            with open(f"{self.__local_directory}/{target_file}", "w") as f:
                f.write(body)
        else:
            raise ValueError("No main function found")

    def __execute_code(
        self,
        context: Context,
        code: Union[str, IO, Dict[str, str], Path],
        target_file: str = "main.py",
    ):
        """
        Executes the specified code in the Python environment and returns the
        output.

        This method runs the code in the context of the Python environment,
        capturing the output and handling any exceptions that may occur during
        execution.

        Args:
            context (Context): The context associated with the current
                execution.

            code (Union[str, IO, Dict[str, str], Path]): The code to execute.

            target_file (str): The name of the target file to execute.

        Returns:
            Tuple(
                Any: The output of the executed code.
                stdout: The stdout of the executed code.
                stderr: The stderr of the executed code.
            )

        Raises:
            PythonExecutionException: If an error occurs during code execution.
        """
        try:
            stdout, stderr = self.run(
                f"python /{self.__container_directory}/__arkaine_exec.py"
            )

            return context.output, stdout, stderr
        except Exception as e:
            if context.exception:
                raise context.exception
            else:
                raise PythonExecutionException(e, traceback.format_exc())

    def execute(
        self,
        code: Union[str, IO, Dict[str, Union[str, Dict]], Path],
        context: Optional[Context] = None,
        target_file: str = "main.py",
    ) -> Tuple[Any, Exception, str, str]:
        """
        Executes the provided code in the Python environment, managing the
        execution context and handling exceptions.

        This method prepares the execution environment, installs necessary
        modules, and runs the code while capturing output and exceptions. It
        returns the output and any exception that occurred.

        Args:
            code (Union[str, IO, Dict[str, Union[str, Dict]], Path]): The code
                to execute.

            context (Optional[Context]): The context to use for execution. If
                None, a new context will be created.

            target_file (str): The name of the target file to execute. Default
                is "main.py".

        Returns:
            Tuple[Any, Exception]: A tuple containing:
                output: The output of the executed code.
                exception: The exception that occurred during code execution.
                stdout: The stdout of the executed code.
                stderr: The stderr of the executed code.
        """
        if context is None:
            context = Context()

        if context.executing:
            # context = context.child_context(None)
            context = context.child_context(self)

        context.executing = True

        with context:
            self.__copy_code_to_tmp(code, target_file)
            self.__add_bridge_imports()
            self.__install_modules()

            thread = Thread(
                target=self.__run_socket_server,
                args=(context,),
                daemon=True,
            )
            thread.start()

            output, stdout, stderr = self.__execute_code(
                context, code, target_file
            )
            return output, context.exception, stdout, stderr

    def __del__(self):
        """
        Cleans up resources when the PythonEnv instance is deleted, including
        stopping the container and removing temporary files.
        """
        self.__halt = True

        if os.path.exists(self.__local_directory):
            shutil.rmtree(self.__local_directory)

        if os.path.exists(self.__socket_path):
            os.unlink(self.__socket_path)

        super().__del__()

        del self.__tmp_bind

    def __enter__(self) -> PythonEnv:
        """
        Prepares the Python environment for use in a context manager.

        This method starts the Python environment and returns the instance for
        use within the context.

        Returns:
            PythonEnv: The current instance of the PythonEnv.
        """
        self.__halt = False
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Cleans up resources when exiting the context manager.

        This method ensures that the Python environment is properly stopped and
        cleaned up.

        Args:
            exc_type: The type of exception raised, if any.

            exc_value: The value of the exception raised, if any.

            traceback: The traceback object associated with the exception, if
                any.
        """
        self.__halt = True
        self.stop()

    def to_json(self) -> Dict[str, Any]:
        return {
            "id": self.__id,
            "name": self.__name,
            "type": self.__type,
            "version": (
                self.image.split(":")[1] if ":" in self.image else "latest"
            ),
            "modules": self.__modules,
            "image": self.image,
            "tools": [tool.to_json() for tool in self.__tools.values()],
            "volumes": [v.to_json() for v in self.volumes],
            "ports": self.ports,
            "entrypoint": self.entrypoint,
            "command": self.command,
            "env": self.env,
            "container_code_directory": self.__container_directory,
            "socket_file": self.__socket_file,
            "local_code_directory": self.__local_directory,
        }


class PythonExecutionException(Exception):
    def __init__(self, e: Exception, stack_trace: str = ""):
        self.exception = e
        try:
            self.message = e.message
        except:  # noqa: E722
            self.message = str(e)
        self.stack_trace = stack_trace
        super().__init__(self.message)

    def __str__(self):
        return f"{self.message}:\n{self.stack_trace}"


class PythonModuleInstallationException(Exception):
    def __init__(self, e: Exception):
        self.exception = e
        super().__init__(f"Failed to install modules: {e}")
        super().__init__(f"Failed to install modules: {e}")
