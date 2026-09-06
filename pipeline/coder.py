from pipeline.knowledge import Knowledge
from pipeline.llm import LLMError
from pipeline.models import Decision, Note
from pipeline.prompt import build_messages
from pipeline.validate import validate

NO_MODEL_REASON = ("no model available (no API key configured); "
                   "note carried forward unresolved for coder review")


def code_note(note: Note, provider, knowledge: Knowledge) -> Decision:
    """Run one note through the model and validator; failures become unresolved, never crashes."""
    if provider is None:
        return Decision.unresolved_decision(note.id, NO_MODEL_REASON)
    try:
        payload = provider.complete(build_messages(knowledge, note), json_mode=True)
        decision = Decision.from_llm(note.id, payload)
    except LLMError as e:
        return Decision.unresolved_decision(note.id, f"model call failed: {e}")
    return validate(decision, knowledge, note.text)
