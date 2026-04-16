"""Unified entry point for MCP Database Server.

This module provides a single entry point that can run in either:
- STDIO mode: For use with MCP clients via stdio transport
- HTTP mode: For use with REST API and SSE MCP transport

Usage:
    # STDIO mode (default)
    python main.py

    # HTTP mode
    python main.py --http

    # HTTP mode with custom host/port
    python main.py --http --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
import os
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_stdio_mode():
    """Run MCP server in STDIO mode.

    This mode is used for direct MCP client communication via stdio transport.
    Typically used when the server is spawned as a subprocess by an MCP client.
    """
    logger.info("Starting MCP FDA Server in STDIO mode")

    from protocol.stdio_server import run_stdio_server
    try:
        await run_stdio_server()
    except Exception as e:
        logger.error(f"STDIO server error: {e}", exc_info=True)
        sys.exit(1)


def run_http_mode(host: str = "0.0.0.0", port: int = 8000):
    """Run MCP server in HTTP mode with REST API and SSE support."""
    logger.info(f"Starting MCP FDA Server in HTTP mode on {host}:{port}")

    from http_server import run_http_server
    run_http_server(host, port)


def main():
    """Main entry point with argument parsing."""
    import argparse

    parser = argparse.ArgumentParser(
        description="MCP Database Server - Unified Entry Point"
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run in HTTP mode (default: STDIO mode)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host address for HTTP mode (default: from HTTP_HOST env or 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port for HTTP mode (default: from HTTP_PORT env or 8000)"
    )

    args = parser.parse_args()

    if args.http:
        # HTTP mode
        host = args.host or os.getenv("HTTP_HOST", "0.0.0.0")
        port = args.port or int(os.getenv("HTTP_PORT", "8000"))
        run_http_mode(host, port)
    else:
        # STDIO mode (default)
        asyncio.run(run_stdio_mode())


if __name__ == "__main__":
    main()
