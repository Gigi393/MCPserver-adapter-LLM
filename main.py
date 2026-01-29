"""
Main entrypoint for the py_mgipsim FastMCP server.

Run this file to start the MCP tool server:

    python main.py
"""

from fastMCP import mcp


def main() -> None:
    """Start the FastMCP server."""
    mcp.run()


if __name__ == "__main__":
    main()


