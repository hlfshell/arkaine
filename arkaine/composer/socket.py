from __future__ import annotations

import json
import threading
from typing import Dict, Set

from websockets.server import WebSocketServerProtocol
from websockets.sync.server import serve

from arkaine.registrar.registrar import Registrar
from arkaine.tools.events import ToolException, ToolReturn
from arkaine.tools.tool import Context, Event, Tool


class ComposerSocket:
    """
    ComposerSocket handles WebSocket connections and broadcasts context events
    to connected clients.
    """

    def __init__(self, port: int = 9001, max_contexts: int = 1024):
        """
        Initialize a ComposerSocket that creates its own WebSocket endpoint.

        Args:
            port (int): The port to run the WebSocket server on (default: 9001)
            max_contexts (int): The maximum number of contexts to keep in
                memory (default: 1024)
        """
        self.port = port
        self.active_connections: Set[WebSocketServerProtocol] = set()
        self._contexts: Dict[str, Context] = {}
        self._tools: Dict[str, Tool] = {}
        self._server = None
        self._server_thread = None
        self._running = False
        self._lock = threading.Lock()
        self.__max_contexts = max_contexts

        Registrar.enable()
        Registrar.add_tool_call_listener(self._on_tool_call)

        Registrar.add_on_tool_register(self._on_tool_register)

        with self._lock:
            tools = Registrar.get_tools()
            for tool in tools:
                self._tools[tool.id] = tool

    def _on_tool_call(self, tool: Tool, context: Context):
        # Subscribe to all the context's events for this tool from
        # here on out if its a root context
        self._handle_context_creation(context)
        self._broadcast_context(context)
        context.add_event_listener(
            self._broadcast_event, ignore_children_events=True
        )
        context.add_on_end_listener(self._context_complete)

    def _context_complete(self, context: Context):
        if context.exception:
            self._broadcast_event(context, ToolException(context.exception))
        else:
            self._broadcast_event(context, ToolReturn(context.output))

    def _on_tool_register(self, tool: Tool):
        with self._lock:
            self._tools[tool.id] = tool
        self._broadcast_tool(tool)

    def _handle_context_creation(self, context: Context):
        """
        Add the context to the internal state memory and remove contexts by
        age if over a certain threshold.
        """
        with self._lock:
            if not context.is_root:
                return
            self._contexts[context.id] = context
            if len(self._contexts) > self.__max_contexts:
                oldest_context = min(
                    self._contexts.values(), key=lambda x: x.created_at
                )
                del self._contexts[oldest_context.id]

    def _broadcast_to_clients(self, message: dict):
        """Helper function to broadcast a message to all active clients"""
        with self._lock:
            dead_connections = set()
            for websocket in self.active_connections:
                try:
                    websocket.send(json.dumps(message))
                except Exception as e:
                    print(f"Failed to send to client {websocket}: {e}")
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

                for tool in self._tools.values():
                    try:
                        websocket.send(
                            json.dumps(self.__build_tool_message(tool))
                        )
                    except Exception as e:
                        print(f"Failed to send initial tool state: {e}")
                        return

                for context in self._contexts.values():
                    try:
                        websocket.send(
                            json.dumps(self.__build_context_message(context))
                        )

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

    def __build_tool_message(self, tool: Tool):
        return {"type": "tool", "data": tool.to_json()}

    def _broadcast_tool(self, tool: Tool):
        """Broadcast a tool to all active clients"""
        self._broadcast_to_clients(self.__build_tool_message(tool))

    def __build_context_message(self, context: Context):
        return {"type": "context", "data": context.to_json()}

    def _broadcast_context(self, context: Context):
        """Broadcast a context to all active clients"""
        self._broadcast_to_clients(self.__build_context_message(context))

    def _broadcast_event(self, context: Context, event: Event):
        """Broadcasts an event to all active WebSocket connections."""
        event_data = event.to_json()
        self._broadcast_to_clients(
            {
                "type": "event",
                "context_id": context.id,
                "data": event_data,
            }
        )

    def start(self):
        """Start the WebSocket server in a background thread"""
        if self._running:
            return

        self._running = True
        self._server_thread = threading.Thread(
            target=self._run_server, daemon=True
        )
        self._server_thread.start()
        print(f"WebSocket server started on ws://localhost:{self.port}")

    def _run_server(self):
        """Run the WebSocket server"""
        with serve(self._handle_client, "localhost", self.port) as server:
            self._server = server
            server.serve_forever()

    def stop(self):
        """Stop the WebSocket server"""
        self._running = False
        if self._server:
            self._server.shutdown()
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join()
        self._server_thread = None
        print("WebSocket server stopped")

    def __del__(self):
        """Clean up resources when the object is deleted"""
        self.stop()
