from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING, Any, Dict, Set

from websockets.server import WebSocketServerProtocol
from websockets.sync.server import serve

from arkaine.internal.registrar import Registrar
from arkaine.tools.datastore import ThreadSafeDataStore
from arkaine.tools.events import ToolException, ToolReturn
from arkaine.tools.tool import Context, Event, Tool

if TYPE_CHECKING:
    from arkaine.llms.llm import LLM


class SpellbookSocket:
    """
    SpellbookSocket handles WebSocket connections and broadcasts context events
    to connected clients.
    """

    def __init__(self, port: int = 9001, max_contexts: int = 1024):
        """
        Initialize a SpellbookSocket that creates its own WebSocket endpoint.

        Args:
            port (int): The port to run the WebSocket server on (default: 9001)
            max_contexts (int): The maximum number of contexts to keep in
                memory (default: 1024)
        """
        self.port = port
        self.active_connections: Set[WebSocketServerProtocol] = set()
        self._contexts: Dict[str, Context] = {}
        self._tools: Dict[str, Tool] = {}
        self._llms: Dict[str, LLM] = {}
        self._server = None
        self._server_thread = None
        self._running = False
        self._lock = threading.Lock()
        self.__max_contexts = max_contexts

        Registrar.enable()

        Registrar.add_on_tool_register(self._on_tool_register)
        Registrar.add_on_llm_register(self._on_llm_register)

        Registrar.add_tool_call_listener(self._on_tool_call)
        Registrar.add_llm_call_listener(self._on_llm_call)

        with self._lock:
            tools = Registrar.get_tools()
            for tool in tools:
                self._tools[tool.id] = tool

            llms = Registrar.get_llms()
            for llm in llms:
                self._llms[llm.name] = llm

    def _on_tool_call(self, tool: Tool, context: Context):
        # Subscribe to all the context's events for this tool from
        # here on out if its a root context
        self._handle_context_creation(context)

    def _on_llm_call(self, llm: LLM, context: Context):
        self._handle_context_creation(context)

    def _context_complete(self, context: Context):
        if context.exception:
            self._broadcast_event(context, ToolException(context.exception))
        else:
            self._broadcast_event(context, ToolReturn(context.output))

    def _on_tool_register(self, tool: Tool):
        with self._lock:
            self._tools[tool.id] = tool
        self._broadcast_tool(tool)

    def _on_llm_register(self, llm: "LLM"):
        with self._lock:
            self._llms[llm.name] = llm
        self._broadcast_llm(llm)

    def _handle_context_creation(self, context: Context):
        """
        Add the context to the internal state memory and remove contexts by
        age if over a certain threshold.
        """
        with self._lock:
            if context.is_root:
                self._contexts[context.id] = context
                if len(self._contexts) > self.__max_contexts:
                    oldest_context = min(
                        self._contexts.values(), key=lambda x: x.created_at
                    )
                    del self._contexts[oldest_context.id]

        self._broadcast_context(context)

        context.add_event_listener(
            self._broadcast_event, ignore_children_events=True
        )

        # Handle datastore event listeners
        data, x, debug = context._datastores
        self.__broadcast_datastore(data)
        self.__broadcast_datastore(x)
        self.__broadcast_datastore(debug)
        data.add_listener(self.__broadcast_datastore_update)
        x.add_listener(self.__broadcast_datastore_update)
        debug.add_listener(self.__broadcast_datastore_update)

        context.add_on_end_listener(self._context_complete)

        # If the listener just got added, but the output is already
        # set due to execution timing, we then broadcast now. This
        # may result in a double broadcast, but this is fine.
        if context.output is not None or context.exception is not None:
            self._context_complete(context)

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
                        tool_msg = self.__build_tool_message(tool)
                        websocket.send(json.dumps(tool_msg))
                    except Exception as e:
                        print(f"Failed to send initial tool state: {e}")

                for llm in self._llms.values():
                    try:
                        llm_msg = self.__build_llm_message(llm)
                        websocket.send(json.dumps(llm_msg))
                    except Exception as e:
                        print(f"Failed to send initial LLM state: {e}")

                for context in self._contexts.values():
                    try:
                        websocket.send(
                            json.dumps(self.__build_context_message(context))
                        )
                    except Exception as e:
                        print(f"Failed to send initial context state: {e}")

            # Keep connection alive until client disconnects or server stops
            while self._running:
                try:
                    message = websocket.recv(timeout=1)
                    if message:
                        try:
                            data = json.loads(message)

                            if data["type"] == "llm_execution":
                                self.__handle_llm_execution(data)
                            elif data["type"] == "tool_execution":
                                self.__handle_tool_execution(data)
                            elif data["type"] == "context_retry":
                                self.__handle_context_retry(data)
                            else:
                                print(f"Unknown message type: {data['type']}")

                        except Exception as e:
                            print(f"Failed to parse message: {e}")
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

    def __handle_llm_execution(self, data: dict):
        llm_name: str = data["llm_name"]
        prompt: str = data["prompt"]

        if llm_name not in self._llms:
            raise ValueError(f"LLM with name {llm_name} not found")

        llm = self._llms[llm_name]
        llm(prompt)

    def __handle_tool_execution(self, data: dict):
        tool_id: str = data["tool_id"]
        args: dict = data["args"]

        if tool_id not in self._tools:
            raise ValueError(f"Tool with id {tool_id} not found")

        tool = self._tools[tool_id]
        tool(**args)

    def __handle_context_retry(self, data: dict):
        context_id: str = data["context_id"]
        if context_id not in self._contexts:
            raise ValueError(f"Context with id {context_id} not found")
        context = self._contexts[context_id]

        if context.tool is None:
            raise ValueError("Context has no tool")

        try:
            context.tool.retry(context)
        except Exception as e:
            print(f"Failed to retry context: {e}")

    def __build_tool_message(self, tool: Tool):
        return {"type": "tool", "data": tool.to_json()}

    def _broadcast_tool(self, tool: Tool):
        """Broadcast a tool to all active clients"""
        self._broadcast_to_clients(self.__build_tool_message(tool))

    def __build_llm_message(self, llm: LLM):
        return {"type": "llm", "data": llm.to_json()}

    def _broadcast_llm(self, llm: LLM):
        """Broadcast a LLM to all active clients"""
        self._broadcast_to_clients(self.__build_llm_message(llm))

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

    def __broadcast_datastore(self, datastore: ThreadSafeDataStore):
        """Broadcast a datastore to all active clients"""
        self._broadcast_to_clients(
            {
                "type": "datastore",
                "data": datastore.to_json(),
            }
        )

    def __broadcast_datastore_update(
        self, datastore: ThreadSafeDataStore, key: str, value: Any
    ):
        """Broadcast a datastore update to all active clients"""
        if hasattr(value, "to_json"):
            value = value.to_json()
        else:
            try:
                value = json.dumps(value)
            except Exception:
                if isinstance(value, str):
                    value = value
                else:
                    value = str(value)

        self._broadcast_to_clients(
            {
                "type": "datastore_update",
                "data": {
                    "context": datastore.context,
                    "label": datastore.label,
                    "key": key,
                    "value": value,
                },
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
        if not self._running:
            return

        self._running = False

        with self._lock:
            for websocket in self.active_connections:
                try:
                    websocket.close()
                except Exception:
                    pass
            self.active_connections.clear()

        if self._server:
            try:
                self._server.shutdown()
                self._server.close()
            except Exception:
                pass
            finally:
                self._server = None

        if self._server_thread and self._server_thread.is_alive():
            try:
                self._server_thread.join(timeout=3.0)
            except Exception:
                pass
            finally:
                self._server_thread = None

        print("WebSocket server stopped")

    def __del__(self):
        """Clean up resources when the object is deleted"""
        self.stop()
