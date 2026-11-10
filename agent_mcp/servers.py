import os
from pathlib import Path

from livekit.agents import mcp

# Read-only documentation tools only. The docs server also offers
# `submit_docs_feedback` (an outbound write to a third party); the model must
# not be able to call it unprompted, so the allow-list is explicit.
LIVEKIT_DOCS_ALLOWED_TOOLS: list[str] = [
    "docs_search",
    "code_search",
    "get_docs_overview",
    "get_pages",
    "get_changelog",
    "get_python_agent_example",
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_livekit_docs_server() -> mcp.MCPServerHTTP:
    """Connect to LiveKit's public documentation MCP server (read-only tools)."""
    return mcp.MCPServerHTTP(
        url="https://docs.livekit.io/mcp",
        transport_type="streamable_http",
        allowed_tools=LIVEKIT_DOCS_ALLOWED_TOOLS,
        timeout=10,
        client_session_timeout_seconds=10,
    )


def get_authenticated_mcp_server(
    allowed_tools: list[str] | None = None,
) -> mcp.MCPServerHTTP:
    """Example configuration for a remote HTTP MCP server requiring an API token.

    Reads MY_MCP_SERVER_URL and MY_MCP_API_KEY from the environment and fails
    fast if either is missing, instead of sending an empty bearer token.
    """
    url = os.environ.get("MY_MCP_SERVER_URL", "").strip()
    token = os.environ.get("MY_MCP_API_KEY", "").strip()
    if not url:
        raise RuntimeError("MY_MCP_SERVER_URL is not set (add it to .env.local).")
    if not token:
        raise RuntimeError("MY_MCP_API_KEY is not set (add it to .env.local).")

    return mcp.MCPServerHTTP(
        url=url,
        transport_type="streamable_http",
        allowed_tools=allowed_tools,
        headers={"Authorization": f"Bearer {token}"},
    )


def get_agent_data_dir() -> Path:
    """Folder exposed to the filesystem MCP server. AGENT_DATA_DIR overrides the default."""
    configured = os.environ.get("AGENT_DATA_DIR", "").strip()
    return Path(configured) if configured else PROJECT_ROOT / "data" / "agent_data"


def get_local_filesystem_server(allowed_folder: str | Path | None = None) -> mcp.MCPServerStdio:
    """Run a local filesystem MCP server over stdio confined to a safe directory.

    stdio servers expose every tool (no allowed_tools support), so keep the
    folder narrow. `npx` cold starts on Windows exceed the 5 s default, hence 60.
    """
    folder = Path(allowed_folder) if allowed_folder else get_agent_data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    return mcp.MCPServerStdio(
        command="npx",
        args=[
            "-y",
            "@modelcontextprotocol/server-filesystem",
            str(folder),
        ],
        client_session_timeout_seconds=60,
    )
