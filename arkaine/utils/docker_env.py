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

from docker import DockerClient
from docker.models.containers import Container

from arkaine.tools.tool import Context, Tool


# TODO - this is dumb - we don't need to start a container
# here becaue we just reference it locally anyway.
class DockerVolume:

    def __init__(
        self,
        local: str = None,
        remote: str = "/data",
        name: Optional[str] = None,
        read_only: bool = False,
        image: str = "alpine:latest",
        persist_volume: bool = False,
    ):
        if name is None:
            self.__name = f"arkaine-{uuid4()}"
        else:
            self.__name = name
        self.__local = local
        self.__remote = remote
        self.__read_only = read_only
        self.__client = DockerClient.from_env()
        self.__image = image
        self.__container = None
        self.__persist_volume = persist_volume
        self.__is_bind_mount = local is not None

    @property
    def name(self) -> str:
        return self.__name

    @property
    def local(self) -> str:
        return self.__local

    @property
    def remote(self) -> str:
        return self.__remote

    @property
    def read_only(self) -> bool:
        return self.__read_only

    @property
    def image(self) -> str:
        return self.__image

    @property
    def persist_volume(self) -> bool:
        return self.__persist_volume

    def move_to(self, from_path: str, to_path: str):
        pass

    def mount_args(self) -> Dict[str, str]:
        if self.__is_bind_mount:
            return {
                "type": "bind",
                "source": self.__local,
                "target": self.__remote,
                "read_only": self.__read_only,
            }
        else:
            return {
                "type": "volume",
                "source": self.__name,
                "target": self.__remote,
                "read_only": self.__read_only,
            }

    def start(self):
        # Create volume if not using bind mount
        if not self.__is_bind_mount:
            self.__client.volumes.create(name=self.__name)

        self.__container = self.__client.containers.run(
            self.__image,
            command="sleep infinity",
            detach=True,
            mounts=[self.mount_args()],
        )

    def stop(self):
        if self.__container:
            self.__container.stop()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()

    def __del__(self):
        self.stop()
        # Only try to remove volume if it's not a bind mount and not persistent
        if not self.__is_bind_mount and not self.__persist_volume:
            try:
                self.__client.volumes.get(self.__name).remove()
            except:
                pass  # Ignore errors during cleanup
        self.__client.close()


class DockerContainer:

    def __init__(
        self,
        name: str,
        image: str = "alpine:latest",
        args: Dict[str, Any] = {},
        env: Dict[str, Any] = {},
        volumes: List[DockerVolume] = [],
        ports: Dict[str, str] = [],
        entrypoint: str = None,
        command: Optional[str] = None,
    ):

        self.__name = name
        self.__image = image
        self.__args = args
        self.__env = env
        self.__volumes = volumes

        port_bindings = {}
        if ports:
            for container_port, host_port in ports.items():
                if "/" not in container_port:
                    container_port = f"{container_port}/tcp"
                port_bindings[container_port] = host_port
        self.__ports = port_bindings

        self.__entrypoint = entrypoint
        if command is None:
            self.__command = "sleep infinity"
        else:
            self.__command = command

        self.__container: Optional[Container] = None
        self.__client = DockerClient.from_env()

    def run(self, command: Optional[str]) -> Tuple[str, str]:
        # Check to see if we have the image; if not, attempt
        # to pull it
        try:
            self.__client.images.get(self.__image)
        except:  # noqa: E722
            try:
                self.__client.images.pull(self.__image)
            except:  # noqa: E722
                pass

        self.__container = self.__client.containers.run(
            self.__image,
            name=self.__name,
            command="sleep infinity",
            detach=True,
            mounts=[v.mount_args() for v in self.__volumes],
            ports=self.__ports,
            environment=self.__env,
            entrypoint=self.__entrypoint,
        )

        # Wait for the container to be fully running
        self.__container.reload()
        if self.__container.status != "running":
            raise DockerExecutionException(
                f"Container failed to start. Status: {self.__container.status}"
            )

        # Execute execute execute!
        result = self.__container.exec_run(
            command,
            stderr=True,  # Enable stderr capture
            demux=True,  # Split stdout/stderr apart
        )

        # Capture output
        stdout, stderr = result.output
        stdout = stdout.decode("utf-8") if stdout else ""
        stderr = stderr.decode("utf-8") if stderr else ""

        # Check for errors
        if result.exit_code != 0:
            raise DockerExecutionException(stdout, stderr)

        return stdout

    def stop(self):
        if self.__container:
            self.__container.remove(force=True)
            self.__container = None

    def cleanup(self):
        if self.__container:
            self.stop()
            self.__container.remove()

    @property
    def container(self) -> Container:
        return self.__container

    def __enter__(self):
        self.run(None)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cleanup()

    def __del__(self):
        self.__exit__(None, None, None)
        self.__client.close()


