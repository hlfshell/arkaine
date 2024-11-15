from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket

from agents.context import Context, Event


class Server:
    """
    ContextSocket creates contexts and automatically broadcasts their events to
    a WebSocket. This allows for real-time monitoring of agent execution
    through WebSocket connections.
    """

    def __init__(self, port: int = 9001):
        """
        Initialize a Server that creates its own WebSocket endpoint.

        Args:
            port (int): The port to run the WebSocket server on (default: 9001)
        """
        self.port = port
        self.app = FastAPI()
        self.websocket: Optional[WebSocket] = None

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            self.websocket = websocket
            try:
                # Keep connection alive
                while True:
                    await websocket.receive_text()
            except:
                self.websocket = None

    async def _broadcast_event(self, event: Event):
        """
        Broadcasts an event to the WebSocket connection.

        Args:
            event (Event): The event to broadcast
        """
        try:
            await self.websocket.send_json(event.to_json())
        except Exception as e:
            # Log error but don't crash if websocket send fails
            print(f"Failed to send event to websocket: {e}")

    def attach_context(self, context: Context):
        """
        Attaches a context to the server.
        """
        context.add_listener(lambda e: self._broadcast_event(e))

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

    def start(self, host: str = "0.0.0.0", reload: bool = False):
        """
        Starts the WebSocket server with the specified configuration.

        Args:
            host (str): Host to bind the server to (default: '0.0.0.0')
            reload (bool): Enable auto-reload on code changes (default: False)
        """
        config = uvicorn.Config(
            app=self.app, host=host, port=self.port, reload=reload
        )
        uvicorn.Server(config=config).run()


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
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind the server to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload on code changes",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with more verbose output",
    )

    args = parser.parse_args()

    if args.debug:
        import logging

        logging.basicConfig(level=logging.DEBUG)

    server = Server(port=args.port)
    server.start(host=args.host, reload=args.reload)
