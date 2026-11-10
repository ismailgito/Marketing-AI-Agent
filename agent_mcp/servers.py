import os
from livekit.agents import mcp # type: ignore

def get_livekit_docs_server() -> mcp.MCPServerHTTP:
    """Connect to LiveKit's public documentation MCP server."""
    return mcp.MCPServerHTTP(
        url="https://docs.livekit.io/mcp",
        transport_type="streamable_http",
    )

def get_authenticated_mcp_server(
    allowed_tools: list[str] | None = None,
) -> mcp.MCPServerHTTP:
    """Example configuration for a remote HTTP/SSE MCP server requiring an API token."""
    return mcp.MCPServerHTTP(
        url="https://your-mcp-server.com",
        transport_type="streamable_http",
        allowed_tools=allowed_tools,
        headers={
            "Authorization": f"Bearer {os.environ.get('MY_MCP_API_KEY', '')}"
        },
    )

def get_local_filesystem_server(allowed_folder: str) -> mcp.MCPServerStdio:
    """Run a local filesystem MCP server over stdio confined to a safe directory."""
    return mcp.MCPServerStdio(
        command="npx",
        args=[
            "-y",
            "@modelcontextprotocol/server-filesystem",
            allowed_folder,
        ],
    )
