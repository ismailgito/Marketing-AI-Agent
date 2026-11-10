import json
from pathlib import Path
from livekit.agents import function_tool # type: ignore 

# Ensure resolving location relative to root workspace setup
NOTES_FILE = Path(__file__).resolve().parent.parent / "data" / "notes.json"

@function_tool
async def save_note(text: str) -> str:
    """Save a text note or task description given by the user.

    Args:
        text: The specific text content or task statement to preserve.
    """
    NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)

    notes = []
    if NOTES_FILE.exists():
        try:
            notes = json.loads(NOTES_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            notes = []

    notes.append({"text": text})
    NOTES_FILE.write_text(json.dumps(notes, indent=2), encoding="utf-8")
    return f"I've saved that note for you: '{text}'"

@function_tool
async def list_notes() -> str:
    """Retrieve and list all previously saved personal notes."""
    if not NOTES_FILE.exists():
        return "You don't have any saved notes yet."

    try:
        notes = json.loads(NOTES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "Your notes file appears corrupted."

    if not notes:
        return "Your notes file is empty."

    return "\n".join(
        f"{index + 1}. {note['text']}"
        for index, note in enumerate(notes)
    )
