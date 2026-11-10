import asyncio
import json
import logging
import os
import tempfile
import time
from pathlib import Path

from livekit.agents import function_tool
from livekit.agents.llm import ToolError

logger = logging.getLogger("jarvis.notes")

# Resolve relative to the project root so the file is found regardless of CWD.
NOTES_FILE = Path(__file__).resolve().parent.parent / "data" / "notes.json"

MAX_NOTE_CHARS = 500
DEFAULT_LIST_LIMIT = 5

# Serialises read-modify-write cycles inside one worker process. Separate job
# processes can still interleave; the atomic replace below guarantees they can
# lose an update but never leave a torn file.
_lock = asyncio.Lock()


class _CorruptNotesError(Exception):
    """notes.json exists but is not a list of {"text": str} objects."""


def _load_notes() -> list[dict]:
    """Return stored notes, [] if the file doesn't exist yet.

    Raises _CorruptNotesError for anything that is not a list of dicts whose
    "text" is a string. Reads with utf-8-sig so a BOM (Notepad, PowerShell
    Set-Content) doesn't make a healthy file look corrupt.
    """
    if not NOTES_FILE.exists():
        return []
    try:
        data = json.loads(NOTES_FILE.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise _CorruptNotesError(str(error)) from error

    if not isinstance(data, list) or not all(
        isinstance(item, dict) and isinstance(item.get("text"), str) for item in data
    ):
        raise _CorruptNotesError("notes file does not contain a list of notes")
    return data


def _quarantine_corrupt_file() -> Path:
    """Move the unreadable file aside so nothing is ever silently overwritten."""
    backup = NOTES_FILE.with_name(f"{NOTES_FILE.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}")
    counter = 1
    while backup.exists():
        backup = NOTES_FILE.with_name(
            f"{NOTES_FILE.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}-{counter}"
        )
        counter += 1
    os.replace(NOTES_FILE, backup)
    logger.warning("notes file was unreadable; moved to %s", backup)
    return backup


def _write_atomic(notes: list[dict]) -> None:
    """Write to a temp file in the same directory, then atomically replace."""
    NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=NOTES_FILE.parent, prefix=".notes-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(notes, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, NOTES_FILE)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


@function_tool
async def save_note(text: str) -> str:
    """Save a text note or task description given by the user.

    Args:
        text: The specific text content or task statement to preserve.
    """
    text = (text or "").strip()
    if not text:
        raise ToolError("The note was empty, so nothing was saved. Ask the user what to note down.")
    if len(text) > MAX_NOTE_CHARS:
        raise ToolError(
            f"That note is too long to save ({len(text)} characters, limit {MAX_NOTE_CHARS}). "
            "Ask the user for a shorter version."
        )

    async with _lock:
        recovered = False
        try:
            notes = _load_notes()
        except _CorruptNotesError:
            _quarantine_corrupt_file()
            notes = []
            recovered = True

        notes.append({"text": text})
        _write_atomic(notes)

    message = f"I've saved that note for you: '{text}'"
    if recovered:
        message += (
            " Your old notes file was unreadable, so I set it aside as a backup "
            "and started a fresh one."
        )
    return message


@function_tool
async def list_notes(limit: int = DEFAULT_LIST_LIMIT) -> str:
    """Retrieve the most recent personal notes, newest last.

    Args:
        limit: How many of the most recent notes to read out. Defaults to 5.
    """
    limit = max(1, min(int(limit), 20))

    async with _lock:
        try:
            notes = _load_notes()
        except _CorruptNotesError:
            return (
                "Your notes file appears corrupted. I haven't changed it; "
                "the next note I save will move it aside as a backup."
            )

    if not notes:
        return "You don't have any saved notes yet."

    start = max(0, len(notes) - limit)
    lines = [f"{index + 1}. {notes[index]['text']}" for index in range(start, len(notes))]
    if start > 0:
        lines.insert(0, f"Showing the latest {len(lines)} of {len(notes)} notes.")
    return "\n".join(lines)
