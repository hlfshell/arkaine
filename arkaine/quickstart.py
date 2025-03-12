import atexit
import signal
from threading import Event
from typing import Callable, List, Optional, Union
import threading

from arkaine.internal.logging.logger import GlobalLogger
from arkaine.spellbook.server import SpellbookServer
from arkaine.spellbook.socket import SpellbookSocket
from arkaine.utils.store.context import (
    ContextStore,
    FileContextStore,
    GlobalContextStore,
    InMemoryContextStore,
)


def quickstart(
    context_store: Optional[Union[ContextStore, str]] = InMemoryContextStore(),
    logger: bool = False,
    spellbook_socket: Union[SpellbookSocket, int, bool] = False,
    spellbook_server: Union[SpellbookServer, int, bool] = False,
) -> Callable[[], None]:
    if context_store is not None:
        if isinstance(context_store, str):
            GlobalContextStore.set_store(FileContextStore.load(context_store))
        elif isinstance(context_store, ContextStore):
            GlobalContextStore.set_store(context_store)
        else:
            raise ValueError(
                f"Invalid context store type: {type(context_store)}"
            )

    if logger:
        GlobalLogger.enable()

    if spellbook_socket is not None:
        if isinstance(spellbook_socket, bool):
            if spellbook_socket:
                spellbook_socket = SpellbookSocket()
            else:
                spellbook_socket = None
        elif isinstance(spellbook_socket, int):
            spellbook_socket = SpellbookSocket(port=spellbook_socket)
        elif isinstance(spellbook_socket, SpellbookSocket):
            spellbook_socket = spellbook_socket
        else:
            raise ValueError(
                f"Invalid spellbook type: {type(spellbook_socket)}"
            )

        if spellbook_socket:
            spellbook_socket.start()

            # Setup cleanup for the spellbook server on shutdown
            def cleanup_spellbook_socket():
                spellbook_socket.stop()

            atexit.register(cleanup_spellbook_socket)
            signal.signal(
                signal.SIGTERM, lambda signo, frame: cleanup_spellbook_socket()
            )
            signal.signal(
                signal.SIGINT, lambda signo, frame: cleanup_spellbook_socket()
            )

    if spellbook_server is not None:
        if isinstance(spellbook_server, bool):
            if spellbook_server:
                spellbook_server = SpellbookServer()
        elif isinstance(spellbook_server, int):
            spellbook_server = SpellbookServer(port=spellbook_server)
        elif isinstance(spellbook_server, SpellbookServer):
            spellbook_server = spellbook_server
        else:
            raise ValueError(
                f"Invalid spellbook server type: {type(spellbook_server)}"
            )

        if spellbook_server:
            spellbook_server.start()

            def cleanup_spellbook_server():
                spellbook_server.stop()

            atexit.register(cleanup_spellbook_server)
            signal.signal(
                signal.SIGTERM, lambda signo, frame: cleanup_spellbook_server()
            )
            signal.signal(
                signal.SIGINT, lambda signo, frame: cleanup_spellbook_server()
            )

    def done():
        if spellbook_socket:
            spellbook_socket.stop()

        if spellbook_server:
            spellbook_server.stop()

    return done


def keep_alive(
    cleanup: Union[Callable[[], None], List[Callable[[], None]]] = [],
    force_quit_timeout: float = 3.0,
):
    """
    keep_alive is a simple function that keeps the program alive until a kill
    signal is received.

    The optional cleanup function(s) are called when a kill signal is received

    The optional force_quit_timeout is the number of seconds to wait for cleanup
    *after* all functions passed have been called. If those functions take
    longer than this timeout, the program will force an exit.
    """

    if not isinstance(cleanup, list):
        cleanup = [cleanup]

    running = Event()
    running.set()

    def handle_shutdown(signo, frame):
        running.clear()

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    try:
        while running.is_set():
            # Using a longer sleep time since we're using an event
            running.wait(1.0)
    except KeyboardInterrupt:
        running.clear()
    finally:
        for cleanup_func in cleanup:
            threading.Thread(target=cleanup_func).start()

        # Set up a force exit after 5 seconds in case cleanup hangs
        def force_exit():
            exit(1)  # Use non-zero exit code to indicate abnormal termination

        # Ensure we terminate within the specified timeout, even if cleanup
        # functions hang or some other service holds the main thread.
        force_exit_timer = threading.Timer(force_quit_timeout, force_exit)
        force_exit_timer.daemon = True  # Make sure timer doesn't prevent exit
        force_exit_timer.start()
