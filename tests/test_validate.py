from pipeline.knowledge import Knowledge
from pipeline.models import Candidate, CodeProposal, Decision, Evidence
from pipeline.validate import validate


def _knowledge():
    """Build a tiny hand-written Knowledge fixture."""
    return Knowledge(
        codes={
            "BA40": {"code": "BA40", "title": "Heart failure", "chapter": "11", "synonyms": []},
            "MD11": {"code": "MD11", "title": "Fever", "chapter": "21", "synonyms": []},
        },
        guidelines=[{"id": "GDL-004", "title": "Fever workup", "source": "manual",
                     "effective": "2024-01-01", "text": "Fever is coded when no cause is found."}],
        added_codes=set(),
    )


def _valid_decision():
    return Decision(
        note_id="n1",
        status="assigned",
        codes=[CodeProposal(
            code="BA40", title="Heart failure", rationale="documented",
            evidence=[
                Evidence(kind="note", ref="", quote="patient has heart failure"),
                Evidence(kind="guideline", ref="GDL-004", quote="Fever is coded when no cause is found."),
            ],
        )],
        confidence="high",
    )


def test_fabricated_code_moved_to_unresolved():
    decision = Decision(
        note_id="n1", status="assigned",
        codes=[CodeProposal(code="ZZ99", title="Not real", rationale="",
                             evidence=[Evidence(kind="note", ref="", quote="x")])],
        confidence="high",
    )
    result = validate(decision, _knowledge())
    assert result.codes == []
    assert result.status == "unresolved"
    assert any("ZZ99" in item["item"] for item in result.unresolved)
    assert any("possible fabrication" in n for n in result.pipeline_notes)


def test_evidence_free_code_demoted_to_candidate():
    decision = Decision(
        note_id="n1", status="assigned",
        codes=[CodeProposal(code="BA40", title="Heart failure", rationale="", evidence=[])],
        confidence="high",
    )
    result = validate(decision, _knowledge())
    assert result.codes == []
    assert len(result.candidates) == 1
    assert result.candidates[0].code == "BA40"
    assert any("lacks required evidence" in n for n in result.pipeline_notes)


def test_assigned_with_nothing_surviving_becomes_unresolved():
    decision = Decision(
        note_id="n1", status="assigned",
        codes=[CodeProposal(code="BA40", title="Heart failure", rationale="", evidence=[])],
        confidence="moderate",
    )
    result = validate(decision, _knowledge())
    assert result.status == "unresolved"
    assert any(item["item"] == "entire note" for item in result.unresolved)


def test_unknown_guideline_citation_dropped_but_code_can_still_survive():
    decision = Decision(
        note_id="n1", status="assigned",
        codes=[CodeProposal(
            code="BA40", title="Heart failure", rationale="documented",
            evidence=[
                Evidence(kind="note", ref="", quote="patient has heart failure"),
                Evidence(kind="guideline", ref="GDL-999", quote="bogus"),
                Evidence(kind="catalog", ref="BA40", quote="Heart failure"),
            ],
        )],
        confidence="high",
    )
    result = validate(decision, _knowledge())
    assert len(result.codes) == 1
    assert all(e.ref != "GDL-999" for e in result.codes[0].evidence)
    assert any("cites unknown guideline" in n for n in result.pipeline_notes)


def test_unknown_guideline_citation_with_no_other_source_demotes_to_candidate():
    decision = Decision(
        note_id="n1", status="assigned",
        codes=[CodeProposal(
            code="BA40", title="Heart failure", rationale="documented",
            evidence=[
                Evidence(kind="note", ref="", quote="patient has heart failure"),
                Evidence(kind="guideline", ref="GDL-999", quote="bogus"),
            ],
        )],
        confidence="high",
    )
    result = validate(decision, _knowledge())
    assert result.codes == []
    assert len(result.candidates) == 1


def test_high_confidence_with_candidates_moved_to_moderate():
    decision = Decision(
        note_id="n1", status="assigned",
        codes=[CodeProposal(
            code="BA40", title="Heart failure", rationale="documented",
            evidence=[
                Evidence(kind="note", ref="", quote="patient has heart failure"),
                Evidence(kind="guideline", ref="GDL-004", quote="Fever is coded when no cause is found."),
            ],
        )],
        candidates=[Candidate(code="MD11", title="Fever", missing_discriminator="cause")],
        confidence="high",
    )
    result = validate(decision, _knowledge())
    assert result.confidence == "moderate"
    assert any("GDL-040" in n for n in result.pipeline_notes)


def test_proposal_title_drift_corrected_to_catalogue_title():
    decision = Decision(
        note_id="n1", status="assigned",
        codes=[CodeProposal(
            code="BA40", title="Wrong title", rationale="documented",
            evidence=[
                Evidence(kind="note", ref="", quote="patient has heart failure"),
                Evidence(kind="guideline", ref="GDL-004", quote="Fever is coded when no cause is found."),
            ],
        )],
        confidence="high",
    )
    result = validate(decision, _knowledge())
    assert result.codes[0].title == "Heart failure"
    assert any("title for BA40 corrected from 'Wrong title' to catalogue title 'Heart failure'" in n
              for n in result.pipeline_notes)


def test_candidate_title_drift_corrected_to_catalogue_title():
    decision = Decision(
        note_id="n1", status="assigned",
        codes=[CodeProposal(
            code="BA40", title="Heart failure", rationale="documented",
            evidence=[
                Evidence(kind="note", ref="", quote="patient has heart failure"),
                Evidence(kind="guideline", ref="GDL-004", quote="Fever is coded when no cause is found."),
            ],
        )],
        candidates=[Candidate(code="MD11", title="Wrong candidate title", missing_discriminator="cause")],
        confidence="high",
    )
    result = validate(decision, _knowledge())
    matching = [c for c in result.candidates if c.code == "MD11"]
    assert matching[0].title == "Fever"
    assert any("title for MD11 corrected from 'Wrong candidate title' to catalogue title 'Fever'" in n
              for n in result.pipeline_notes)


def test_fully_valid_decision_passes_through_untouched():
    decision = _valid_decision()
    result = validate(decision, _knowledge())
    assert result.status == "assigned"
    assert result.confidence == "high"
    assert len(result.codes) == 1
    assert result.codes[0].code == "BA40"
    assert result.pipeline_notes == []


def test_unknown_status_downgraded_to_unresolved():
    decision = Decision(note_id="n1", status="weird", confidence="high")
    result = validate(decision, _knowledge())
    assert result.status == "unresolved"
    assert any("unknown status" in n for n in result.pipeline_notes)


def test_unknown_confidence_downgraded_to_low():
    decision = Decision(note_id="n1", status="unresolved", confidence="super-high")
    result = validate(decision, _knowledge())
    assert result.confidence == "low"
    assert any("unknown confidence" in n for n in result.pipeline_notes)
