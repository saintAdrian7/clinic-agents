import json
import shutil
from pathlib import Path

import pipeline.cli as cli
from pipeline.cli import main
from pipeline.models import Decision

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
"""


def _make_root(tmp_path):
    """Build a scratch repo root with config.yaml and the real data files."""
    (tmp_path / "config.yaml").write_text(CONFIG_YAML, encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copy(DATA_DIR / "icd_catalog.json", data_dir / "icd_catalog.json")
    shutil.copy(DATA_DIR / "guideline_snippets.json", data_dir / "guideline_snippets.json")
    return tmp_path


def test_run_with_no_key_produces_unresolved_jsonl_for_every_note(tmp_path, monkeypatch):
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

    exit_code = main(["run", str(input_path)], root=root)
    assert exit_code == 0

    out_path = root / "out" / "results.jsonl"
    lines = out_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    records = [json.loads(line) for line in lines]
    assert [r["note_id"] for r in records] == ["n-1", "n-2"]
    for record in records:
        assert record["status"] == "unresolved"
        assert any("no model" in item["reason"] for item in record["unresolved"])


def test_decision_with_non_ascii_confidence_rationale_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_KEY_XYZ", raising=False)
    root = _make_root(tmp_path)
    input_path = tmp_path / "notes.jsonl"
    input_path.write_text(json.dumps({"id": "n-1", "text": "Patient has fever."}), encoding="utf-8")

    def fake_code_note(note, provider, knowledge):
        return Decision(note_id=note.id, status="unresolved",
                        confidence="low", confidence_rationale="score ≥ threshold")

    monkeypatch.setattr(cli, "code_note", fake_code_note)

    exit_code = main(["run", str(input_path)], root=root)
    assert exit_code == 0

    out_path = root / "out" / "results.jsonl"
    record = json.loads(out_path.read_text(encoding="utf-8").strip())
    assert record["confidence_rationale"] == "score ≥ threshold"


def test_missing_input_file_returns_1(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_KEY_XYZ", raising=False)
    root = _make_root(tmp_path)
    exit_code = main(["run", str(tmp_path / "does-not-exist.jsonl")], root=root)
    assert exit_code == 1
