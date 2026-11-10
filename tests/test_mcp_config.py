"""MCP wiring tests. Offline by default; the live check needs RUN_NETWORK_TESTS=1."""
import os

import pytest

import agent
from agent_mcp import servers
from agent_mcp.toolsets import get_livekit_docs_toolset


def test_docs_server_exposes_only_the_allow_list():
    server = servers.get_livekit_docs_server()
    assert server._allowed_tools == set(servers.LIVEKIT_DOCS_ALLOWED_TOOLS)


def test_docs_allow_list_has_no_outbound_write_tools():
    assert "submit_docs_feedback" not in servers.LIVEKIT_DOCS_ALLOWED_TOOLS


def test_docs_server_url_and_timeouts():
    server = servers.get_livekit_docs_server()
    assert server.url == "https://docs.livekit.io/mcp"  # a bare livekit.io connects to nothing
    assert server._timeout >= 10 and server._read_timeout >= 10


def test_stdio_filesystem_server_has_long_timeout_and_creates_folder(tmp_path):
    folder = tmp_path / "agent_data"
    server = servers.get_local_filesystem_server(folder)
    assert folder.is_dir()
    assert server._read_timeout == 60  # npx cold start on Windows
    assert str(folder) in server.args


def test_filesystem_folder_comes_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path / "custom"))
    assert servers.get_agent_data_dir() == tmp_path / "custom"
    monkeypatch.delenv("AGENT_DATA_DIR")
    assert servers.get_agent_data_dir() == servers.PROJECT_ROOT / "data" / "agent_data"


@pytest.mark.parametrize("missing", ["MY_MCP_SERVER_URL", "MY_MCP_API_KEY"])
def test_authenticated_server_fails_fast_without_env(monkeypatch, missing):
    monkeypatch.setenv("MY_MCP_SERVER_URL", "https://mcp.example.com")
    monkeypatch.setenv("MY_MCP_API_KEY", "token")
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match=missing):
        servers.get_authenticated_mcp_server()


def test_authenticated_server_sends_bearer_token(monkeypatch):
    monkeypatch.setenv("MY_MCP_SERVER_URL", "https://mcp.example.com")
    monkeypatch.setenv("MY_MCP_API_KEY", "s3cret")
    server = servers.get_authenticated_mcp_server(allowed_tools=["a"])
    assert server._headers == {"Authorization": "Bearer s3cret"}
    assert server._allowed_tools == {"a"}


# ---- BUG-08: prompt must match what is actually attached ----------------------------------

def test_prompt_mentions_docs_only_when_attached():
    with_docs = agent.build_instructions(has_docs=True)
    without = agent.build_instructions(has_docs=False)
    assert "docs_search" in with_docs and "docs_search" not in without
    assert "livekit_docs" not in with_docs  # a toolset id, not a tool name
    assert "{" not in with_docs and "{" not in without  # no unfilled placeholder


def test_assistant_tool_list_follows_toolset():
    base = agent.Assistant()
    assert [getattr(t, "id", None) for t in base.tools] == [
        "get_current_time", "save_note", "list_notes", "get_webpage_title",
    ]
    attached = agent.Assistant(docs_toolset=get_livekit_docs_toolset())
    assert [getattr(t, "id", None) for t in attached.tools][-1] == "livekit_docs"
    assert "docs_search" in str(attached.instructions)


async def test_dead_docs_server_degrades_gracefully(monkeypatch, caplog):
    class _Dead:
        closed = False

        async def setup(self):
            raise ConnectionError("docs.livekit.io unreachable")

        async def aclose(self):
            self.closed = True

    dead = _Dead()
    monkeypatch.setattr(agent, "get_livekit_docs_toolset", lambda: dead)
    with caplog.at_level("WARNING", logger="jarvis.agent"):
        assert await agent.connect_docs_toolset() is None
    assert dead.closed
    assert "continuing without docs tools" in caplog.text


async def test_hung_docs_server_times_out(monkeypatch):
    import asyncio

    class _Hung:
        async def setup(self):
            await asyncio.sleep(60)

        async def aclose(self):
            pass

    monkeypatch.setattr(agent, "get_livekit_docs_toolset", lambda: _Hung())
    monkeypatch.setattr(agent, "DOCS_SETUP_TIMEOUT_SECONDS", 0.2)
    assert await agent.connect_docs_toolset() is None


@pytest.mark.skipif(os.environ.get("RUN_NETWORK_TESTS") != "1", reason="set RUN_NETWORK_TESTS=1")
async def test_live_docs_server_matches_allow_list():
    toolset = await agent.connect_docs_toolset()
    assert toolset is not None
    try:
        names = {t.id for t in toolset.tools}
        assert names and names <= set(servers.LIVEKIT_DOCS_ALLOWED_TOOLS)
        assert "submit_docs_feedback" not in names
    finally:
        await toolset.aclose()
