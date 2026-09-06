from pipeline.knowledge import Knowledge
from pipeline.llm import LLMError
from pipeline.models import Decision, Note
from pipeline.prompt import build_messages
from pipeline.replay import ReplayError, ResponseStore
from pipeline.validate import validate

NO_MODEL_REASON = ("no model available (no API key configured); "
                   "note carried forward unresolved for coder review")


def code_note(note: Note, provider, knowledge: Knowledge, recorder=None) -> Decision:
    """Run one note through the model and validator; failures become unresolved, never crashes."""
    if provider is None:
        return Decision.unresolved_decision(note.id, NO_MODEL_REASON)
    try:
        payload = provider.complete(build_messages(knowledge, note), json_mode=True)
    except LLMError as e:
        return Decision.unresolved_decision(note.id, f"model call failed: {e}")
    if recorder is not None:
        recorder.record(note, payload)
    return validate(Decision.from_llm(note.id, payload), knowledge, note.text)


def replay_note(note: Note, store: ResponseStore, knowledge: Knowledge) -> Decision:
    """Re-run the parser and validator over a recorded response; no model involved."""
    try:
        payload = store.payload_for(note)
    except ReplayError as e:
        return Decision.unresolved_decision(note.id, f"replay: {e}")
    return validate(Decision.from_llm(note.id, payload), knowledge, note.text)
