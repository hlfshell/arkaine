import os
import pickle
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

from arkaine.tools.tool import Context, Tool
from arkaine.utils.docker import BindVolume, Container, Volume


class PythonEnv(Container):

    def __init__(
        self,
        name: Optional[str] = None,
        version: str = "3.12",
        # modules: Optional[
        #     Union[Dict[str, Union[str, Tuple[str, str]]], List[str]]
        # ] = None,
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
    ):
        if name is None:
            name = f"arkaine-python-{uuid4()}"
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

        self.__client_import_filename = "arkaine_bridge.py"

        self.__server_thread: Optional[Thread] = None
        self.__halt = False

        self.__load_bridge_functions(tools)

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

    # def __install_modules(
    #     self,
    #     modules: Union[Dict[str, Union[str, Tuple[str, str]]], List[str]],
    # ):
    #     pass

    def __handle_client(self, client: socket, context: Context) -> Any:
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
        How this works - basically it opens the socket and checks for a
        connection. Once made (via a message being sent), we create a thread
        to handle the client message coming in. This allows possibly multiple 
        incoming messages to be processed in parallel. Then we start listening
        yet again. Of course, we also have a __halt check; if we call stop or
        go to delete the process we stop this and die off.

        TODO - use a threadpool executor to clean this up
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
                bridge_code += tool_call_template.replace(
                    "{tool_name}", tool.tname
                )

            f.write(bridge_code)

    def __add_bridge_imports(self):

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
        elif "if __name__ == '__main__'" in body:
            body = body.replace("if __name__ == '__main__':", "def main():")
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
        try:
            # result = self.run(f"python /{self.__container_directory}/{target_file}")
            self.run(f"python /{self.__container_directory}/__arkaine_exec.py")

            return context.output
        except Exception as e:
            if context.exception:
                raise context.exception
            else:
                raise PythonExecutionException(e, traceback.format_exc())
        finally:
            self.stop()

    def execute(
        self,
        code: Union[str, IO, Dict[str, Union[str, Dict]], Path],
        context: Optional[Context] = None,
        target_file: str = "main.py",
    ) -> Tuple[Any, Exception]:
        if context is None:
            context = Context()

        with context:
            context.executing = True
            self.__copy_code_to_tmp(code, target_file)

            # if self.__tools:
            self.__add_bridge_imports()

            if self.__server_thread is None:
                self.__server_thread = Thread(
                    target=self.__run_socket_server,
                    args=(context,),
                    daemon=True,
                )
                self.__server_thread.start()

            self.__execute_code(context, code, target_file)
            return context.output, context.exception

    def __del__(self):
        self.__halt = True

        if self.__server_thread is not None:
            self.__server_thread.join(timeout=1)

        if os.path.exists(self.__local_directory):
            shutil.rmtree(self.__local_directory)

        if os.path.exists(self.__socket_path):
            os.unlink(self.__socket_path)

        super().__del__()

        del self.__tmp_bind

    def __enter__(self):
        self.__halt = False
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.__halt = True
        self.stop()


class PythonExecutionException(Exception):
    def __init__(self, e: Exception, stack_trace: str = ""):
        self.exception = e
        try:
            self.message = e.message
        except:
            self.message = str(e)
        self.stack_trace = stack_trace
        super().__init__(self.message)
