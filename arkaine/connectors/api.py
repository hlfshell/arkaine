import json
import os
import secrets
from abc import ABC, abstractmethod
from typing import List, Optional, Union

import jwt
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from arkaine.internal.registrar import Registrar
from arkaine.tools.context import Context
from arkaine.tools.tool import Tool


class AuthRequest(BaseModel):
    tools: Union[str, List[str]]
    key: str


class AuthResponse(BaseModel):
    token: str


class Auth(ABC):
    """
    Auth is an abstract class that defines an authentication and authorization
    interface for optional use for ToolAPI.
    """

    def __init__(self):
        super().__init__()

    @abstractmethod
    def auth(self, request: Request, tool: Tool) -> bool:
        """
        Authenticate and authorize the request.
        """
        pass

    @abstractmethod
    def issue(self, request: AuthRequest) -> str:
        """
        Issue an auth token for the given tools.
        """
        pass


class API(FastAPI):
    """
    API provides a FastAPI-based HTTP interface for arkAIne tools. It allows
    tools to be exposed as REST endpoints with automatic OpenAPI documentation
    generation, authentication support, and flexible input/output handling.

    Quick Start:
        Basic usage with a single tool:
        ```python
        from arkAIne.triggers.api import ToolAPI

        # Create API with a single tool
        api = API(my_tool)
        api.serve()  # Starts server at http://localhost:8000
        ```

        Multiple tools with custom prefix:
        ```python
        # Create API with multiple tools and custom route prefix
        api = API(
            tools=[tool1, tool2, tool3],
            name="MyAPI",
            prefix="/api/v1"
        )
        api.serve(port=8080)
        ```

        With authentication:
        ```python
        from arkaine.triggers.api import API, JWTAuth

        # Create auth handler with secret and API keys
        auth = JWTAuth.from_file("auth_config.json")

        # Create authenticated API
        api = API(
            tools=my_tools,
            auth=auth
        )

        # Get auth token
        token = auth.issue(AuthRequest(tools=["tool1"], key="my-api-key"))

        # Make authenticated request
        # curl -H "Authorization: Bearer {token}" \
        #      http://localhost:8000/api/tool1
        ```

    Input Methods:
        - Query parameters: /api/tool?arg1=value1&arg2=value2
        - JSON body: POST with {"arg1": "value1", "arg2": "value2"}
        - Mixed: Both query params and JSON body (body takes precedence)

    Response Format:
        Success:
        ```json
        {
            "result": <tool output>,
            "context": <context data if requested>
        }
        ```

        Error:
        ```json
        {
            "detail": "Error message",
            "context": <context data if requested>
        }
        ```

    Headers:
        - X-Return-Context: Set to "true" to include context in response
        - X-Context-ID: Returned in response with context identifier
        - Authorization: Bearer token for authenticated endpoints
    """

    def __init__(
        self,
        tools: Union[Tool, List[Tool]],
        name: Optional[str] = None,
        description: Optional[str] = None,
        prefix: str = "/api",
        api_docs: str = "/api",
        auth: Optional[Auth] = None,
    ):
        """
        Initialize the server.

        Args:
            tools: Tool or list of tools to create endpoints for
            name: Name for the API (defaults to first tool's name)
            description: Description for the API
            prefix: Prefix for all routes (e.g., "/api")
            api_docs: URL for API documentation (set to None to disable)
        """
        self.tools = [tools] if isinstance(tools, Tool) else tools
        name = name or "Arkaine API"
        description = description or "API generated from arkAIne tools"

        super().__init__(
            title=name,
            description=description,
            docs_url=api_docs,
        )

        self._prefix = prefix
        self.auth = auth

        # Add routes for tools
        for tool in self.tools:
            self.add_tool_route(tool)

        # Add authentication middleware and route if auth is provided
        if auth:
            # Add auth endpoint
            route = "/auth"
            if self._prefix:
                route = f"{self._prefix.rstrip('/')}{route}"
            self._auth_route = route
            self.add_api_route(
                route,
                self.auth_handler,
                methods=["POST"],
                response_model=AuthResponse,
            )

            # Add auth middleware
            @self.middleware("http")
            async def auth_middleware(request: Request, call_next):
                return await self._auth_middleware(request, call_next)

    async def _auth_middleware(self, request: Request, call_next):
        """Handle authentication middleware for HTTP requests."""
        try:
            # Skip auth check for auth endpoint
            if request.url.path == self._auth_route:
                return await call_next(request)

            # Find matching tool based on path
            path = request.url.path.rstrip("/")
            if self._prefix:
                prefix = self._prefix.rstrip("/")
                if path.startswith(prefix):
                    path = path[len(prefix) :]

            path = path.lstrip("/")
            matching_tool = None
            for tool in self.tools:
                if path == tool.tname:
                    matching_tool = tool
                    break

            if matching_tool and not self.auth.auth(request, matching_tool):
                return JSONResponse(
                    status_code=401, content={"detail": "Unauthorized"}
                )

            return await call_next(request)
        except Exception as e:
            return JSONResponse(status_code=500, content={"detail": str(e)})

    def __create_endpoint_handler(self, tool: Tool):
        """Create a handler function for a tool endpoint."""

        async def handler(request: Request):
            try:
                # Get query parameters
                query_params = dict(request.query_params)

                # Get JSON body if present
                body_params = {}
                if request.headers.get("content-type") == "application/json":
                    try:
                        body_params = await request.json()
                    except json.JSONDecodeError:
                        pass

                # Combine parameters (body takes precedence)
                params = {**query_params, **body_params}

                # Convert types based on tool arguments
                converted_params = {}
                for arg in tool.args:
                    if arg.name in params:
                        try:
                            if arg.type == "int":
                                converted_params[arg.name] = int(
                                    params[arg.name]
                                )
                            elif arg.type == "float":
                                converted_params[arg.name] = float(
                                    params[arg.name]
                                )
                            elif arg.type == "bool":
                                converted_params[arg.name] = str(
                                    params[arg.name]
                                ).lower() in ["true", "1", "yes"]
                            else:
                                converted_params[arg.name] = params[arg.name]
                        except (ValueError, TypeError):
                            raise HTTPException(
                                status_code=400,
                                detail=f"Invalid type for parameter {arg.name}",
                            )
                    elif arg.required:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Missing required parameter: {arg.name}",
                        )
                    elif arg.default is not None:
                        converted_params[arg.name] = arg.default

                # Execute tool
                context = Context(tool)
                try:
                    result = tool(context=context, **converted_params)
                except Exception as e:
                    if request.headers.get("X-Return-Context"):
                        raise HTTPException(
                            status_code=500,
                            detail={
                                "error": str(e),
                                "context": context.to_json(),
                            },
                        )
                    else:
                        raise HTTPException(
                            status_code=500,
                            detail={"error": str(e)},
                        )

                response = {"result": result}

                if request.headers.get("X-Return-Context"):
                    response["context"] = context.to_json()
                # Always set context ID in response header

                return JSONResponse(
                    content=response,
                    headers={
                        "X-Context-ID": context.id,
                    },
                )

            except Exception as e:
                if isinstance(e, HTTPException):
                    raise e
                raise HTTPException(status_code=500, detail=str(e))

        return handler

    def add_tool_route(
        self,
        tool: Tool,
        route: Optional[str] = None,
        method: Union[str, List[str]] = "POST",
    ):
        # Confirm that the route, if set, is valid and starts/ends
        # correctly
        if route:
            if not route.startswith("/"):
                route = f"/{route}"
            if not route.endswith("/"):
                route = f"{route}/"
        else:
            route = f"/{tool.name}/"

        # Add route prefix if specified for server
        if self._prefix:
            route = f"{self._prefix.rstrip('/')}{route}"

        # Confirm that the route isn't already used
        if route in self.routes:
            raise ValueError(f"Route {route} is already registered")

        # Confirm that all methods listed are valid methods
        if isinstance(method, str):
            method = [method]
        for m in method:
            if m not in ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]:
                raise ValueError(f"Invalid method: {m}")

        # Add route documentation
        description = f"{tool.name}\n\n{tool.description}\n\nArguments:\n"
        for arg in tool.args:
            description += f"\n- {arg.name}: {arg.description}"
            if arg.required:
                description += " (required)"
            if arg.default is not None:
                description += f" (default: {arg.default})"

        if tool.examples:
            description += "\n\nExamples:\n"
            for example in tool.examples:
                description += f"\n{example.name}:"
                if example.description:
                    description += f" {example.description}"
                description += f"\nInput: {json.dumps(example.args)}"
                if example.output:
                    description += f"\nOutput: {example.output}"

        self.add_api_route(
            route,
            self.__create_endpoint_handler(tool),
            methods=method,
            description=description,
        )

    @staticmethod
    def __strip_bearer(auth_header: Optional[str]) -> Optional[str]:
        """Helper method to strip 'Bearer ' prefix from auth header"""
        if not auth_header:
            return None
        return auth_header.replace("Bearer ", "")

    async def auth_handler(self, request: Request) -> AuthResponse:
        """Handle authentication requests and return JWT tokens"""
        try:
            # Parse the raw request body into AuthRequest model
            body = await request.json()
            auth_request = AuthRequest(**body)
            return AuthResponse(token=self.auth.issue(auth_request))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def serve(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        ssl_keyfile: Optional[str] = None,
        ssl_certfile: Optional[str] = None,
        ssl_keyfile_password: Optional[str] = None,
        reload: bool = False,
        workers: Optional[int] = None,
        log_level: str = "info",
        proxy_headers: bool = True,
        forwarded_allow_ips: Optional[str] = None,
    ):
        """
        Runs the API server with configurable HTTP/WebSocket support and SSL
        options.

        Args:
            host: Bind socket to this host. Defaults to "127.0.0.1".

            port: Bind socket to this port. Defaults to 8000.

            ssl_keyfile: SSL key file path for HTTPS/WSS support.

            ssl_certfile: SSL certificate file path for HTTPS/WSS support.

            ssl_keyfile_password: Password for decrypting SSL key file.

            reload: Enable auto-reload on code changes (development only).
                Defaults to False.

            workers: Number of worker processes. Defaults to 1.

            log_level: Logging level (critical, error, warning, info, debug).
                Defaults to "info".

            proxy_headers: Enable processing of proxy headers. Defaults to
                True.

            forwarded_allow_ips: Comma separated list of IPs to trust with
                proxy headers. Defaults to the $FORWARDED_ALLOW_IPS environment
                variable or "127.0.0.1".

        Note:
            - At least one of `http` or `ws` must be True.
            - For SSL support, both ssl_keyfile and ssl_certfile must be
              provided.
            - WebSocket endpoints will be available at the same routes as HTTP
              endpoints when ws=True.
        """

        ssl_config = None
        if ssl_keyfile and ssl_certfile:
            ssl_config = {
                "keyfile": ssl_keyfile,
                "certfile": ssl_certfile,
            }
            if ssl_keyfile_password:
                ssl_config["password"] = ssl_keyfile_password

        uvicorn.run(
            self,
            host=host,
            port=port,
            ssl_keyfile=ssl_keyfile,
            ssl_certfile=ssl_certfile,
            ssl_keyfile_password=ssl_keyfile_password,
            reload=reload,
            workers=workers,
            log_level=log_level,
            proxy_headers=proxy_headers,
            forwarded_allow_ips=forwarded_allow_ips,
        )