class DockerExecutionException(Exception):
    def __init__(self, message: str, stderr_or_trace: str = None):
        self.message = message
        self.stderr_or_trace = stderr_or_trace
        super().__init__(self.message)

    def __str__(self):
        if self.stderr_or_trace:
            return f"Python code execution failed:\n{self.message}\n\nError output:\n{self.stderr_or_trace}"
        return f"Python code execution failed: {self.message}"


class PythonEnv(DockerContainer):

    def __init__(
        self,
        name: Optional[str] = None,
        version: str = "3.12",
        # modules: Optional[
        #     Union[Dict[str, Union[str, Tuple[str, str]]], List[str]]
        # ] = None,
        image: Optional[str] = None,
        tools: List[Tool] = [],
        volumes: List[DockerVolume] = [],
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
        self.__tmp_bind = DockerVolume(
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

    def __handle_client(self, client: socket, context: Context):
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
            "_bridge_functions.py",
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
            for tool in tools:
                bridge_code += f"""
def {tool.tname}(*args, **kwargs):
    return __call_host_function('{tool.tname}', *args, **kwargs)"""

            f.write(bridge_code)

    def __add_bridge_imports(self):

        ignore_files = ["setup.py", self.__client_import_filename]

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

    def __execute_code(
        self,
        code: Union[str, IO, Dict[str, str], Path],
        target_file: str = "main.py",
    ):
        try:
            result = self.run(f"python /arkaine/{target_file}")

            return result
        except Exception as e:
            raise PythonExecutionException(str(e), traceback.format_exc())
        finally:
            self.stop()

    def execute(
        self,
        code: Union[str, IO, Dict[str, Union[str, Dict]], Path],
        context: Optional[Context] = None,
        target_file: str = "main.py",
    ) -> str:
        if context is None:
            context = Context()

        with context:
            self.__copy_code_to_tmp(code, target_file)

            if self.__tools:
                self.__add_bridge_imports()

                if self.__server_thread is None:
                    self.__server_thread = Thread(
                        target=self.__run_socket_server,
                        args=(context,),
                        daemon=True,
                    )
                    self.__server_thread.start()

            return self.__execute_code(code, target_file)

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


class PythonNotParseableException(Exception):
    def __init__(self, message: str, stack_trace: str = None):
        self.message = message
        self.stack_trace = stack_trace
        super().__init__(self.message)

    def __str__(self):
        if self.stack_trace:
            return f"Python code is not parseable:\n{self.message}\n\nStack trace:\n{self.stack_trace}"
        return f"Python code is not parseable: {self.message}"


class PythonExecutionException(Exception):
    def __init__(self, message: str, stderr_or_trace: str = None):
        self.message = message
        self.stderr_or_trace = stderr_or_trace
        super().__init__(self.message)

    def __str__(self):
        if self.stderr_or_trace:
            return f"Python code execution failed:\n{self.message}\n\nError output:\n{self.stderr_or_trace}"
        return f"Python code execution failed: {self.message}"
