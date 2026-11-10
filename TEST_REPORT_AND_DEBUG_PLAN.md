# Test Report & Debug Plan — Marketing-AI-Agent ("Jarvis")

**Date:** 2026-11-10  **Branch:** `main` (clean at start)  **Tester:** Claude Code
**Stack:** Python 3.12.14 · LiveKit Agents 1.8.11 · Gemini Live via LiveKit Inference · uv

> **Scope note.** `README.md` describes a *Marketing AI Agent* (ROAS, funnels, A/B tests, Meta/Google Ads connectors).
> The code, `AGENTS.md` and `CUSTOMIZATION.md` describe a *generic "Jarvis" voice assistant* with 4 demo tools plus the LiveKit docs MCP server.
> This report tests **the code as it exists** and treats the README as the *target product*. No project source was modified.

---

## 0. Execution status (updated after running the plan)

Work is on branch `fix/test-report-plan`, **uncommitted**. Phases 1–5 are done; Phase 6 waits on the Phase 0 decision.

| Phase | Status | Result |
|---|---|---|
| 0 Decide direction | **Open — needs you** | Marketing agent (README) or Jarvis scaffold? |
| 1 Data loss + exposure | Done | BUG-01/02/03/05/15 fixed |
| 2 Web tool | Done | BUG-06/07/09 fixed |
| 3 MCP reliability | Done | BUG-08/12 fixed |
| 4 Hygiene + docs | Done | BUG-10/11/13/14 fixed |
| 5 Test suite | Done | 98 tests: **93 pass, 5 skipped** (opt-in LLM tests) |
| 6 Align product | **Not started** | Blocked on Phase 0 |

**Verification:** `ruff` clean · `pyright` 0 errors · `pytest` 91 pass offline / 93 pass with `RUN_NETWORK_TESTS=1` (live docs MCP + live HTTPS). Against the *original* notes code, 19 of the 22 notes tests fail, so the tests detect the bugs. `data/notes.json` checksum unchanged throughout.

