from __future__ import annotations

import argparse
import signal
import sys
import threading
from typing import Optional

from arkaine.spellbook.server import SpellbookServer

_server: Optional[SpellbookServer] = None


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    print("\nShutting down servers...")
    if _server:
        _server.stop()
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Start the Composer server")
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="HTTP server port (default: 8080)",
    )

    args = parser.parse_args()

    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    global _server
    _server = SpellbookServer(port=args.port)

    # Start servers in threads
    server_thread = threading.Thread(target=_server.start)
    server_thread.daemon = True
    server_thread.start()

    try:
        print("\nPress Ctrl+C to stop the servers")
        signal.pause()
    except KeyboardInterrupt:
        print("\nShutting down servers...")
        _server.stop()


if __name__ == "__main__":
    main()