class JWTAuth(Auth):
    """
    JSONWebTokenAuth is an implementation of Auth that uses JSON Web Tokens
    for authentication and authorization.
    """

    def __init__(self, secret: str, keys: List[str]):
        super().__init__()
        self.secret = secret
        self.keys = dict(zip(keys, [None] * len(keys)))

    def auth(self, request: Request, tool: Tool) -> bool:
        token = request.headers.get("Authorization")

        if not token:
            return False

        # Strip 'Bearer ' prefix if present
        if token.startswith("Bearer "):
            token = token[7:]

        try:
            payload = jwt.decode(token, self.secret, algorithms=["HS256"])

            if "all" in payload["tools"] or tool.tname in payload["tools"]:
                return True
            else:
                return False
        except jwt.InvalidTokenError as e:
            return False

    def issue(self, request: AuthRequest) -> str:
        """
        Issue a JWT token for the given tools.
        """
        possible_tools = Registrar.get_tools()
        tools_requested = request.tools

        if isinstance(request.tools, str):
            tools_requested = [request.tools]

        key = request.key

        # Compare the key against known keys
        if key not in self.keys:
            raise HTTPException(status_code=401, detail="Invalid key")

        # Confirm that requested tools exist
        if (isinstance(tools_requested, str) and tools_requested != "all") or (
            isinstance(tools_requested, list) and tools_requested != ["all"]
        ):
            if isinstance(tools_requested, str):
                tools_requested = [tools_requested]
            for tool_name in tools_requested:
                if tool_name not in possible_tools:
                    raise HTTPException(status_code=401, detail="Invalid tool")

        # Now that we have allowed_tools, create a JWT token
        payload = {"tools": tools_requested}
        token = jwt.encode(payload, self.secret, algorithm="HS256")

        return token

    @classmethod
    def from_env(cls):
        secret = os.getenv("JWT_SECRET")
        if not secret:
            raise ValueError("JWT_SECRET environment variable is not set")
        keys = os.getenv("JWT_KEYS")
        if not keys:
            raise ValueError("JWT_KEYS environment variable is not set")
        return cls(secret, keys)

    @classmethod
    def from_file(cls, path: str):
        with open(path, "r") as f:
            config = json.load(f)
        return cls(config["secret"], config["keys"])

    def create_key_file(self, path: str, key_count: int = 1):
        # Generate a secret and at least one key:
        secret = secrets.token_urlsafe(32)
        keys = [secrets.token_urlsafe(32) for _ in range(key_count)]
        with open(path, "w") as f:
            json.dump({"secret": secret, "keys": keys}, f)