**Deviations from the plan above (be aware):**
- **BUG-09:** instead of moving `http_session()` inside the `try`, the web tool now owns its own `aiohttp` session. That is required for the SSRF guard (a custom resolver validates every connection and redirect hop) and removes the "outside a job context" trap for this tool.
- **New bug found during live verification, fixed:** after the rewrite, `https://example.com` failed with `unable to get local issuer certificate` (Windows trust store lacks newer CA chains; LiveKit's own session adds `certifi`). Added `certifi` to the SSL context and as a declared dependency, plus a regression test. Unit tests alone did not catch this; only the real network did.
- **BUG-15:** notes writes are now atomic and serialised in-process; I did **not** add a cross-process file lock. Two job processes can still lose an update (never a torn file).
- **Dropped the `google` extra** from `livekit-agents` and removed `chromadb`, `requirements.txt`. Imports, CLI and all tests still work.
- `ruff format` is **not** enforced (it would rewrite ~10 files incl. the GIF script); only `ruff check` runs in CI.

**Not verified (still open):**
- `tests/test_agent_turns.py` (5 real-model tests) was written from the current LiveKit docs but **never executed**: it would send prompts through your LiveKit Inference account. Run `RUN_LLM_TESTS=1 uv run pytest tests/test_agent_turns.py -s` once and expect to adjust model/assertions.
- No live voice session (`console` / `dev`) was run; the stdio filesystem MCP server (`npx`) was only constructed, never launched.
- `scripts/generate_readme_gifs.py` was linted/typechecked, not run.

---

## 1. Summary

| Area | Result |
|---|---|
| Compile / import (`compileall`, `import agent`) | PASS |
| Lockfile in sync (`uv sync --locked --dry-run`) | PASS |
| Model ID `google/gemini-3.8-live`, `EnhancerModel.QUAIL_VF_S`, `inference.RealtimeModel` | PASS (all exist in installed SDK) |
| `get_current_time` | PASS (tzdata is installed) |
| `save_note` / `list_notes` | **FAIL — 5 defects** (data loss, 3 crashes, no validation) |
| `get_webpage_title` | **FAIL — 6 defects** (parser, size, encoding, SSRF, errors) |
| LiveKit docs MCP toolset | Connects (1.6 s, 9 tools) — **2 defects** (over-exposed, silent failure) |
| Dormant MCP configs (`custom_api`, `filesystem`) | Not wired; **4 latent defects** |
| Secrets in git | PASS (`.env.local` ignored, never committed, no key patterns in tracked files) |
| Automated tests / CI | **None exist** |

**Totals: 15 findings — 4 High, 6 Medium, 5 Low.**

### Not tested (be aware of these gaps)
- Live voice session (`console` / `dev`): needs a microphone and LiveKit Cloud; I did not connect with your credentials.
- Real model tool-selection quality (needs the turn-level harness, see Phase 5).
- `pyright` typecheck (the `uvx` download was declined; `pyright` is not in `.venv`).
- stdio MCP server via `npx` (the target folder doesn't exist) and `scripts/generate_readme_gifs.py` (needs Pillow; only compiled, not run).
- Cross-process write races on `notes.json` (LiveKit runs one process per job).

---

## 2. Findings

Evidence tags: **[T]** reproduced by executing code · **[C]** confirmed by reading code/SDK source.

### High

#### BUG-01 — `save_note` silently destroys the notes file when it can't parse it  [T]
`skills/notes_skills.py:17-25`
- If `notes.json` is unparseable, `save_note` sets `notes = []`, overwrites the file, and replies *"I've saved that note"*. Every previous note is gone with no backup and no warning.
- Triggers reproduced: invalid JSON, 0-byte file, and a **UTF-8 BOM file** (what Windows Notepad / PowerShell `Set-Content` produce). `list_notes` reports "corrupted" for BOM files, and the next `save_note` wipes them.
- The write is also non-atomic (`write_text`), so a crash mid-write creates the corrupt file that the next save then erases.

#### BUG-02 — `get_webpage_title` fetches any URL the model is given (SSRF) and returns untrusted text  [T][C]
`skills/web_skills.py:13-32`
- No scheme/host allow-list. `http://127.0.0.1:…` was attempted and the connection error, including host and port, was returned to the model. On a cloud worker the same path reaches internal services and metadata endpoints (`169.254.169.254`). Redirects are followed (302 reproduced) with no re-check of the destination.
- The returned title is attacker-controlled text fed straight into a speech-to-speech model: a prompt-injection channel with no delimiting.

#### BUG-03 — Docs MCP toolset exposes all 9 tools, including an outbound write  [T]
`agent_mcp/servers.py:4-9`, `agent_mcp/toolsets.py:8-13`
- `get_livekit_docs_server()` passes no `allowed_tools`. Live tool list: `get_docs_overview, get_sdks, get_pages, docs_search, get_changelog, get_python_agent_example, get_pricing_info, submit_docs_feedback, code_search`.
- `submit_docs_feedback` sends data to a third party. The model can call it on its own mid-conversation. This contradicts the README guardrail "Read-only by default… whitelist with `allowed_tools`".

#### BUG-04 — Product and documentation disagree about what this project is  [C]
`README.md` vs `agent.py:27-39,74-76`, `AGENTS.md`, `CUSTOMIZATION.md`
- README promises 7 marketing skills, ad-platform connectors and guardrails (propose→confirm→apply, write log). **None exist in code.** README is honest about "planned", but its title, hero and skill table present them as the product.
- The live system prompt is a generic assistant; the opening line is *"say you are ready to test tools"* (dev scaffold text shipping as user-facing behaviour). The package is still named `livekit-gemini-agent`.
- Three docs (`README`, `AGENTS.md`, `CUSTOMIZATION.md`) each describe a different project identity (marketing analyst / Jarvis / "Atlas personal assistant").

### Medium

#### BUG-05 — `notes.json` shape errors crash the tools with uncaught exceptions  [T]
`skills/notes_skills.py:20,43-44`
| Input file | Result |
|---|---|
| `{}` | `save_note` → `AttributeError: 'dict' has no attribute 'append'` |
| `[{"foo":1}]` | `list_notes` → `KeyError: 'text'` |
| `"a string"` | `list_notes` → `TypeError: string indices must be integers` |

Only `JSONDecodeError` is handled; valid-JSON-wrong-shape is not.

#### BUG-06 — Title extraction is wrong for many real pages  [T]
`skills/web_skills.py:23-29`
| Page | Expected | Actual |
|---|---|---|
| `<TITLE>Upper</TITLE>` | `Upper` | "missing title" |
| `<title data-react-helmet="true">X</title>` (very common) | `X` | "missing title" |
| `Tom &amp; Jerry &#8211; Home` | `Tom & Jerry – Home` | entities returned raw |
| multi-line title | `Spaced Title` | `Spaced\n  Title` |
| inline `<svg><title>` before head | head title | SVG title |
| `<title></title>` | "no title" message | returns `''` (model says nothing) |

Hand-rolled `str.find` on raw HTML is the root cause.

#### BUG-07 — Response body is unbounded and encoding is brittle  [T]
`skills/web_skills.py:22`
- `response.text()` reads the whole body: a 50 MB page was read into memory. No `Content-Type` check, no byte cap.
- Non-UTF-8 pages (Latin-1 `Café`) and binary responses raise `UnicodeDecodeError`, reported as a network failure.

#### BUG-08 — A dead MCP server degrades silently and the prompt then lies  [C]
`livekit/agents/voice/agent_activity.py:1211-1216`, `agent.py:34`
- The SDK runs toolset `setup()` with `return_exceptions=True`, so if `docs.livekit.io/mcp` is down (or the 5 s default timeout trips) the session starts **without** the tools and only logs.
- The prompt still says *"Use livekit_docs…"*. `livekit_docs` is a toolset id, **not** a tool name (real names are `docs_search`, `code_search`, …), so even when healthy the instruction doesn't match what the model sees. With the tools missing, the model will answer LiveKit questions from memory.

#### BUG-09 — `get_webpage_title` error handling is misleading  [T]
`skills/web_skills.py:31-32`
- The `ToolError` raised for non-200 is caught by the blanket `except Exception` and re-wrapped: *"Network call execution failure during crawl process: Target site returned status code 404"*.
- Timeouts surface as an empty message (`str(TimeoutError)==''`), and scheme-less URLs as just the URL. The model gets nothing actionable to say aloud.
- `http_session()` is outside the `try`, so calling outside a job context raises `RuntimeError` (documented trap, but untestable without `utils.http_context.open()`).

#### BUG-10 — Documentation drift on `tzdata`  [T][C]
`AGENTS.md`, `CUSTOMIZATION.md` ("Fix the time tool — `uv add tzdata`")
- Both say `get_current_time` is broken on Windows. It **passes**: `tzdata 2026.6` is in `pyproject.toml` and installed. `README.md` already says it's resolved. A future contributor will chase a non-bug.

### Low

#### BUG-11 — Notes tools have no input/output limits  [T]
`save_note("")` is accepted ("saved ''"). `list_notes` returned all **1,000,007 characters** of a 1 MB note into the model context; a voice agent shouldn't read 200 notes aloud.

#### BUG-12 — Dormant MCP configs contain latent bugs  [T][C]
`agent_mcp/servers.py`, `agent_mcp/toolsets.py` (not wired in, so no runtime impact yet)
- `get_local_filesystem_server` omits `client_session_timeout_seconds=60`, which AGENTS.md calls mandatory for `npx` on Windows (default is 5).
- Hard-coded `C:\Users\Lenovo\Documents\Jarvis\agent_data` (doesn't exist, wrong project folder, not portable).
- `get_authenticated_mcp_server` sends `Authorization: Bearer ` (empty token) when `MY_MCP_API_KEY` is missing instead of failing fast.
- Placeholder URL fails with an opaque `ExceptionGroup: unhandled errors in a TaskGroup`.

#### BUG-13 — Dependency and file hygiene  [T][C]
- `chromadb` is declared (and locked) but **never imported**: dead weight and a large transitive tree.
- `aiohttp` is imported directly (`web_skills.py`) but not declared in `pyproject.toml`; it only works transitively. `pillow` (used by `scripts/`) is also undeclared.
- `livekit-agents[…google]` extra is unused on the LiveKit Inference path.
- `requirements.txt`: stale duplicate, saved with a UTF-8 BOM, pins differ in shape from `pyproject.toml`.
- `agent.py:1` has an unused `import os`. Blanket `# type: ignore` on SDK imports hides real type errors.

#### BUG-14 — No automated tests, lint config or CI  [C]
No `tests/`, no `pytest`, no ruff/pyright config, no CI. README roadmap lists tests as unchecked.

#### BUG-15 — Notes persistence is not safe across processes  [C]
LiveKit spawns one process per job; `notes.json` is shared with no lock or atomic replace. Single-process concurrency was fine (50/50 kept, because the sync IO never yields), but two simultaneous calls can lose updates or leave a torn file (feeds BUG-01).

### Verified OK
Compile · imports · lockfile · model ID and enhancer enum · `get_current_time` · notes happy path, Unicode, missing file, 0-byte file handling in `list_notes` · concurrent saves in one process · docs MCP connect · `.env.local` and `data/notes.json` ignored · no secrets in tracked files · `data/notes.json` untouched by this test run (checksum verified).

---

## 3. Debug & Fix Plan

Phases are ordered by risk. Each task lists files, the fix, and a done-when check. Estimated effort assumes one developer.

### Phase 0 — Decide direction (½ h, blocks Phase 6)
Decide what this repo is: **(A)** the Marketing agent in the README, or **(B)** a Jarvis scaffold. Everything in Phase 6 depends on it. Phases 1–5 are valid either way.

### Phase 1 — Stop data loss and unsafe exposure (High, ~3 h)

| # | Fixes | Change | Done when |
|---|---|---|---|
| 1.1 | BUG-01, 05, 15 | In `notes_skills.py`: read with `utf-8-sig`; validate `list[dict]` with a `text` str; on parse/shape failure **rename the file to `notes.json.corrupt-<timestamp>`** and tell the user; write via temp file + `os.replace`; wrap in `asyncio.Lock` and (optionally) a file lock for multi-process. | Tests: corrupt, BOM, `{}`, `"str"`, missing `text` → no crash, original bytes preserved in backup, tool says so. |
| 1.2 | BUG-03 | `get_livekit_docs_server()` → `allowed_tools=["docs_search","code_search","get_docs_overview","get_pages","get_changelog","get_python_agent_example"]`. Drop `submit_docs_feedback`, `get_pricing_info`/`get_sdks` unless wanted. | `toolset.tools` names exactly equal the allow-list (test). |
| 1.3 | BUG-02 | In `web_skills.py`: require `http`/`https`; resolve host and reject loopback, link-local, private, multicast and reserved IPs (re-check after each redirect, `max_redirects=3`); don't echo raw exception text. Wrap the returned title as plain data (strip control chars, cap ~200 chars) and tell the prompt that tool output is untrusted. | Tests for `127.0.0.1`, `169.254.169.254`, `10.x`, `file://`, redirect-to-private all return a short refusal. |

### Phase 2 — Make the web tool correct (Medium, ~3 h)

| # | Fixes | Change | Done when |
|---|---|---|---|
| 2.1 | BUG-06 | Replace `str.find` with a real parser (`html.parser.HTMLParser` or `selectolax`; stdlib is enough). Take the first `<title>` inside `<head>`, case-insensitive, `html.unescape`, collapse whitespace; empty → "page has no title". | All six BUG-06 rows pass. |
| 2.2 | BUG-07 | Stream with a cap (e.g. read ≤ 256 KB, stop at `</head>`); require `text/html`; decode with `response.get_encoding()` / `errors="replace"`. | 50 MB and binary responses return in <1 s with a clean message; Latin-1 decodes. |
| 2.3 | BUG-09 | Move `http_session()` inside the `try`; re-raise `ToolError` untouched (`except ToolError: raise`); map `asyncio.TimeoutError`, `ClientConnectorError`, `InvalidURL` to short spoken-friendly messages; auto-prefix `https://` for scheme-less input only if desired. | Error text for 404/timeout/bad URL is one clear sentence, no "crawl" wording, never empty. |

### Phase 3 — MCP reliability (Medium, ~2 h)

| # | Fixes | Change | Done when |
|---|---|---|---|
| 3.1 | BUG-08 | Fix prompt wording to the real tool names ("use docs_search / code_search for LiveKit questions"). Build instructions dynamically: include the docs line only if `toolset.setup()` succeeded. Raise `timeout`/`client_session_timeout_seconds` for the docs server and log a clear WARNING when setup fails. | With the URL pointed at a dead host, the session starts, the log has one clear warning, and the prompt has no docs line. |
| 3.2 | BUG-12 | Add `client_session_timeout_seconds=60` to the stdio server; take the folder from an env var (`AGENT_DATA_DIR`, default `./data/agent_data`) and create it; fail fast if `MY_MCP_API_KEY` is empty; read URLs from env. Or delete the unused templates until needed. | Functions import and construct without side effects; a missing key raises a clear error. |

### Phase 4 — Hygiene and docs (Low, ~2 h)

| # | Fixes | Change |
|---|---|---|
| 4.1 | BUG-13 | `uv remove chromadb` (re-add with RAG); `uv add aiohttp`; `uv add --dev pillow` or keep `--with`; drop the `google` extra if unused; delete `requirements.txt` (or regenerate with `uv export --no-hashes`); remove unused `import os`; narrow `# type: ignore` to specific codes. |
| 4.2 | BUG-10 | Remove the "tzdata broken" trap from `AGENTS.md` and the "Fix the time tool" step from `CUSTOMIZATION.md`. Re-verify each remaining "trap" claim before keeping it. |
| 4.3 | BUG-11 | Reject blank notes; `list_notes(limit=5)` returning the latest N with a "and N more" suffix; cap note length (e.g. 500 chars). |
| 4.4 | BUG-14 | Add `ruff` + `pyright` as dev deps and a `[tool.pyright]` section; add a GitHub Actions workflow running `uv sync --locked`, ruff, pyright, pytest. |

### Phase 5 — Test suite (the permanent regression net, ~4 h)

```bash
uv add --dev pytest pytest-asyncio
```
```
tests/
  conftest.py            # monkeypatch NOTES_FILE -> tmp_path; fixture wrapping utils.http_context.open()
  test_notes.py          # every row in BUG-01/05/11/15 + Unicode + BOM
  test_time.py           # IST format, tzdata present
  test_web.py            # local aiohttp fixture server: upper/attr/entity/multiline/svg/empty/latin1/binary/big/slow/redirect-to-private
  test_mcp_config.py     # allow-list == expected; stdio timeout == 60; no network
  test_agent_turns.py    # LiveKit turn harness (AgentSession with a text LLM): right tool chosen for
                         #   "what time is it", "save a note…", "title of <url>"; refuses private URLs.
                         #   Gate the real MCP toolset behind an env flag (it opens a network connection).
```
**Exit criteria:** `uv run pytest` green offline; each BUG-01…11 has at least one failing-before / passing-after test. Reuse the scripts I used for this report as a starting point (they exercised every table row above).

### Phase 6 — Align the product (depends on Phase 0)
- **If Marketing agent (A):** rename the package (`pyproject.toml` `name`), rewrite `instructions` and the greeting (drop "ready to test tools"), remove the LiveKit docs toolset from the user-facing agent (keep it for dev only), add the first real skill + read-only connector, and implement the README guardrails (read-only tokens, propose→confirm→apply, append-only write log) **before** any write-capable connector.
- **If Jarvis scaffold (B):** retitle the README as a scaffold, move the marketing roadmap to a `ROADMAP.md`, and make `AGENTS.md`/`CUSTOMIZATION.md`/`README.md` agree on one persona.
- Either way: keep **one** source of truth for traps (AGENTS.md) and link to it from the others.

---

## 4. Debug playbook (reproduce → verify)

```bash
uv sync --locked                          # env matches lockfile
uv run python -m compileall -q agent.py agent_mcp skills scripts
uv run pytest -q                          # after Phase 5

# Smoke-test a tool without a LiveKit job (note the context wrapper)
uv run python - <<'PY'
import asyncio
from livekit.agents import utils
from skills.web_skills import get_webpage_title
async def main():
    async with utils.http_context.open():
        print(await get_webpage_title._func("https://example.com"))
asyncio.run(main())
PY

uv run agent.py console                   # manual voice check (needs mic + LIVEKIT_* in .env.local)
```

| Symptom | First check |
|---|---|
| Agent never mentions LiveKit docs / answers vaguely | Log for MCP `setup()` failure (BUG-08); confirm tool names in `toolset.tools` |
| `ModuleNotFoundError: mcp.types` from inside site-packages | A top-level folder named `mcp/` exists (must stay `agent_mcp/`) |
| "Notes file appears corrupted" | Check `data/notes.json` for BOM / truncation; look for `*.corrupt-*` backup after Phase 1 |
| Tool raises `RuntimeError … outside of a job context` | Wrap in `utils.http_context.open()` |
| Worker online but no one connects | Explicit dispatch: worker is registered as `agent_name="my-agent"`; the room/dispatch rule must request it |

## 5. Suggested order of work
1. Phase 0 decision → 2. Phase 1 (data loss + exposure) → 3. Phase 5 test scaffold *(write the failing tests first)* → 4. Phases 2 & 3 → 5. Phase 4 → 6. Phase 6.

Total estimate: **~15 h** (≈ 2 working days) excluding Phase 6 product work.
