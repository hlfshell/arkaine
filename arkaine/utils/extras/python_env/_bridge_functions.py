import pickle
import socket
import struct
import time
import traceback


def __wait_for_host():
    """
    Wait for the host to become available by attempting to connect to the
    socket.
    """
    while True:
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect("/{code_directory}/{socket_file}")
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
    """
    Send data to the host and receive a response.
    """
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


def __send_exception(exception):
    """
    Send an exception and stack trace to the host.
    """
    trace = traceback.format_exc()
    __call_host_function("_exception", exception, trace)


def __send_result(result):
    """
    Send a result to the host.
    """
    __call_host_function("_result", result)


def __call_host_function(func_name, *args, **kwargs):
    """
    Call a function on the host and return the result.
    """
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect("/{code_directory}/{socket_file}")
        result = __send_recv_data(
            sock, {"function": func_name, "args": args, "kwargs": kwargs}
        )

        if isinstance(result, Exception):
            raise result
        return result
    finally:
        sock.close()


# Wait for the host to connect to give us the go-ahead
__wait_for_host()
