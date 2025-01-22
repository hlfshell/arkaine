from __future__ import annotations

import os
import socketserver
from http.server import SimpleHTTPRequestHandler


class StaticFileHandler(SimpleHTTPRequestHandler):
    """Handler for serving static files from the static directory"""

    def __init__(self, *args, **kwargs):
        # Get the directory containing this file
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        # Change to the static directory before serving
        os.chdir(static_dir)
        # Initialize with the static directory as the base
        super().__init__(*args, directory=static_dir, **kwargs)

    def translate_path(self, path):
        """Override to ensure we stay within the static directory"""
        # Get the directory containing this file
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        # If requesting root, serve index.html
        if path == "/" or path == "":
            return os.path.join(static_dir, "index.html")
        # Otherwise serve from static directory
        return os.path.join(static_dir, path.lstrip("/"))


class SpellbookServer:
    """Serves the static files for the Spellbook UI"""

    def __init__(self, port: int = 8080):
        self.port = port
        self._server = None

    def start(self):
        """Start the HTTP server"""
        print(f"Starting HTTP server on port {self.port}")
        self._server = socketserver.TCPServer(
            ("localhost", self.port), StaticFileHandler
        )
        self._server.serve_forever()

    def stop(self):
        """Stop the HTTP server"""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            print("HTTP server stopped")
