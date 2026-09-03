import json

from pipeline.models import Decision


def test_from_llm_empty_payload_defaults():
    decision = Decision.from_llm("note-1", {})
    assert decision.note_id == "note-1"
    assert decision.status == "unresolved"
    assert decision.extracted_facts == {}
    assert decision.codes == []
    assert decision.candidates == []
    assert decision.confidence == "low"
    assert decision.unresolved == []
    assert decision.data_quality_flags == []
    assert decision.pipeline_notes == []


def test_from_llm_round_trips_codes_and_evidence():
    payload = {
        "status": "assigned",
        "codes": [
            {
                "code": "A1",
                "title": "Some condition",
                "rationale": "documented explicitly",
                "evidence": [{"kind": "note", "ref": "", "quote": "patient reports fever"}],
            }
        ],
        "candidates": [{"code": "B2", "title": "Other condition", "missing_discriminator": "laterality"}],
    }
    decision = Decision.from_llm("note-2", payload)
    assert decision.status == "assigned"
    assert len(decision.codes) == 1
    assert decision.codes[0].code == "A1"
    assert decision.codes[0].title == "Some condition"
    assert decision.codes[0].rationale == "documented explicitly"
    assert len(decision.codes[0].evidence) == 1
    assert decision.codes[0].evidence[0].kind == "note"
    assert decision.codes[0].evidence[0].quote == "patient reports fever"
    assert len(decision.candidates) == 1
    assert decision.candidates[0].code == "B2"
    assert decision.candidates[0].missing_discriminator == "laterality"


def test_from_llm_survives_wrongly_typed_fields():
    """A live model returned codes:[0]; malformed fields must degrade, not raise."""
    payload = {
        "status": "assigned",
        "extracted_facts": "not an object",
        "codes": [0, {"code": "A1", "title": "T", "evidence": ["bare string"]}],
        "candidates": "nope",
        "unresolved": ["insufficient information"],
        "data_quality_flags": "single flag",
    }
    decision = Decision.from_llm("note-4", payload)
    assert [c.code for c in decision.codes] == ["A1"]
    assert decision.codes[0].evidence == []
    assert decision.extracted_facts == {}
    assert decision.candidates == []
    assert decision.unresolved == [{"item": "entire note", "reason": "insufficient information"}]
    assert decision.data_quality_flags == ["single flag"]
    assert any("not an object" in n for n in decision.pipeline_notes)


def test_to_dict_is_json_serializable():
    decision = Decision.unresolved_decision("note-3", "no discernible diagnosis")
    payload = decision.to_dict()
    assert payload["note_id"] == "note-3"
    assert payload["status"] == "unresolved"
    serialized = json.dumps(payload)
    assert "note-3" in serialized
