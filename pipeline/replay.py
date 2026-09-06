import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline.models import Note


class ReplayError(Exception):
    """Raised when a recorded response cannot be matched to a note."""


def _note_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ResponseRecorder:
    """Appends one JSONL line per raw model response so a run can be replayed later."""

    def __init__(self, path: Path, provider: str = "", model: str = ""):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = path.open("w", encoding="utf-8")
        self.provider = provider
        self.model = model

    def record(self, note: Note, payload: dict) -> None:
        """Write the model payload for one note, keyed by note id and text hash."""
        line = {"note_id": note.id, "note_sha256": _note_sha(note.text),
                "provider": self.provider, "model": self.model,
                "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "payload": payload}
        self._handle.write(json.dumps(line, ensure_ascii=False) + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()


class ResponseStore:
    """Recorded responses keyed by note id, for replaying a run without a model."""

    def __init__(self, entries: dict):
        self._entries = entries

    @classmethod
    def load(cls, path: Path) -> "ResponseStore":
        entries = {}
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {e}") from e
            entries[str(entry.get("note_id"))] = entry
        return cls(entries)

    def payload_for(self, note: Note) -> dict:
        """Return the recorded payload for a note; refuse if the note text has changed."""
        entry = self._entries.get(note.id)
        if entry is None:
            raise ReplayError(f"no recorded response for note id '{note.id}'")
        if entry.get("note_sha256") != _note_sha(note.text):
            raise ReplayError(f"note text for '{note.id}' differs from the recorded run")
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            raise ReplayError(f"recorded payload for '{note.id}' is not an object")
        return payload
