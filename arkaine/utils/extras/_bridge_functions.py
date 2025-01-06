import pickle
import socket
import struct
import time


def __wait_for_host():
    """Wait for the host to become available by attempting to connect to the socket."""
    while True:
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect("/arkaine/arkaine_bridge.sock")
            # Send a ping and wait for acknowledgment
            result = __send_recv_data(
                sock, {"function": "_ping", "args": (), "kwargs": {}}
            )
            if result == "pong":
                return
        except (socket.error, RuntimeError):
            time.sleep(0.1)
        finally:
            sock.close()


def __send_recv_data(sock, data):
    # Send size first, then data
    data_bytes = pickle.dumps(data)
    sock.sendall(struct.pack("!Q", len(data_bytes)))
    sock.sendall(data_bytes)

    # Receive size, then response
    size = struct.unpack("!Q", sock.recv(8))[0]
    chunks = []
    bytes_received = 0
    while bytes_received < size:
        chunk = sock.recv(min(size - bytes_received, 4096))
        if not chunk:
            raise RuntimeError("Connection broken")
        chunks.append(chunk)
        bytes_received += len(chunk)

    return pickle.loads(b"".join(chunks))


def __call_host_function(func_name, *args, **kwargs):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect("/arkaine/arkaine_bridge.sock")
        result = __send_recv_data(
            sock, {"function": func_name, "args": args, "kwargs": kwargs}
        )

        if isinstance(result, Exception):
            raise result
        return result
    finally:
        sock.close()


__wait_for_host()
