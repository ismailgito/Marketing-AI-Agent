# Customizing Jarvis Voice Agent

A comprehensive guide to adding skills, MCP servers, system instructions, RAG, and personalizing this voice agent.

## Project Layout

```
agent.py                  # Entrypoint: AgentServer + Assistant class (instructions + tools live here)
skills/                   # Local in-process tools (fast, no network)
  time_skills.py          # get_current_time  (@function_tool)
  notes_skills.py         # save_note, list_notes  (@function_tool, writes to data/notes.json)
  web_skills.py           # get_webpage_title  (@function_tool, aiohttp)
agent_mcp/                # MCP server wrappers (network latency)
  servers.py              # Server configs: HTTP (remote URL + headers), Stdio (npx)
  toolsets.py             # Wraps servers into MCPToolset objects
.env.local                # All secrets (LIVEKIT_API_KEY, etc.)
data/                     # Runtime data (notes.json, RAG docs)
```

---

## 1. Adding / Removing Skills (Local Tools)

A "skill" is a Python file in `skills/` containing one or more `@function_tool`-decorated functions. They run in-process, require no external server, and are fast.

### Adding a new skill

Create `skills/weather_skills.py`:

```python
import os
import aiohttp
from livekit.agents import function_tool, utils
from livekit.agents.llm import ToolError

@function_tool
async def get_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: The city name, e.g. 'London'.
    """
    session = utils.http_context.http_session()
    api_key = os.environ["OPENWEATHER_API_KEY"]
    async with session.get(
        f"https://api.openweathermap.org/data/2.5/weather",
        params={"q": city, "appid": api_key, "units": "metric"},
        timeout=aiohttp.ClientTimeout(total=10),
    ) as resp:
        if resp.status != 200:
            raise ToolError(f"Weather API returned {resp.status}")
        data = await resp.json()
        return f"{city}: {data['main']['temp']}°C, {data['weather'][0]['description']}"
```

Then wire it into `agent.py`:

```python
from skills.weather_skills import get_weather

class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""
            ...
            - Use get_weather for questions about the weather.
            """,
            tools=[
                get_current_time,
                save_note,
                list_notes,
                get_webpage_title,
                get_weather,                      # <-- add here
                # the docs toolset is appended conditionally in agent.py (see Assistant.__init__)
            ],
        )
```

### Removing a skill

Delete the import line, remove the entry from `tools=[...]`, and optionally delete the file. The model will stop seeing that tool.

### Key rules

- `@function_tool` returns a `FunctionTool` object, not a function — always pass the bare name into `tools=[...]`.
- Docstrings on the tool function become the tool's description that the model sees. Write them clearly; they're the model's only clue about when to call the tool.
- To call a tool directly in your own code: `await tool._func(...)`.

---

## 2. Adding / Removing MCP Servers (URLs and APIs)

MCP (Model Context Protocol) servers expose tools over HTTP or stdio. Configuration spans two files.

### `agent_mcp/servers.py` — define server connections

```python
def get_weather_mcp_server() -> mcp.MCPServerHTTP:
    """A remote MCP server exposing weather tools."""
    return mcp.MCPServerHTTP(
        url="https://mcp.weather.example.com",
        transport_type="streamable_http",
        allowed_tools=["get_forecast", "get_alerts"],   # optional filter
        headers={
            "Authorization": f"Bearer {os.environ.get('WEATHER_MCP_API_KEY', '')}",
        },
    )

def get_local_kb_server() -> mcp.MCPServerStdio:
    """A local knowledge-base MCP server."""
    return mcp.MCPServerStdio(
        command="python",
        args=["-m", "my_kb_server", "--index", "data/kb"],
        client_session_timeout_seconds=60,   # stdio cold-start on Windows needs this
    )
```

### `agent_mcp/toolsets.py` — wrap servers into toolsets

```python
def get_weather_toolset() -> mcp.MCPToolset:
    return mcp.MCPToolset(
        id="weather",
        mcp_server=get_weather_mcp_server(),
    )
```

