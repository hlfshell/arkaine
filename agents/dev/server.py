from __future__ import annotations

import json
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

    def _broadcast_to_clients(self, message: dict):
        """Helper function to broadcast a message to all active clients"""

        with self._lock:
            dead_connections = set()
            for websocket in self.active_connections:
                try:
                    websocket.send(json.dumps(message))
                except Exception as e:
                    print(
                        f"Failed to send to client {websocket.remote_address}: "
                        f"{e}"
                    )
                    dead_connections.add(websocket)

            # Clean up dead connections
            self.active_connections -= dead_connections

    def _handle_client(self, websocket):
        """Handle an individual client connection"""
        try:
            remote_addr = websocket.remote_address
            print(f"New client connected from {remote_addr}")
        except Exception:
            remote_addr = "unknown"
            print("New client connected (address unknown)")

        try:
            with self._lock:
                self.active_connections.add(websocket)
                # Send initial context states and their events immediately
                for context in self._contexts.values():
                    try:
                        # Send full context state
                        context_state = context.to_json()
                        websocket.send(
                            json.dumps({"type": "context", **context_state})
                        )

                        # Send historical events
                        for event in context_state["history"]:
                            websocket.send(json.dumps(event))

                    except Exception as e:
                        print(f"Failed to send initial context state: {e}")
                        return

            # Keep connection alive until client disconnects or server stops
            while self._running:
                try:
                    message = websocket.recv(timeout=1)
                    if message:  # Handle any client messages if needed
                        pass
                except TimeoutError:
                    continue
                except Exception:
                    break

        except Exception as e:
            print(f"Client connection error: {e}")
        finally:
            with self._lock:
                self.active_connections.discard(websocket)
            print(f"Client disconnected from {remote_addr}")

    def _broadcast_event(self, id: str, event: Event):
        """Broadcasts an event to all active WebSocket connections."""
        event_data = event.to_json()
        self._broadcast_to_clients(
            {
                "type": "event",
                "context_id": id,
                "data": event_data,
            }
        )

    def attach_context(self, context: Context):
        """Attaches a context to the socket for event broadcasting."""
        self._contexts[context.id] = context

        # Broadcast full context state
        context_state = context.to_json()
        self._broadcast_to_clients({"type": "context", "data": context_state})

        # Broadcast historical events
        for event in context_state["history"]:
            self._broadcast_to_clients(event)

        # Set up event listener for future events
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
