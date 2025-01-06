import shutil
import tempfile
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

from docker import DockerClient
from docker.models.containers import Container


class Volume:

    def __init__(
        self,
        name: Optional[str] = None,
        remote: str = "/data",
        image: Optional[str] = None,
        persist_volume: bool = False,
        read_only: bool = False,
    ):
        if name is None:
            self.__name = f"arkaine-{uuid4()}"
        else:
            self.__name = name
        self.__remote = remote
        self.__image = image
        self.__persist_volume = persist_volume
        self.__read_only = read_only

    @property
    def name(self) -> str:
        return self.__name

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

    def mount_args(self) -> Dict[str, str]:
        return {
            "type": "volume",
            "source": self.__name,
            "target": self.__remote,
            "read_only": self.__read_only,
        }

    def delete(self):
        """
        Deletes the volume, *even if persist volume is set*; this
        is meant as an "overwrite" method to manually clean up the
        volume after its persistence is unneeded.
        """
        self.__persist_volume = False
        del self

    def __del__(self):
        if self.__persist_volume:
            pass
        else:
            self.__client.volumes.get(self.__name).remove()


class BindVolume:

    def __init__(
        self,
        local: Optional[str] = None,
        remote: str = "/data",
        name: Optional[str] = None,
        read_only: bool = False,
    ):
        if name is None:
            self.__name = f"arkaine-{uuid4()}"
        else:
            self.__name = name
        if local is None:
            self.__local = tempfile.mkdtemp()
            self.__tmpdir = True
        else:
            self.__local = local
            self.__tmpdir = False
        self.__remote = remote
        self.__read_only = read_only

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
        return {
            "type": "bind",
            "source": self.__local,
            "target": self.__remote,
            "read_only": self.__read_only,
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def __del__(self):
        if self.__tmpdir:
            shutil.rmtree(self.__local)


class Container:

    def __init__(
        self,
        name: str,
        image: str = "alpine:latest",
        args: Dict[str, Any] = {},
        env: Dict[str, Any] = {},
        volumes: List[Union[BindVolume, Volume]] = [],
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
