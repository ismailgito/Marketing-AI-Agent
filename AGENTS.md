# AGENTS.md

Voice agent "Jarvis" built on LiveKit Agents 1.8 + Gemini Live (speech-to-speech).
Python 3.12, Windows, uv-managed venv.

## Commands

```bash
uv sync                                  # install / repair deps (reads pyproject.toml + uv.lock)
uv run agent.py console                  # talk to the agent locally (no room needed)
uv run agent.py dev                      # registers worker "my-agent" against LiveKit Cloud
uv run agent.py download-files           # prewarm plugin models
uvx --from pyright pyright --pythonpath .venv/Scripts/python.exe .   # typecheck
```

`.venv` has **no pip**. Never run `pip install`; use `uv add` / `uv sync`.
`requirements.txt` is a stale duplicate that nothing reads — editing it changes nothing.
`pyproject.toml` + `uv.lock` are the only source of truth.

## Architecture worth knowing

- Single entrypoint: `agent.py`. Module-level `server = AgentServer()`, `@server.rtc_session(agent_name="my-agent")`.
- **Realtime speech-to-speech.** `AgentSession` is constructed in the entrypoint with `inference.RealtimeModel(model="google/gemini-3.8-live", voice="Puck")`. There is no STT, TTS, VAD, or separate LLM. Do not add them unless asked.
- `Assistant` holds only instructions + `tools=[...]`. The model lives on the session, not the agent — a deliberate split.
- Two tool sources land in the same `tools=[...]` list and are indistinguishable at runtime:
  - `skills/*.py` → in-process `@function_tool` (fast)
  - `agent_mcp/*.py` → `mcp.MCPToolset` wrapping a remote HTTP server (network latency)
- Only `get_livekit_docs_toolset()` is attached. `get_custom_api_toolset()` (placeholder URL) and `get_filesystem_toolset()` are defined but **not wired in** — they are templates, not live features.

## Traps that have already bitten

- **Never rename `agent_mcp/` back to `mcp/`.** It shadows the PyPI `mcp` SDK and makes `livekit.agents` fail with `ModuleNotFoundError: No module named 'mcp.types'` raised from *inside* site-packages. The traceback points at LiveKit, not at your folder. Same rule for any new top-level package name.
- **Env file is `.env.local`, not `.env`** — loaded explicitly via `load_dotenv(BASE_DIR / ".env.local")`. New env vars go there.
- **Gemini Live routes through LiveKit Inference**, so it authenticates with `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET`. `GOOGLE_API_KEY` is present in `.env.local` but unused on this path; that is not a bug.
- `ai_coustics.audio_enhancement()` also defaults to LiveKit Cloud auth (same two env vars).
- **`get_current_time` is broken on Windows**: `ZoneInfo("Asia/Kolkata")` raises `ZoneInfoNotFoundError` because `tzdata` is not installed. Fix with `uv add tzdata`, not by rewriting the tool.
- `@function_tool` returns a `FunctionTool` object, not a function. To call one directly: `await tool._func(...)`.
- `utils.http_context.http_session()` raises outside a job context. Wrap standalone calls in `async with utils.http_context.open():`.
- **MCP specifics:**
  - Docs server URL must be `https://docs.livekit.io/mcp` (a bare `https://livekit.io` connects to nothing useful).
  - `MCPServerHTTP` accepts `allowed_tools`; `MCPServerStdio` does **not** — stdio servers expose every tool.
  - Default `client_session_timeout_seconds=5` is too short for `npx` cold start on Windows. Use `60` for any stdio server.
  - `get_filesystem_toolset()` points at `C:\Users\Lenovo\Documents\Jarvis\agent_data`, which does not exist.

## Conventions

- Assistant instructions are spoken aloud: no markdown, asterisks, or emojis in replies. Keep this constraint when editing the prompt.
- Notes persist to `data/notes.json` (project-relative, created on demand).
- Keep voice replies short; depth only on request.

## Testing status

No tests exist and `pytest` is not installed. If you add the LiveKit turn-level harness:

- `uv add --dev pytest pytest-asyncio`
- `AgentSession(llm=<text model>)` in tests substitutes a text LLM for Gemini Live, so it verifies tool selection and instructions — **not** the audio pipeline.
- `mock_tools` intercepts tool *execution* by name (works for MCP tools too) but does **not** prevent `MCPToolset.setup()` from opening a real network connection during `session.start()`. Tests are network-dependent unless you gate the MCP toolset behind an env flag.
