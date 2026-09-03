import pathlib

from pipeline.config import Config
from pipeline.knowledge import Knowledge
from pipeline.models import Note
from pipeline.prompt import build_messages


def _repo_knowledge():
    """Load Knowledge from the real repository data files."""
    config = Config.load(pathlib.Path(__file__).resolve().parents[1])
    return Knowledge.load(config)


def test_build_messages_includes_note_and_corpus():
    knowledge = _repo_knowledge()
    note = Note(id="note-42", text="Patient reports abdominal pain for three days.")
    messages = build_messages(knowledge, note)

    assert len(messages) == 2
    system = messages[0]["content"]
    user = messages[1]["content"]

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"

    assert "<catalog>" in system and "</catalog>" in system
    assert "<guidelines>" in system and "</guidelines>" in system
    assert note.text in user
    assert "note-42" in user

    # GDL-040's quoted sentence appears verbatim in the policy section.
    assert ("Where the documented condition falls outside the entries available in "
            "the catalogue in use, the encounter is recorded as unresolved with the "
            "reason stated") in system

    # The corpus goes in whole: spot-check codes/guidelines from opposite ends.
    assert "1A00" in system
    assert "GDL-041" in system
