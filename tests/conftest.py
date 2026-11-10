"""Shared fixtures. Everything here is offline unless a test is explicitly marked."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import skills.notes_skills as notes_skills  # noqa: E402
import skills.web_skills as web_skills  # noqa: E402


@pytest.fixture
def notes_file(tmp_path, monkeypatch) -> Path:
    """Point the notes tools at a throwaway file; the real data/notes.json is never touched."""
    path = tmp_path / "data" / "notes.json"
    monkeypatch.setattr(notes_skills, "NOTES_FILE", path)
    return path


@pytest.fixture
def allow_loopback(monkeypatch):
    """Let the web tool reach the local test server. Other private ranges stay blocked."""
    original = web_skills._is_public_ip

    def _allow(raw: str) -> bool:
        return raw in ("127.0.0.1", "::1") or original(raw)

    monkeypatch.setattr(web_skills, "_is_public_ip", _allow)


async def call(tool, *args, **kwargs):
    """@function_tool returns a FunctionTool object; the real coroutine lives on ._func."""
    return await tool._func(*args, **kwargs)