### `agent.py` — attach the toolset

```python
from agent_mcp.toolsets import get_weather_toolset

# in Assistant.__init__, next to where docs_toolset is appended:
tools.append(get_weather_toolset())      # <-- add
```

If the server can be down, connect it first like `connect_docs_toolset()` does in `agent.py`
and only attach it (and mention it in the prompt) when `setup()` succeeded. The SDK swallows
toolset setup errors, so otherwise the model keeps being told about tools it doesn't have.

### Removing an MCP toolset

Remove the import and the `tools.append(...)` call, and any mention of its tools in the prompt.

### MCP traps

- `MCPServerHTTP` accepts `allowed_tools`; `MCPServerStdio` does **not** — stdio servers expose every tool.
- Default `client_session_timeout_seconds=5` is too short for `npx` cold start on Windows. Bump to `60` for any stdio server.
- The docs server URL must be `https://docs.livekit.io/mcp` — a bare `https://livekit.io` connects to nothing useful.
- **Never rename `agent_mcp/` back to `mcp/`** — it shadows the PyPI `mcp` SDK and breaks LiveKit with a confusing traceback.

---

## 3. System Instructions

The system instructions live in `BASE_INSTRUCTIONS` in `agent.py` (built by `build_instructions()`, which adds the docs-tools line only when the docs MCP server really connected). They are spoken aloud, so follow these constraints:

- **No markdown, asterisks, or emojis** in replies.
- Keep voice replies short; depth only on request.

### Example — personal AI assistant persona

```python
instructions="""
You are Atlas, my personal voice assistant. You are helpful, warm, and concise.

You have access to my personal tools:
- Use get_current_time for questions about the current date or time (IST).
- Use save_note and list_notes to store and recall personal notes and tasks.
- Use get_webpage_title when I give you a link.
- Use get_weather for weather questions.
- Use livekit_docs for LiveKit technical questions.

Behavior rules:
- Remember I'm in India (IST timezone).
- If a note sounds like a reminder, acknowledge the time explicitly.
- When unsure which tool to use, ask a quick clarifying question instead of guessing.
- Speak naturally and conversationally. Keep responses short unless I ask for detail.
""",
```

### Split instructions into a file

Create `instructions/atlas.txt` and load it:

```python
instructions=Path(__file__).resolve().parent.joinpath("instructions", "atlas.txt").read_text(),
```

---

## 4. RAG (Retrieval-Augmented Generation)

This project has **no RAG wired in yet**, but there are two clean ways to add it.

### Option A — Build an MCP RAG server (recommended)

Create a small Python MCP server that owns your knowledge base:

```python
# agent_mcp/rag_server.py  (run as: python -m agent_mcp.rag_server)
import os
from mcp.server.fastmcp import FastMCP
import chromadb
from chromadb.utils import embedding_functions

mcp = FastMCP("personal-kb")

client = chromadb.PersistentClient(path="data/chroma")
collection = client.get_or_create_collection(
    name="jarvis_kb",
    embedding_function=embedding_functions.DefaultEmbeddingFunction(),
)

@mcp.tool()
def search_knowledge(query: str, n_results: int = 3) -> str:
    """Search my personal knowledge base for relevant context."""
    results = collection.query(query_texts=[query], n_results=n_results)
    docs = results.get("documents", [[]])[0]
    return "\n---\n".join(docs) if docs else "No relevant context found."
```

Wire it in via `agent_mcp/servers.py` + `toolsets.py`:

```python
# servers.py
def get_rag_server() -> mcp.MCPServerStdio:
    return mcp.MCPServerStdio(
        command="python",
        args=["-m", "agent_mcp.rag_server"],
        client_session_timeout_seconds=60,
    )

# toolsets.py
def get_rag_toolset() -> mcp.MCPToolset:
    return mcp.MCPToolset(id="personal_kb", mcp_server=get_rag_server())
```

```python
# agent.py
from agent_mcp.toolsets import get_rag_toolset
tools.append(get_rag_toolset())   # in Assistant.__init__
```

