from pipeline.knowledge import Knowledge
from pipeline.models import Candidate, Decision

_STATUSES = {"assigned", "provisional", "unresolved"}
_CONFIDENCE = {"high", "moderate", "low"}


def validate(decision: Decision, knowledge: Knowledge) -> Decision:
    """Enforce output invariants; downgrade violations to unresolved, never drop or trust them."""
    notes = decision.pipeline_notes
    if decision.status not in _STATUSES:
        notes.append(f"validator: unknown status '{decision.status}' -> unresolved")
        decision.status = "unresolved"
    if decision.confidence not in _CONFIDENCE:
        notes.append(f"validator: unknown confidence '{decision.confidence}' -> low")
        decision.confidence = "low"

    kept = []
    for proposal in decision.codes:
        if proposal.code not in knowledge.codes:
            notes.append(f"validator: proposed code '{proposal.code}' not in catalogue; "
                         "moved to unresolved (possible fabrication)")
            decision.unresolved.append({"item": f"proposed code {proposal.code} ({proposal.title})",
                                        "reason": "code does not exist in the catalogue in use"})
            continue
        has_note_quote = any(e.kind == "note" and e.quote.strip() for e in proposal.evidence)
        cites_source = any(e.kind in ("guideline", "catalog") and e.ref for e in proposal.evidence)
        bad_gdl = [e.ref for e in proposal.evidence
                   if e.kind == "guideline" and e.ref not in knowledge.guideline_ids]
        if bad_gdl:
            notes.append(f"validator: {proposal.code} cites unknown guideline(s) {bad_gdl}; dropped citation(s)")
            proposal.evidence = [e for e in proposal.evidence
                                 if not (e.kind == "guideline" and e.ref in bad_gdl)]
            cites_source = any(e.kind in ("guideline", "catalog") and e.ref for e in proposal.evidence)
        if not (has_note_quote and cites_source):
            notes.append(f"validator: {proposal.code} lacks required evidence "
                         "(note quote + catalogue/guideline citation); demoted to candidate")
            decision.candidates.append(Candidate(code=proposal.code, title=proposal.title,
                                                 missing_discriminator="evidence not supplied by model"))
            continue
        kept.append(proposal)
    decision.codes = kept

    if decision.status in ("assigned", "provisional") and not decision.codes:
        notes.append("validator: status was "
                     f"'{decision.status}' with no surviving evidenced code -> unresolved")
        decision.status = "unresolved"
        if not decision.unresolved:
            decision.unresolved.append({"item": "entire note",
                                        "reason": "no proposed code survived evidence validation"})
    if decision.status == "unresolved" and decision.confidence == "high":
        notes.append("validator: high confidence on unresolved -> low")
        decision.confidence = "low"
    if decision.confidence == "high" and decision.candidates:
        notes.append("validator: high confidence with open candidates -> moderate (GDL-040)")
        decision.confidence = "moderate"
    return decision
