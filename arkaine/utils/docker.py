from __future__ import annotations

import shutil
import tempfile
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

from docker import DockerClient
from docker.models.containers import Container as dContainer


class Volume:
    """
    Volume represents a Docker volume that can be used to persist data
    across container runs. It encapsulates the properties and behaviors
    associated with a Docker volume.

    Attributes:
        name (str): A unique identifier for the volume. If not provided,
            a UUID will be generated.
        remote (str): The path inside the container where the volume will
            be mounted. Default is "/data".
        image (Optional[str]): The Docker image associated with the volume.
        persist_volume (bool): Indicates whether the volume should persist
            after the container is stopped. Default is False.
        read_only (bool): Indicates whether the volume should be mounted as
            read-only. Default is False.

    Methods:
        delete():
            Deletes the volume, even if it is marked as persistent. This method
            is intended for manual cleanup of the volume when persistence is no
            longer needed.
    """

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

    def to_json(self) -> Dict[str, Any]:
        return {
            "name": self.__name,
            "remote": self.__remote,
            "image": self.__image,
            "persist_volume": self.__persist_volume,
            "read_only": self.__read_only,
        }

    @classmethod
    def from_json(cls, json: Dict[str, Any]) -> Volume:
        return cls(
            name=json["name"],
            remote=json["remote"],
            image=json["image"],
            persist_volume=json["persist_volume"],
            read_only=json["read_only"],
        )


class BindVolume:
    """
    BindVolume represents a bind mount in Docker, allowing a local directory
    to be mounted into a container. This is useful for sharing files between
    the host and the container.

    Attributes:
        local (Optional[str]): The local path on the host machine to be
            mounted. If not provided, a temporary directory will be created.
        remote (str): The path inside the container where the bind mount will
            be located. Default is "/data".
        name (Optional[str]): A unique identifier for the bind volume. If not
            provided, a UUID will be generated.
        read_only (bool): Indicates whether the bind mount should be read-only.
            Default is False.
    """

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

    def to_json(self) -> Dict[str, Any]:
        return {
            "name": self.__name,
            "local": self.__local,
            "remote": self.__remote,
            "read_only": self.__read_only,
        }

    @classmethod
    def from_json(cls, json: Dict[str, Any]) -> BindVolume:
        return cls(
            local=json["local"],
            remote=json["remote"],
            name=json["name"],
            read_only=json["read_only"],
        )


class Container:
    """
    Container represents a Docker container that can be created, started,
    and managed. It encapsulates the properties and behaviors associated
    with a Docker container.

    Attributes:
        name (str): A unique identifier for the container.
        image (str): The Docker image to use for the container. Default is
                     "alpine:latest".
        args (Dict[str, Any]): Arguments to pass to the container at runtime.
        env (Dict[str, Any]): Environment variables to set in the container.
        volumes (List[Union[BindVolume, Volume]]): A list of volumes to mount
            in the container.
        ports (Dict[str, str]): Port mappings between the container and the
            host.
        entrypoint (Optional[str]): The command to run when the container
            starts.
        command (Optional[str]): The command to execute in the container.

    Methods:
        start():
            Starts the container with the specified configuration, running a
            command to keep it alive.

        run(command: Optional[str]) -> Tuple[str, str]:
            Executes a command in the running container and returns the output
            and error messages.

        bash(command: str) -> str:
            Executes a bash command in the container.

        stop():
            Stops and removes the container.
    """

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

        self._container: Optional[dContainer] = None
        self.__client = DockerClient.from_env()

    def __image_check(self):
        # Check to see if we have the image; if not, attempt
        # to pull it
        try:
            self.__client.images.get(self.__image)
        except:  # noqa: E722
            try:
                self.__client.images.pull(self.__image)
            except:  # noqa: E722
                pass

    def __wait_for_container(self):
        self._container.reload()
        if self._container.status != "running":
            raise DockerExecutionException(
                f"Container failed to start. Status: {self._container.status}"
            )

    def start(self):
        """
        start runs the container with a "sleep infinity" command to keep
        it alive and running until it is told to stop.
        """
        if self._container:
            return

        self.__image_check()

        self._container = self.__client.containers.run(
            self.__image,
            name=self.__name,
            command="sleep infinity",
            detach=True,
            mounts=[v.mount_args() for v in self.__volumes],
            ports=self.__ports,
            environment=self.__env,
            entrypoint=self.__entrypoint,
        )

        self.__wait_for_container()

    def run(self, command: Optional[str]) -> Tuple[str, str]:
        self.__image_check()

        command = self.__command if command is None else command

        if not self._container:
            self.start()

        # Execute execute execute!
        result = self._container.exec_run(
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

        return stdout, stderr

    def bash(self, command: str) -> str:
        # Make sure escape characters are handled for quotations
        command = command.replace("'", "\\'")
        return self.run(f"/bin/bash -c '{command}'")

    def stop(self):
        if self._container:
            self._container.remove(force=True)
            self._container = None

    @property
    def container(self) -> dContainer:
        return self._container

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
