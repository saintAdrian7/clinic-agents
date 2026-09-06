import json
import shutil
from pathlib import Path

import pipeline.cli as cli
from pipeline.cli import main
from pipeline.models import Note
from pipeline.replay import ReplayError, ResponseRecorder, ResponseStore

import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

CONFIG_YAML = """\
llm:
  provider: anthropic
  model: m
  api_key_env: MISSING_KEY_XYZ
  max_tokens: 100
paths:
  catalog: data/icd_catalog.json
  guidelines: data/guideline_snippets.json
  results: out/results.jsonl
  responses: out/responses.jsonl
"""

PAYLOAD = {
    "status": "unresolved",
    "confidence": "low",
    "unresolved": [{"item": "entire note", "reason": "insufficient information"}],
}


def _make_root(tmp_path):
    """Build a scratch repo root with config.yaml and the real data files."""
    (tmp_path / "config.yaml").write_text(CONFIG_YAML, encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copy(DATA_DIR / "icd_catalog.json", data_dir / "icd_catalog.json")
    shutil.copy(DATA_DIR / "guideline_snippets.json", data_dir / "guideline_snippets.json")
    return tmp_path


class _CannedProvider:
    """Fake provider returning a fixed payload."""

    def complete(self, messages, json_mode=False):
        return dict(PAYLOAD)


def test_recorder_and_store_round_trip(tmp_path):
    path = tmp_path / "responses.jsonl"
    recorder = ResponseRecorder(path, provider="p", model="m")
    note = Note(id="n-1", text="Patient has fever.")
    recorder.record(note, PAYLOAD)
    recorder.close()

    entry = json.loads(path.read_text(encoding="utf-8").strip())
    assert entry["note_id"] == "n-1"
    assert entry["provider"] == "p"
    assert entry["payload"] == PAYLOAD

    store = ResponseStore.load(path)
    assert store.payload_for(note) == PAYLOAD


def test_store_refuses_missing_note_and_changed_text(tmp_path):
    path = tmp_path / "responses.jsonl"
    recorder = ResponseRecorder(path)
    recorder.record(Note(id="n-1", text="Patient has fever."), PAYLOAD)
    recorder.close()
    store = ResponseStore.load(path)

    with pytest.raises(ReplayError, match="no recorded response"):
        store.payload_for(Note(id="n-2", text="Patient has fever."))
    with pytest.raises(ReplayError, match="differs from the recorded run"):
        store.payload_for(Note(id="n-1", text="Patient has cough."))


def test_store_rejects_invalid_json_line(tmp_path):
    path = tmp_path / "responses.jsonl"
    path.write_text('{"note_id": "n-1"}\nnot json\n', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        ResponseStore.load(path)


def test_run_records_responses_and_replay_reproduces_results(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_KEY_XYZ", raising=False)
    root = _make_root(tmp_path)
    input_path = tmp_path / "notes.jsonl"
    input_path.write_text(
        "\n".join([
            json.dumps({"id": "n-1", "text": "Patient has fever."}),
            json.dumps({"id": "n-2", "text": "Patient has cough."}),
        ]),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "get_provider", lambda config: _CannedProvider())

    assert main(["run", str(input_path)], root=root) == 0
    results_path = root / "out" / "results.jsonl"
    responses_path = root / "out" / "responses.jsonl"
    live = results_path.read_text(encoding="utf-8")
    assert len(responses_path.read_text(encoding="utf-8").strip().splitlines()) == 2

    replay_out = tmp_path / "replayed.jsonl"
    assert main(["replay", str(input_path), "--out", str(replay_out)], root=root) == 0
    assert replay_out.read_text(encoding="utf-8") == live


def test_replay_with_tampered_note_text_is_unresolved_with_reason(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_KEY_XYZ", raising=False)
    root = _make_root(tmp_path)
    input_path = tmp_path / "notes.jsonl"
    input_path.write_text(json.dumps({"id": "n-1", "text": "Patient has fever."}), encoding="utf-8")
    monkeypatch.setattr(cli, "get_provider", lambda config: _CannedProvider())
    assert main(["run", str(input_path)], root=root) == 0

    input_path.write_text(json.dumps({"id": "n-1", "text": "Patient has chest pain."}),
                          encoding="utf-8")
    replay_out = tmp_path / "replayed.jsonl"
    assert main(["replay", str(input_path), "--out", str(replay_out)], root=root) == 0
    record = json.loads(replay_out.read_text(encoding="utf-8").strip())
    assert record["status"] == "unresolved"
    assert any("differs from the recorded run" in item["reason"] for item in record["unresolved"])


def test_replay_without_recorded_responses_returns_1(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_KEY_XYZ", raising=False)
    root = _make_root(tmp_path)
    input_path = tmp_path / "notes.jsonl"
    input_path.write_text(json.dumps({"id": "n-1", "text": "Patient has fever."}), encoding="utf-8")
    assert main(["replay", str(input_path)], root=root) == 1


def test_run_without_key_records_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_KEY_XYZ", raising=False)
    root = _make_root(tmp_path)
    input_path = tmp_path / "notes.jsonl"
    input_path.write_text(json.dumps({"id": "n-1", "text": "Patient has fever."}), encoding="utf-8")
    assert main(["run", str(input_path)], root=root) == 0
    assert not (root / "out" / "responses.jsonl").exists()
