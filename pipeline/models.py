from dataclasses import asdict, dataclass, field


def _unresolved_items(value) -> list[dict]:
    """Normalise the unresolved field; a bare string keeps its reason rather than being dropped."""
    if value in (None, "", [], {}):
        return []
    if isinstance(value, (str, dict)):
        value = [value]
    if not isinstance(value, list):
        return [{"item": "entire note", "reason": str(value)}]
    items = []
    for entry in value:
        if isinstance(entry, dict):
            items.append(entry)
        else:
            items.append({"item": "entire note", "reason": str(entry)})
    return items


@dataclass
class Note:
    id: str
    text: str


@dataclass
class Evidence:
    kind: str  # note | catalog | guideline
    ref: str   # "" for note quotes, catalogue code, or guideline id
    quote: str


@dataclass
class CodeProposal:
    code: str
    title: str
    rationale: str
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class Candidate:
    code: str
    title: str
    missing_discriminator: str


@dataclass
class Decision:
    note_id: str
    status: str  # assigned | provisional | unresolved
    extracted_facts: dict = field(default_factory=dict)
    codes: list[CodeProposal] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    confidence: str = "low"
    confidence_rationale: str = ""
    would_raise_confidence: str = ""
    would_lower_confidence: str = ""
    unresolved: list[dict] = field(default_factory=list)
    data_quality_flags: list[str] = field(default_factory=list)
    pipeline_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to a JSON-ready dict."""
        return asdict(self)

    @classmethod
    def unresolved_decision(cls, note_id: str, reason: str) -> "Decision":
        """Decision for a note the pipeline could not place; the reason is preserved."""
        return cls(note_id=note_id, status="unresolved",
                   unresolved=[{"item": "entire note", "reason": reason}],
                   confidence="low", confidence_rationale=reason)

    @classmethod
    def from_llm(cls, note_id: str, payload: dict) -> "Decision":
        """Build from model JSON, tolerating missing, extra or wrongly-typed keys."""
        dropped: list[str] = []

        def objects(value, where: str) -> list[dict]:
            """Keep only the dict entries of a list-shaped field, recording what was skipped."""
            if isinstance(value, dict):
                value = [value]
            if not isinstance(value, list):
                if value not in (None, ""):
                    dropped.append(f"{where} was {type(value).__name__}, not a list; ignored")
                return []
            kept = []
            for item in value:
                if isinstance(item, dict):
                    kept.append(item)
                else:
                    dropped.append(f"{where} entry {item!r} was not an object; ignored")
            return kept

        def ev(items):
            return [Evidence(kind=str(e.get("kind", "")), ref=str(e.get("ref", "")),
                             quote=str(e.get("quote", ""))) for e in objects(items, "evidence")]

        facts = payload.get("extracted_facts")
        if facts is not None and not isinstance(facts, dict):
            dropped.append(f"extracted_facts was {type(facts).__name__}, not an object; ignored")
            facts = None
        flags = payload.get("data_quality_flags")
        if isinstance(flags, (str, dict)):
            flags = [flags]
        notes = payload.get("pipeline_notes")
        if isinstance(notes, (str, dict)):
            notes = [notes]
        return cls(
            note_id=note_id,
            status=str(payload.get("status", "unresolved")),
            extracted_facts=facts or {},
            codes=[CodeProposal(code=str(c.get("code", "")), title=str(c.get("title", "")),
                                rationale=str(c.get("rationale", "")), evidence=ev(c.get("evidence")))
                   for c in objects(payload.get("codes"), "codes")],
            candidates=[Candidate(code=str(c.get("code", "")), title=str(c.get("title", "")),
                                  missing_discriminator=str(c.get("missing_discriminator", "")))
                        for c in objects(payload.get("candidates"), "candidates")],
            confidence=str(payload.get("confidence", "low")),
            confidence_rationale=str(payload.get("confidence_rationale", "")),
            would_raise_confidence=str(payload.get("would_raise_confidence", "")),
            would_lower_confidence=str(payload.get("would_lower_confidence", "")),
            unresolved=_unresolved_items(payload.get("unresolved")),
            data_quality_flags=[str(f) for f in flags or []],
            pipeline_notes=[str(n) for n in notes or []]
            + [f"parser: {d}" for d in dropped],
        )
