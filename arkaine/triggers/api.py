import json
from typing import List, Optional, Union

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from arkaine.tools.tool import Context, Tool


class ToolAPI(FastAPI):
    """
    A FastAPI-based server for arkAIne tools.

    This class extends FastAPI to create a server that exposes arkAIne Tools as
    endpoints, preserving tool metadata and supporting various input methods.
    """

    def __init__(
        self,
        tools: Union[Tool, List[Tool]],
        name: Optional[str] = None,
        description: Optional[str] = None,
        prefix: str = "/api",
        api_docs: str = "/api",
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
        name = name or self.tools[0].name
        description = description or "API generated from arkAIne tools"

        super().__init__(
            title=name,
            description=description,
            docs_url=api_docs,
        )

        self._prefix = prefix

        for tool in self.tools:
            self.add_tool_route(tool)

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

        for m in method:
            self.add_api_route(
                route,
                self.__create_endpoint_handler(tool),
                methods=[m],
                description=description,
            )

    def serve(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        http: bool = True,
        ws: bool = False,
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

            http: Enable HTTP protocol. Defaults to True.

            ws: Enable WebSocket protocol. Defaults to False.

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
        if not http and not ws:
            raise ValueError(
                "At least one protocol (HTTP or WebSocket) must be enabled"
            )

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
            http=http,
            ws=ws,
            ssl_keyfile=ssl_keyfile,
            ssl_certfile=ssl_certfile,
            ssl_keyfile_password=ssl_keyfile_password,
            reload=reload,
            workers=workers,
            log_level=log_level,
            proxy_headers=proxy_headers,
            forwarded_allow_ips=forwarded_allow_ips,
        )
