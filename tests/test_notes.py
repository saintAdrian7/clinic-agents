import json

from pipeline.notes import load_notes


def test_load_json_array_of_dicts_preserves_id(tmp_path):
    path = tmp_path / "notes.json"
    path.write_text(
        json.dumps(
            [
                {"id": "n-1", "text": "Patient has fever."},
                {"note_id": "n-2", "note": "Patient has cough."},
            ]
        ),
        encoding="utf-8",
    )
    notes = load_notes(path)
    assert [n.id for n in notes] == ["n-1", "n-2"]
    assert notes[0].text == "Patient has fever."
    assert notes[1].text == "Patient has cough."


def test_load_jsonl(tmp_path):
    path = tmp_path / "notes.jsonl"
    lines = [
        json.dumps({"id": "n-1", "text": "First note."}),
        json.dumps({"id": "n-2", "text": "Second note."}),
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    notes = load_notes(path)
    assert [n.id for n in notes] == ["n-1", "n-2"]
    assert notes[0].text == "First note."
    assert notes[1].text == "Second note."


def test_load_plain_text_two_blocks(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("First note text.\n\nSecond note text.", encoding="utf-8")
    notes = load_notes(path)
    assert [n.id for n in notes] == ["note-001", "note-002"]
    assert notes[0].text == "First note text."
    assert notes[1].text == "Second note text."


def test_load_single_block_text(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("Just one note with no blank lines.", encoding="utf-8")
    notes = load_notes(path)
    assert len(notes) == 1
    assert notes[0].id == "note-001"
    assert notes[0].text == "Just one note with no blank lines."


def test_load_malformed_jsonl_line_kept_as_raw_text(tmp_path):
    path = tmp_path / "notes.jsonl"
    good_line = json.dumps({"id": "n-1", "text": "Well-formed note."})
    bad_line = '{"id": "n-2", "text": "missing closing brace"'
    path.write_text(f"{good_line}\n{bad_line}", encoding="utf-8")
    notes = load_notes(path)
    assert len(notes) == 2
    assert notes[0].id == "n-1"
    assert notes[0].text == "Well-formed note."
    assert notes[1].id == "note-002"
    assert notes[1].text == bad_line
