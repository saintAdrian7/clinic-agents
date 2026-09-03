import json
from pathlib import Path

from pipeline.models import Note

_ID_KEYS = ("id", "note_id", "encounter_id")
_TEXT_KEYS = ("text", "note", "note_text", "body", "content")


def load_notes(path: Path) -> list[Note]:
    """Load notes from a JSON array, JSONL, or plain-text file; never drop a record."""
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [_to_note(item, i) for i, item in enumerate(parsed)]
        if isinstance(parsed, dict):
            return [_to_note(parsed, 0)]
    except json.JSONDecodeError:
        pass
    lines = raw.splitlines()
    if all(_is_json_object(line) for line in lines if line.strip()):
        return [_to_note(_loads_or_raw(line), i) for i, line in enumerate(lines) if line.strip()]
    blocks = [b.strip() for b in raw.split("\n\n") if b.strip()]
    return [Note(id=f"note-{i + 1:03d}", text=b) for i, b in enumerate(blocks)]


def _is_json_object(line: str) -> bool:
    """True when the stripped line looks like a JSON object."""
    return line.strip().startswith("{")


def _loads_or_raw(line: str):
    """Parse a JSONL line, falling back to the raw string so nothing is dropped."""
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return line


def _to_note(item, index: int) -> Note:
    """Coerce one input record (dict or string) into a Note with a stable id."""
    if isinstance(item, str):
        return Note(id=f"note-{index + 1:03d}", text=item)
    note_id = next((str(item[k]) for k in _ID_KEYS if item.get(k)), f"note-{index + 1:03d}")
    text = next((str(item[k]) for k in _TEXT_KEYS if item.get(k)), "")
    if not text:
        text = json.dumps(item, ensure_ascii=False)
    return Note(id=note_id, text=text)
