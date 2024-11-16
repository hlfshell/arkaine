from __future__ import annotations

import json
import socket
import threading
from typing import Dict, Optional, Set

from websockets.server import WebSocketServerProtocol
from websockets.sync.server import serve

from agents.context import Context, Event


class ContextSocket:
    """
    ContextSocket creates contexts and automatically broadcasts their events to
    a WebSocket. This allows for real-time monitoring of agent execution
    through WebSocket connections.
    """

    def __init__(self, port: int = 9001):
        """
        Initialize a ContextSocket that creates its own WebSocket endpoint.

        Args:
            port (int): The port to run the WebSocket server on (default: 9001)
        """
        self.port = port
        self.active_connections: Set[WebSocketServerProtocol] = set()
        self._contexts: Dict[str, Context] = {}  # Track contexts by ID
        self._server = None
        self._server_thread = None
        self._running = False
        self._lock = threading.Lock()

    def _handle_client(self, websocket):
        """Handle an individual client connection"""
        print("New client connected")
        with self._lock:
            self.active_connections.add(websocket)
            # Send initial context states to new client
            for context_id, context in self._contexts.items():
                init_message = {
                    "type": "context_init",
                    "context_id": context_id,
                    "parent_id": context._Context__parent_id,
                    "status": context.status,
                }
                websocket.send(json.dumps(init_message))
        try:
            while self._running:
                try:
                    websocket.recv()
                except Exception:
                    break
        except Exception as e:
            print(f"Client connection error: {e}")
        finally:
            with self._lock:
                self.active_connections.remove(websocket)
            print("Client disconnected")

    def _broadcast_event(self, id: str, event: Event):
        """
        Broadcasts an event to all active WebSocket connections.

        Args:
            event (Event): The event to broadcast
        """
        event_data = event.to_json()
        event_data["context_id"] = id

        message = json.dumps(event_data)

        dead_connections = set()
        with self._lock:
            for websocket in self.active_connections:
                try:
                    print("SENDING", message)
                    websocket.send(message)
                except Exception as e:
                    print(f"Failed to send event to websocket: {e}")
                    dead_connections.add(websocket)

            self.active_connections -= dead_connections

    def attach_context(self, context: Context):
        """
        Attaches a context to the socket for event broadcasting.
        """
        self._contexts[context._Context__id] = context
        context.add_listener(self._broadcast_event)

    def create_context(self, parent_id: Optional[str] = None) -> Context:
        """
        Creates a new Context and sets up event broadcasting to the WebSocket.

        Args:
            parent_id (Optional[str]): Optional parent context ID

        Returns:
            Context: A new context instance that will broadcast events to the
            WebSocket
        """
        context = Context(parent_id=parent_id)
        self.attach_context(context)
        return context

    def _run_server(self):
        """Run the WebSocket server"""
        print(f"Starting WebSocket server on port {self.port}")
        with serve(self._handle_client, "localhost", self.port) as server:
            self._server = server
            self._running = True
            server.serve_forever()

    def start(self):
        """Start the WebSocket server in a background thread"""
        if self._running:
            return

        self._running = True
        self._server_thread = threading.Thread(
            target=self._run_server, daemon=True
        )
        self._server_thread.start()
        print("WebSocket server started")

    def stop(self):
        """Stop the WebSocket server"""
        self._running = False
        if self._server:
            self._server.shutdown()
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join()
        self._server_thread = None
        print("WebSocket server stopped")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Start the WebSocket server for agent monitoring"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9001,
        help="Port to run the server on (default: 9001)",
    )

    args = parser.parse_args()
    context_socket = ContextSocket(port=args.port)

    try:
        context_socket.start()
        # Keep main thread alive
        while True:
            import time

            time.sleep(1)
    except KeyboardInterrupt:
        context_socket.stop()
