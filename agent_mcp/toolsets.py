from livekit.agents import mcp

from agent_mcp.servers import (
    get_authenticated_mcp_server,
    get_livekit_docs_server,
    get_local_filesystem_server,
)


def get_livekit_docs_toolset() -> mcp.MCPToolset:
    """Wraps the LiveKit Documentation MCP server tools for Jarvis."""
    return mcp.MCPToolset(
        id="livekit_docs",
        mcp_server=get_livekit_docs_server(),
    )


def get_custom_api_toolset() -> mcp.MCPToolset:
    """Wraps your remote custom API MCP server with allowed tools filter."""
    return mcp.MCPToolset(
        id="my_custom_api",
        mcp_server=get_authenticated_mcp_server(
            allowed_tools=[
                "search_documents",
                "get_document",
            ]
        ),
    )


def get_filesystem_toolset() -> mcp.MCPToolset:
    """Wraps the local filesystem node MCP server inside the agent data folder."""
    return mcp.MCPToolset(
        id="local_files",
        mcp_server=get_local_filesystem_server(),
    )
