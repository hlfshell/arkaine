import pickle
import socket
import struct
import threading
import time


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


def __wait_for_data(sock):
    """Wait for and receive data from the socket."""
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


def __send_data(sock, data):
    """Send data through the socket."""
    data_bytes = pickle.dumps(data)
    sock.sendall(struct.pack("!Q", len(data_bytes)))
    sock.sendall(data_bytes)


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


# def __send_exception(exception):
#     """
#     Send an exception and stack trace to the host.
#     """
#     trace = traceback.format_exc()
#     __call_host_function("_exception", exception, trace)


# def __send_result(result):
#     """
#     Send a result to the host.
#     """
#     __call_host_function("_result", result)


def __call_host_function(func_name, *args, **kwargs):
    """Call a function on the host and return the result."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect("/{code_directory}/{socket_file}")

        # Send the function call request
        __send_data(
            sock, {"function": func_name, "args": args, "kwargs": kwargs}
        )

        # Wait for and return the response
        result = __wait_for_data(sock)

        if isinstance(result, Exception):
            raise result
        return result
    except (socket.error, RuntimeError) as e:
        print(f"Error calling host function: {e}")
        raise
    finally:
        sock.close()


def __message_loop():
    """Main message loop to handle incoming requests from the host."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect("/{code_directory}/{socket_file}")

        while True:
            try:
                data = __wait_for_data(sock)

                if data["function"] == "_execute":
                    # Handle code execution
                    try:
                        result = eval(data["code"], globals(), locals())
                        response = {"status": "success", "result": result}
                    except Exception as e:
                        response = {"status": "error", "error": str(e)}

                    __send_data(sock, response)

            except (socket.error, RuntimeError) as e:
                print(f"Error in message loop: {e}")
                break

    finally:
        sock.close()


# Start the message loop in a separate thread
message_thread = threading.Thread(target=__message_loop, daemon=True)
message_thread.start()

# Wait for the host to connect
__wait_for_host()
