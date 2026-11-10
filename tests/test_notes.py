import asyncio
import json

import pytest
from livekit.agents.llm import ToolError

import skills.notes_skills as ns
from skills.notes_skills import list_notes, save_note
from tests.conftest import call


async def test_list_when_file_missing(notes_file):
    assert "don't have any saved notes" in await call(list_notes)


async def test_save_then_list_roundtrip_and_unicode(notes_file):
    await call(save_note, "hello world")
    await call(save_note, "नमस्ते ☕")
    out = await call(list_notes)
    assert out == "1. hello world\n2. नमस्ते ☕"
    # stored readable, not \u-escaped
    assert "नमस्ते" in notes_file.read_text(encoding="utf-8")


# ---- BUG-01 / BUG-15: never destroy data -------------------------------------------------

@pytest.mark.parametrize(
    "raw",
    [b"{not json", b"", b"\xff\xfe\x00garbage", b'{"a": 1}', b'"a string"', b'[{"foo": 1}]', b"[1, 2]"],
    ids=["invalid-json", "zero-byte", "bad-bytes", "dict-root", "str-root", "missing-text", "non-dict-items"],
)
async def test_corrupt_file_is_backed_up_not_overwritten(notes_file, raw):
    notes_file.parent.mkdir(parents=True)
    notes_file.write_bytes(raw)

    assert "corrupted" in await call(list_notes)          # list never crashes, never mutates
    assert notes_file.read_bytes() == raw

    reply = await call(save_note, "fresh note")           # save never crashes
    assert "backup" in reply
    backups = list(notes_file.parent.glob("notes.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == raw                 # original bytes preserved exactly
    assert json.loads(notes_file.read_text(encoding="utf-8")) == [{"text": "fresh note"}]


async def test_bom_file_is_read_normally(notes_file):
    notes_file.parent.mkdir(parents=True)
    notes_file.write_bytes(b"\xef\xbb\xbf" + json.dumps([{"text": "from notepad"}]).encode())
    assert await call(list_notes) == "1. from notepad"
    await call(save_note, "second")
    assert not list(notes_file.parent.glob("*.corrupt-*"))   # a BOM is not corruption
    assert (await call(list_notes)).splitlines() == ["1. from notepad", "2. second"]


async def test_write_is_atomic_no_temp_files_left(notes_file):
    await call(save_note, "one")
    assert [p.name for p in notes_file.parent.iterdir()] == ["notes.json"]


async def test_failed_write_leaves_original_intact(notes_file, monkeypatch):
    await call(save_note, "keep me")
    before = notes_file.read_bytes()

    def boom(*_a, **_k):
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(ns.os, "replace", boom)
        with pytest.raises(OSError):
            await call(save_note, "will fail")
    assert notes_file.read_bytes() == before
    assert [p.name for p in notes_file.parent.iterdir()] == ["notes.json"]  # temp cleaned up


async def test_concurrent_saves_lose_nothing(notes_file):
    await asyncio.gather(*(call(save_note, f"n{i}") for i in range(50)))
    assert len(json.loads(notes_file.read_text(encoding="utf-8"))) == 50


# ---- BUG-11: limits ----------------------------------------------------------------------

@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
async def test_blank_note_rejected(notes_file, text):
    with pytest.raises(ToolError, match="empty"):
        await call(save_note, text)
    assert not notes_file.exists()


async def test_overlong_note_rejected(notes_file):
    with pytest.raises(ToolError, match="too long"):
        await call(save_note, "x" * (ns.MAX_NOTE_CHARS + 1))
    await call(save_note, "x" * ns.MAX_NOTE_CHARS)  # boundary is allowed


async def test_note_text_is_stripped(notes_file):
    await call(save_note, "  padded  ")
    assert json.loads(notes_file.read_text(encoding="utf-8")) == [{"text": "padded"}]


async def test_list_returns_only_latest_n_with_absolute_numbers(notes_file):
    for i in range(1, 9):
        await call(save_note, f"note {i}")
    out = await call(list_notes)
    lines = out.splitlines()
    assert lines[0] == "Showing the latest 5 of 8 notes."
    assert lines[1:] == [f"{i}. note {i}" for i in range(4, 9)]
    assert (await call(list_notes, limit=2)).splitlines()[1:] == ["7. note 7", "8. note 8"]


@pytest.mark.parametrize("limit", [0, -5, 10_000])
async def test_list_limit_is_clamped(notes_file, limit):
    for i in range(30):
        await call(save_note, f"n{i}")
    lines = (await call(list_notes, limit=limit)).splitlines()
    assert 2 <= len(lines) <= 21  # header + between 1 and 20 notes
