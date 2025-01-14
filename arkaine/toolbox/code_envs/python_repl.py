import os
import pickle
import socket
import struct
import time
from concurrent.futures import Future, ThreadPoolExecutor
from os.path import join
from pathlib import Path
from queue import Queue
from threading import Lock, Thread
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

        # self.__install_repl()
        self.__socket = SocketServer(socket_file)
        self.__running = False

    # def __install_repl(self):
    #     with open(
    #         join(Path(__file__).parent, "extras", "python_env", "_repl.py"), "r"
    #     ) as f:
    #         self.__repl_code = f.read()

    #     __repl_code = self.__repl_code.replace(
    #         "{tool_names}", "\n".join([tool.tname for tool in self.__tools])
    #     ).replace("{client_import}", self.__client_import_filename)

    #     with open(join(self.__local_code_directory, "_repl.py"), "w") as f:
    #         f.write(__repl_code)

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
        if not self.__running:
            self.start()

        if context is None:
            context = Context()

        if context.executing:
            context = context.child_context(None)

        context.executing = True

        with context:
            self._add_bridge_imports()
            self._install_modules()
            # self.__install_repl()
            # server = self._run_socket_server(context)

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


class SocketServer:
    """
    A SocketServer is a cross-host/container communication server designed
    to allow code injection and observability into remote code.
    """

    def __init__(self, socket_file: str):
        self.__socket_file = socket_file
        self.__socket: Optional[socket.socket] = None
        self.__run_thread: Optional[Thread] = None
        self.__client_threads = ThreadPoolExecutor()

        self.__running = False
        self.__ready = False

        self.__send_queue: Queue[Tuple[Dict[str, Any], Future]] = Queue()

        self.__lock = Lock()

    @property
    def running(self):
        with self.__lock:
            return self.__running

    @property
    def ready(self):
        with self.__lock:
            return self.__ready

    def start(self):
        with self.__lock:
            if self.__running:
                return

            self.__running = True

        self.__run_thread = Thread(target=self.__run)
        self.__run_thread.start()

    def stop(self):
        with self.__lock:
            if not self.__running:
                return

            self.__running = False
            self.__run_thread.join()
            self.__run_thread = None

            self.__client_threads.shutdown(wait=True)

    def send(self, data: Dict[str, Any]) -> Any:
        future = Future()
        self.__send_queue.put((data, future))
        return future.result()

    def __send_recv_data(
        self, client: socket.socket, data: Dict[str, Any]
    ) -> Any:
        data_bytes = pickle.dumps(data)
        with client:
            client.sendall(struct.pack("!Q", len(data_bytes)))
            client.sendall(data_bytes)

        # Now we handle the response to that data
        size = struct.unpack("!Q", client.recv(8))[0]
        chunks = []
        bytes_received = 0
        while bytes_received < size:
            chunk = client.recv(min(size - bytes_received, 4096))
            if not chunk:
                raise RuntimeError("Client connection broken")
            chunks.append(chunk)
            bytes_received += len(chunk)

        return pickle.loads(b"".join(chunks))

    def __run(self, context: Context):
        """
        Starts a socket server to listen for incoming client connections and
        handle requests.
        """
        if os.path.exists(self.__socket_file):
            os.unlink(self.__socket_file)

        self.__socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.__socket.bind(self.__socket_file)
        self.__socket.listen(5)

        while self.running:
            try:
                # Set socket to non-blocking mode temporarily
                self.__socket.setblocking(False)
                try:
                    client, _ = self.__socket.accept()
                    self.__client_threads.submit(self.__handle_client, client)
                except BlockingIOError:
                    # No client connected, check send queue
                    if not self.__send_queue.empty():
                        data, future = self.__send_queue.get()
                        client = socket.socket(
                            socket.AF_UNIX, socket.SOCK_STREAM
                        )
                        try:
                            client.connect(self.__socket_file)
                            result = self.__send_recv_data(client, data)
                            future.set_result(result)
                            self.__send_queue.task_done()
                        except (socket.error, RuntimeError) as e:
                            print(f"Failed to send data: {e}")
                            if future:
                                future.set_exception(e)
                        finally:
                            client.close()
                finally:
                    self.__socket.setblocking(True)
            except Exception as e:
                print(f"Error in server loop: {e}")
                # Brief pause to prevent tight loop on errors
                time.sleep(0.1)

    def __ping_until_response(self):
        while not self.ready:
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(self.__socket_file)
                result = self.__send_recv_data(sock, {"function": "_ping"})
                if result == "pong":
                    self.__ready = True
                    break
            except (socket.error, RuntimeError):
                time.sleep(0.1)
            finally:
                sock.close()

    def __handle_client(self, client: socket.socket):
        """Handle incoming client connections and requests."""
        try:
            while True:
                try:
                    size = struct.unpack("!Q", client.recv(8))[0]
                    chunks = []
                    bytes_received = 0

                    while bytes_received < size:
                        chunk = client.recv(min(size - bytes_received, 4096))
                        if not chunk:
                            raise RuntimeError("Client connection broken")
                        chunks.append(chunk)
                        bytes_received += len(chunk)

                    data = pickle.loads(b"".join(chunks))

                    if data["function"] == "_ping":
                        response = "pong"
                    elif data["function"] == "_execute":
                        # Handle code execution request
                        code = data["args"][0]
                        response = self.__execute_code(code)
                    else:
                        # Handle other function calls
                        response = self.__handle_function_call(
                            data["function"],
                            data.get("args", []),
                            data.get("kwargs", {}),
                        )

                    # Send response back
                    response_bytes = pickle.dumps(response)
                    client.sendall(struct.pack("!Q", len(response_bytes)))
                    client.sendall(response_bytes)

                except (struct.error, pickle.PickleError) as e:
                    print(f"Protocol error: {e}")
                    break

        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            client.close()

    def __del__(self):
        self.stop()