### Ingest documents

Create `scripts/ingest_kb.py`:

```python
import chromadb, glob
from pathlib import Path
from chromadb.utils import embedding_functions

client = chromadb.PersistentClient(path="data/chroma")
col = client.get_or_create_collection("jarvis_kb", embedding_function=embedding_functions.DefaultEmbeddingFunction())

for path in glob.glob("data/kb/**/*.md", recursive=True):
    text = Path(path).read_text(encoding="utf-8")
    col.add(documents=[text], ids=[path], metadatas=[{"source": path}])
```

Run whenever your knowledge changes:

```bash
python scripts/ingest_kb.py
```

### Option B — In-process RAG via a `@function_tool`

Put the RAG logic directly in a skill file and expose it as a single `@function_tool`. Same embedding/chroma logic, wrapped in a function the model calls as `search_knowledge`.

### Dependencies

Use `uv add`, never `pip install`:

```bash
uv add chromadb
```

---

## 5. Customizing as a Personal AI Assistant — Checklist

| Area | What to change | Where |
|---|---|---|
| Identity & persona | Name, tone, rules | `instructions=` in `agent.py` |
| Timezone | `ZoneInfo("Asia/Kolkata")` → your zone | `skills/time_skills.py` |
| Persistent memory | Notes already persist to `data/notes.json` | `skills/notes_skills.py` |
| Knowledge base (RAG) | Add MCP RAG server + ingest script | `agent_mcp/`, `scripts/` |
| External APIs | Weather, email, calendar, etc. | New `skills/*.py` (local) or `agent_mcp/` (MCP) |
| Voice | `voice="Puck"` → other Gemini voices | `my_agent()` in `agent.py` (`voice=`) |
| Model | `model="google/gemini-3.8-live"` | `my_agent()` in `agent.py` (`model=`) |
| Secrets | API keys | `.env.local` |
| Audio | Noise cancellation model | `my_agent()` in `agent.py` (`noise_cancellation=`) |
| Deployment | Register worker against LiveKit Cloud | `uv run agent.py dev` |

---

## Environment Variables

All config goes in `.env.local` (not `.env`). Already used:

```
LIVEKIT_API_KEY=...        # LiveKit Cloud auth (Gemini Live routes through LiveKit Inference)
LIVEKIT_API_SECRET=...     # Same auth
GOOGLE_API_KEY=...         # Present but unused on the Gemini Live path (not a bug)
```

Add your own, e.g.:

```
OPENWEATHER_API_KEY=...
MY_MCP_SERVER_URL=...      # used by get_authenticated_mcp_server()
MY_MCP_API_KEY=...         # same; both are required, the function raises if either is empty
AGENT_DATA_DIR=...         # optional: folder for the filesystem MCP server
```

Read required keys with `os.environ["..."]` or fail loudly like `get_authenticated_mcp_server()` does, rather than sending an empty value.

---

## Running It

```bash
uv sync                                  # install/repair deps
uv run agent.py console                  # talk locally, no room needed
uv run agent.py dev                      # register worker "my-agent" on LiveKit Cloud
uv run pytest -q                         # offline tests; see AGENTS.md for the other suites
```

---

## Recommended Next Steps for a Personal Assistant

1. **Rename the persona** — change `instructions=` to your name/tone.
2. **Set your timezone** — `skills/time_skills.py` is hard-coded to `Asia/Kolkata`. `tzdata` is already a dependency, so any IANA zone works on Windows.
3. **Add a calendar/email skill** — either as a `@function_tool` hitting your provider's API, or as an MCP server if the provider offers one.
4. **Set up RAG** — ingest your notes, docs, and transcripts into Chroma and expose `search_knowledge`.
5. **Wire in the filesystem toolset** — `get_filesystem_toolset()` is defined but not attached. It serves `AGENT_DATA_DIR` (default `data/agent_data/`, created automatically); add it to `tools=[...]` in `Assistant.__init__` to let the agent read/write files there. Remember stdio servers expose every tool, so keep the folder narrow.
